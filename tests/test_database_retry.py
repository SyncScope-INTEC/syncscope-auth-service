import os

import django
import pytest
from django.conf import settings

# Configure Django settings before importing anything else
if not settings.configured:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    django.setup()

import time
from unittest.mock import MagicMock, Mock, patch

import psycopg2
from django.core.cache import cache
from django.db import connection, transaction
from django.db.utils import DatabaseError, InterfaceError, OperationalError

from config.database_retry import (
    DatabaseHealthCheck,
    DatabaseRetryConfig,
    RetryableQuerySet,
    atomic_with_retry,
    close_old_connections,
    configure_connection_pool,
    database_retry,
    exponential_backoff,
    get_db_with_retry,
    is_retryable_error,
)


class TestDatabaseRetryConfig:
    """Test database retry configuration."""

    def test_config_values(self):
        """Test that configuration values are set correctly."""
        assert DatabaseRetryConfig.MAX_RETRIES == 3
        assert DatabaseRetryConfig.INITIAL_DELAY == 0.5
        assert DatabaseRetryConfig.MAX_DELAY == 5.0
        assert DatabaseRetryConfig.BACKOFF_MULTIPLIER == 2

    def test_retryable_errors_contains_expected_types(self):
        """Test that retryable errors include expected error types."""
        expected_errors = (
            OperationalError,
            InterfaceError,
            psycopg2.OperationalError,
            psycopg2.InterfaceError,
            psycopg2.DatabaseError,
            ConnectionError,
        )
        assert DatabaseRetryConfig.RETRYABLE_ERRORS == expected_errors


class TestExponentialBackoff:
    """Test exponential backoff calculation."""

    def test_backoff_calculation(self):
        """Test that exponential backoff calculates correctly."""
        # First attempt (attempt 0)
        delay0 = exponential_backoff(0)
        assert delay0 == 0.5  # INITIAL_DELAY * (2^0) = 0.5

        # Second attempt (attempt 1)
        delay1 = exponential_backoff(1)
        assert delay1 == 1.0  # INITIAL_DELAY * (2^1) = 1.0

        # Third attempt (attempt 2)
        delay2 = exponential_backoff(2)
        assert delay2 == 2.0  # INITIAL_DELAY * (2^2) = 2.0

    def test_backoff_max_delay_cap(self):
        """Test that backoff delay is capped at MAX_DELAY."""
        # Large attempt number should be capped
        delay = exponential_backoff(10)
        assert delay == DatabaseRetryConfig.MAX_DELAY  # Should be 5.0


class TestIsRetryableError:
    """Test retryable error detection."""

    def test_retryable_error_types(self):
        """Test that specific error types are detected as retryable."""
        assert is_retryable_error(OperationalError()) is True
        assert is_retryable_error(InterfaceError()) is True
        assert is_retryable_error(psycopg2.OperationalError()) is True
        assert is_retryable_error(psycopg2.InterfaceError()) is True
        assert is_retryable_error(ConnectionError()) is True

    def test_non_retryable_error_types(self):
        """Test that non-retryable error types are detected correctly."""
        assert is_retryable_error(ValueError()) is False
        assert is_retryable_error(TypeError()) is False
        assert is_retryable_error(KeyError()) is False

    def test_retryable_error_messages(self):
        """Test that specific error messages are detected as retryable."""
        retryable_messages = [
            "connection refused",
            "connection timeout",
            "connection reset",
            "connection closed",
            "connection lost",
            "server closed the connection",
            "database is starting up",
            "too many connections",
            "connection pool exhausted",
            "connection not available",
            "timeout expired",
        ]

        for msg in retryable_messages:
            error = Exception(f"Database error: {msg}")
            assert is_retryable_error(error) is True

    def test_non_retryable_error_messages(self):
        """Test that non-retryable error messages are detected correctly."""
        error = Exception("Some other database error")
        assert is_retryable_error(error) is False

    def test_case_insensitive_message_matching(self):
        """Test that error message matching is case insensitive."""
        error = Exception("CONNECTION REFUSED")
        assert is_retryable_error(error) is True


class TestCloseOldConnections:
    """Test connection closing functionality."""

    @patch("config.database_retry.connection")
    @patch("config.database_retry.logger")
    def test_close_connection_success(self, mock_logger, mock_connection):
        """Test successful connection closure."""
        mock_connection.close.return_value = None

        close_old_connections()

        mock_connection.close.assert_called_once()
        mock_logger.info.assert_called_once_with("Closed old database connection")

    @patch("config.database_retry.connection")
    @patch("config.database_retry.logger")
    def test_close_connection_error(self, mock_logger, mock_connection):
        """Test connection closure with error."""
        mock_connection.close.side_effect = Exception("Close error")

        close_old_connections()

        mock_connection.close.assert_called_once()
        mock_logger.warning.assert_called_once_with("Error closing connection: Close error")


class TestDatabaseRetry:
    """Test database retry decorator."""

    def test_successful_operation(self):
        """Test that successful operations don't retry."""
        call_count = 0

        @database_retry()
        def test_function():
            nonlocal call_count
            call_count += 1
            return "success"

        result = test_function()

        assert result == "success"
        assert call_count == 1

    @patch("config.database_retry.time.sleep")
    @patch("config.database_retry.close_old_connections")
    def test_retry_on_retryable_error(self, mock_close_connections, mock_sleep):
        """Test that retryable errors trigger retries."""
        call_count = 0

        @database_retry(max_retries=2)
        def test_function():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise OperationalError("connection refused")
            return "success"

        result = test_function()

        assert result == "success"
        assert call_count == 3
        assert mock_close_connections.call_count == 2  # Called on retries
        assert mock_sleep.call_count == 2  # Sleep called for each retry

    @patch("config.database_retry.time.sleep")
    def test_non_retryable_error_no_retry(self, mock_sleep):
        """Test that non-retryable errors don't trigger retries."""
        call_count = 0

        @database_retry()
        def test_function():
            nonlocal call_count
            call_count += 1
            raise ValueError("not retryable")

        with pytest.raises(ValueError):
            test_function()

        assert call_count == 1
        assert mock_sleep.call_count == 0

    @patch("config.database_retry.time.sleep")
    def test_max_retries_exceeded(self, mock_sleep):
        """Test that max retries are respected."""
        call_count = 0

        @database_retry(max_retries=2)
        def test_function():
            nonlocal call_count
            call_count += 1
            raise OperationalError("connection refused")

        with pytest.raises(OperationalError):
            test_function()

        assert call_count == 3  # Original + 2 retries
        assert mock_sleep.call_count == 2

    @patch("config.database_retry.logger")
    def test_logging_disabled(self, mock_logger):
        """Test that logging can be disabled."""

        @database_retry(log_attempts=False)
        def test_function():
            raise ValueError("error")

        with pytest.raises(ValueError):
            test_function()

        # Should not log when log_attempts=False
        mock_logger.error.assert_not_called()
        mock_logger.warning.assert_not_called()

    def test_custom_max_retries(self):
        """Test custom max retries parameter."""
        call_count = 0

        @database_retry(max_retries=1)
        def test_function():
            nonlocal call_count
            call_count += 1
            raise OperationalError("connection refused")

        with pytest.raises(OperationalError):
            test_function()

        assert call_count == 2  # Original + 1 retry


@pytest.mark.django_db
class TestDatabaseHealthCheck:
    """Test database health check functionality."""

    def setUp(self):
        cache.clear()

    @patch("config.database_retry.connection")
    def test_check_connection_success(self, mock_connection):
        """Test successful database connection check."""
        mock_cursor = Mock()
        mock_connection.cursor.return_value.__enter__.return_value = mock_cursor

        result = DatabaseHealthCheck.check_connection()

        assert result is True
        mock_cursor.execute.assert_called_once_with("SELECT 1")
        mock_cursor.fetchone.assert_called_once()

    @patch("config.database_retry.connection")
    @patch("config.database_retry.logger")
    def test_check_connection_failure(self, mock_logger, mock_connection):
        """Test database connection check failure."""
        mock_connection.cursor.side_effect = OperationalError("connection failed")

        result = DatabaseHealthCheck.check_connection()

        assert result is False
        mock_logger.warning.assert_called()

    @patch.object(DatabaseHealthCheck, "check_connection")
    def test_is_healthy_no_cache(self, mock_check):
        """Test health check without cache."""
        mock_check.return_value = True

        result = DatabaseHealthCheck.is_healthy(use_cache=False)

        assert result is True
        mock_check.assert_called_once()

    @patch.object(DatabaseHealthCheck, "check_connection")
    @patch("config.database_retry.cache")
    def test_is_healthy_with_cache_hit(self, mock_cache, mock_check):
        """Test health check with cache hit."""
        mock_cache.get.return_value = True

        result = DatabaseHealthCheck.is_healthy(use_cache=True)

        assert result is True
        mock_check.assert_not_called()  # Should not check if cached

    @patch.object(DatabaseHealthCheck, "check_connection")
    @patch("config.database_retry.cache")
    def test_is_healthy_with_cache_miss(self, mock_cache, mock_check):
        """Test health check with cache miss."""
        mock_cache.get.return_value = None
        mock_check.return_value = True

        result = DatabaseHealthCheck.is_healthy(use_cache=True)

        assert result is True
        mock_check.assert_called_once()
        mock_cache.set.assert_called_once_with(
            DatabaseHealthCheck.HEALTH_CACHE_KEY, True, DatabaseHealthCheck.HEALTH_CACHE_TIMEOUT
        )

    @patch("config.database_retry.cache")
    def test_mark_unhealthy(self, mock_cache):
        """Test marking database as unhealthy."""
        DatabaseHealthCheck.mark_unhealthy()

        mock_cache.set.assert_called_once_with(
            DatabaseHealthCheck.HEALTH_CACHE_KEY, False, DatabaseHealthCheck.HEALTH_CACHE_TIMEOUT
        )


class TestGetDbWithRetry:
    """Test database connection with retry."""

    @patch("config.database_retry.connection")
    def test_successful_connection(self, mock_connection):
        """Test successful database connection."""
        mock_cursor = Mock()
        mock_connection.cursor.return_value.__enter__.return_value = mock_cursor

        result = get_db_with_retry()

        assert result == mock_connection
        mock_cursor.execute.assert_called_once_with("SELECT 1")


class TestRetryableQuerySet:
    """Test retryable queryset wrapper."""

    def test_init(self):
        """Test RetryableQuerySet initialization."""
        mock_queryset = Mock()
        retryable_qs = RetryableQuerySet(mock_queryset)

        assert retryable_qs.queryset == mock_queryset

    def test_get_method(self):
        """Test get method with retry."""
        mock_queryset = Mock()
        mock_queryset.get.return_value = "result"
        retryable_qs = RetryableQuerySet(mock_queryset)

        result = retryable_qs.get(id=1)

        assert result == "result"
        mock_queryset.get.assert_called_once_with(id=1)

    def test_filter_method(self):
        """Test filter method with retry."""
        mock_queryset = Mock()
        mock_queryset.filter.return_value = "filtered"
        retryable_qs = RetryableQuerySet(mock_queryset)

        result = retryable_qs.filter(active=True)

        assert result == "filtered"
        mock_queryset.filter.assert_called_once_with(active=True)

    def test_create_method(self):
        """Test create method with retry."""
        mock_queryset = Mock()
        mock_queryset.create.return_value = "created"
        retryable_qs = RetryableQuerySet(mock_queryset)

        result = retryable_qs.create(name="test")

        assert result == "created"
        mock_queryset.create.assert_called_once_with(name="test")

    def test_update_method(self):
        """Test update method with retry."""
        mock_queryset = Mock()
        mock_queryset.update.return_value = 1
        retryable_qs = RetryableQuerySet(mock_queryset)

        result = retryable_qs.update(active=False)

        assert result == 1
        mock_queryset.update.assert_called_once_with(active=False)

    def test_delete_method(self):
        """Test delete method with retry."""
        mock_queryset = Mock()
        mock_queryset.delete.return_value = (1, {"Model": 1})
        retryable_qs = RetryableQuerySet(mock_queryset)

        result = retryable_qs.delete()

        assert result == (1, {"Model": 1})
        mock_queryset.delete.assert_called_once()

    def test_exists_method(self):
        """Test exists method with retry."""
        mock_queryset = Mock()
        mock_queryset.exists.return_value = True
        retryable_qs = RetryableQuerySet(mock_queryset)

        result = retryable_qs.exists()

        assert result is True
        mock_queryset.exists.assert_called_once()

    def test_count_method(self):
        """Test count method with retry."""
        mock_queryset = Mock()
        mock_queryset.count.return_value = 5
        retryable_qs = RetryableQuerySet(mock_queryset)

        result = retryable_qs.count()

        assert result == 5
        mock_queryset.count.assert_called_once()


class TestAtomicWithRetry:
    """Test atomic transaction with retry."""

    @patch("config.database_retry.transaction")
    def test_successful_transaction(self, mock_transaction):
        """Test successful atomic transaction."""
        # Use MagicMock to handle context manager protocol
        mock_atomic = MagicMock()
        mock_transaction.atomic.return_value = mock_atomic

        @atomic_with_retry()
        def test_function():
            return "success"

        result = test_function()

        assert result == "success"
        mock_transaction.atomic.assert_called()

    def test_atomic_with_custom_params(self):
        """Test atomic with custom parameters."""

        @atomic_with_retry(using="custom_db", savepoint=False)
        def test_function():
            return "success"

        # Function should be decorated properly
        assert callable(test_function)


class TestConfigureConnectionPool:
    """Test connection pool configuration."""

    @patch("config.database_retry.logger")
    @patch("django.conf.settings")
    def test_configure_connection_pool(self, mock_settings, mock_logger):
        """Test database connection pool configuration."""
        # Mock settings to avoid modifying real settings
        mock_db_config = {}
        mock_settings.DATABASES = {"default": mock_db_config}

        configure_connection_pool()

        # Check that connection settings were added
        assert mock_db_config.get("CONN_MAX_AGE") == 0
        assert mock_db_config.get("CONN_HEALTH_CHECKS") is True
        assert "OPTIONS" in mock_db_config

        options = mock_db_config["OPTIONS"]
        assert options["connect_timeout"] == 10
        assert options["application_name"] == "syncscope-auth-serverless"
        assert "search_path=auth" in options["options"]

        mock_logger.info.assert_called_once_with("Database configured for serverless environment")

    @patch("config.database_retry.logger")
    @patch("django.conf.settings")
    def test_configure_connection_pool_existing_options(self, mock_settings, mock_logger):
        """Test configuration with existing OPTIONS."""
        mock_db_config = {"OPTIONS": {"existing_option": "value"}}
        mock_settings.DATABASES = {"default": mock_db_config}

        configure_connection_pool()

        # Check that existing options are preserved and new ones added
        options = mock_db_config["OPTIONS"]
        assert options["existing_option"] == "value"
        assert options["connect_timeout"] == 10
