import os

import django
import pytest
from django.conf import settings

# Configure Django settings before importing anything else
if not settings.configured:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    django.setup()

import sys
from datetime import datetime
from unittest.mock import MagicMock, Mock, patch

import healthcheck


class TestCheckDatabase:
    """Test database health check functionality."""

    @patch("healthcheck.DatabaseHealthCheck")
    def test_check_database_healthy(self, mock_db_health):
        """Test successful database check."""
        mock_db_health.is_healthy.return_value = True

        result = healthcheck.check_database()

        assert result is True
        mock_db_health.is_healthy.assert_called_once_with(use_cache=False)

    @patch("healthcheck.DatabaseHealthCheck")
    def test_check_database_unhealthy(self, mock_db_health):
        """Test database check failure."""
        mock_db_health.is_healthy.return_value = False

        result = healthcheck.check_database()

        assert result is False
        mock_db_health.is_healthy.assert_called_once_with(use_cache=False)

    @patch("healthcheck.DatabaseHealthCheck")
    @patch("builtins.print")
    def test_check_database_exception(self, mock_print, mock_db_health):
        """Test database check with exception."""
        mock_db_health.is_healthy.side_effect = Exception("Database connection error")

        result = healthcheck.check_database()

        assert result is False
        mock_print.assert_called_once_with("Database check failed: Database connection error")


class TestCheckRedis:
    """Test Redis health check functionality."""

    @patch("django.core.cache.cache")
    def test_check_redis_healthy(self, mock_cache):
        """Test successful Redis check."""
        mock_cache.get.return_value = "test"

        result = healthcheck.check_redis()

        assert result is True
        mock_cache.set.assert_called_once_with("health_check", "test", 10)
        mock_cache.get.assert_called_once_with("health_check")

    @patch("django.core.cache.cache")
    def test_check_redis_unhealthy(self, mock_cache):
        """Test Redis check failure."""
        mock_cache.get.return_value = "wrong_value"

        result = healthcheck.check_redis()

        assert result is False

    @patch("django.core.cache.cache")
    @patch("builtins.print")
    def test_check_redis_exception(self, mock_print, mock_cache):
        """Test Redis check with exception."""
        mock_cache.set.side_effect = Exception("Redis connection error")

        result = healthcheck.check_redis()

        assert result is False
        mock_print.assert_called_once_with("Redis check failed: Redis connection error")


class TestCheckExternalServices:
    """Test external services health check."""

    @patch("healthcheck.requests")
    @patch("healthcheck.settings")
    def test_check_external_services_github_healthy(self, mock_settings, mock_requests):
        """Test successful GitHub API check."""
        mock_settings.GITHUB_CLIENT_ID = "test_client_id"
        mock_response = Mock()
        mock_response.status_code = 200
        mock_requests.get.return_value = mock_response

        result = healthcheck.check_external_services()

        assert result == [("GitHub API", True)]
        mock_requests.get.assert_called_once_with("https://api.github.com", timeout=5)

    @patch("healthcheck.requests")
    @patch("healthcheck.settings")
    def test_check_external_services_github_unhealthy(self, mock_settings, mock_requests):
        """Test failed GitHub API check."""
        mock_settings.GITHUB_CLIENT_ID = "test_client_id"
        mock_response = Mock()
        mock_response.status_code = 500
        mock_requests.get.return_value = mock_response

        result = healthcheck.check_external_services()

        assert result == [("GitHub API", False)]

    @patch("healthcheck.requests")
    @patch("healthcheck.settings")
    def test_check_external_services_github_exception(self, mock_settings, mock_requests):
        """Test GitHub API check with exception."""
        mock_settings.GITHUB_CLIENT_ID = "test_client_id"
        mock_requests.get.side_effect = Exception("Connection timeout")

        result = healthcheck.check_external_services()

        assert result == [("GitHub API", False)]

    @patch("healthcheck.settings")
    def test_check_external_services_no_github(self, mock_settings):
        """Test external services check when GitHub is not configured."""
        mock_settings.GITHUB_CLIENT_ID = None

        result = healthcheck.check_external_services()

        assert result == []


class TestRunHealthCheck:
    """Test complete health check run."""

    @patch("healthcheck.check_external_services")
    @patch("healthcheck.check_redis")
    @patch("healthcheck.check_database")
    @patch("healthcheck.datetime")
    @patch("builtins.print")
    def test_run_health_check_all_healthy(
        self, mock_print, mock_datetime, mock_check_db, mock_check_redis, mock_check_external
    ):
        """Test health check when all services are healthy."""
        # Setup mocks
        mock_datetime.now.return_value.isoformat.return_value = "2024-01-01T12:00:00"
        mock_check_db.return_value = True
        mock_check_redis.return_value = True
        mock_check_external.return_value = [("GitHub API", True)]

        healthy, results = healthcheck.run_health_check()

        assert healthy is True
        assert results == {"database": True, "redis": True, "github_api": True}

        # Check that all check functions were called
        mock_check_db.assert_called_once()
        mock_check_redis.assert_called_once()
        mock_check_external.assert_called_once()

    @patch("healthcheck.check_external_services")
    @patch("healthcheck.check_redis")
    @patch("healthcheck.check_database")
    @patch("healthcheck.datetime")
    @patch("builtins.print")
    def test_run_health_check_some_unhealthy(
        self, mock_print, mock_datetime, mock_check_db, mock_check_redis, mock_check_external
    ):
        """Test health check when some services are unhealthy."""
        # Setup mocks
        mock_datetime.now.return_value.isoformat.return_value = "2024-01-01T12:00:00"
        mock_check_db.return_value = True
        mock_check_redis.return_value = False
        mock_check_external.return_value = [("GitHub API", False)]

        healthy, results = healthcheck.run_health_check()

        assert healthy is False
        assert results == {"database": True, "redis": False, "github_api": False}

    @patch("healthcheck.check_external_services")
    @patch("healthcheck.check_redis")
    @patch("healthcheck.check_database")
    @patch("healthcheck.datetime")
    @patch("builtins.print")
    def test_run_health_check_no_external_services(
        self, mock_print, mock_datetime, mock_check_db, mock_check_redis, mock_check_external
    ):
        """Test health check with no external services."""
        # Setup mocks
        mock_datetime.now.return_value.isoformat.return_value = "2024-01-01T12:00:00"
        mock_check_db.return_value = True
        mock_check_redis.return_value = True
        mock_check_external.return_value = []

        healthy, results = healthcheck.run_health_check()

        assert healthy is True
        assert results == {"database": True, "redis": True}

    @patch("healthcheck.check_external_services")
    @patch("healthcheck.check_redis")
    @patch("healthcheck.check_database")
    @patch("healthcheck.datetime")
    @patch("builtins.print")
    def test_run_health_check_multiple_external_services(
        self, mock_print, mock_datetime, mock_check_db, mock_check_redis, mock_check_external
    ):
        """Test health check with multiple external services."""
        # Setup mocks
        mock_datetime.now.return_value.isoformat.return_value = "2024-01-01T12:00:00"
        mock_check_db.return_value = True
        mock_check_redis.return_value = True
        mock_check_external.return_value = [("GitHub API", True), ("Another Service", False)]

        healthy, results = healthcheck.run_health_check()

        assert healthy is False
        assert results == {"database": True, "redis": True, "github_api": True, "another_service": False}

    @patch("healthcheck.check_external_services")
    @patch("healthcheck.check_redis")
    @patch("healthcheck.check_database")
    @patch("healthcheck.datetime")
    @patch("builtins.print")
    def test_run_health_check_print_statements(
        self, mock_print, mock_datetime, mock_check_db, mock_check_redis, mock_check_external
    ):
        """Test that health check prints expected messages."""
        # Setup mocks
        mock_datetime.now.return_value.isoformat.return_value = "2024-01-01T12:00:00"
        mock_check_db.return_value = True
        mock_check_redis.return_value = False
        mock_check_external.return_value = [("GitHub API", True)]

        healthcheck.run_health_check()

        # Check important print calls
        print_calls = [call[0][0] for call in mock_print.call_args_list]

        # Check that header, status messages, and overall status are printed
        assert any("Health Check" in call for call in print_calls)
        assert any("Checking database" in call for call in print_calls)
        assert any("Checking Redis" in call for call in print_calls)
        assert any("Checking external services" in call for call in print_calls)
        assert any("Overall Status" in call for call in print_calls)


class TestMain:
    """Test main entry point function."""

    @patch("healthcheck.run_health_check")
    @patch("healthcheck.sys")
    def test_main_healthy_exit(self, mock_sys, mock_run_health):
        """Test main function with healthy status."""
        mock_run_health.return_value = (True, {"database": True})

        healthcheck.main()

        mock_sys.exit.assert_called_once_with(0)

    @patch("healthcheck.run_health_check")
    @patch("healthcheck.sys")
    def test_main_unhealthy_exit(self, mock_sys, mock_run_health):
        """Test main function with unhealthy status."""
        mock_run_health.return_value = (False, {"database": False})

        healthcheck.main()

        mock_sys.exit.assert_called_once_with(1)

    @patch("healthcheck.run_health_check")
    @patch("healthcheck.sys")
    @patch("builtins.print")
    def test_main_exception_exit(self, mock_print, mock_sys, mock_run_health):
        """Test main function with exception."""
        mock_run_health.side_effect = Exception("Unexpected error")

        healthcheck.main()

        mock_print.assert_called_once_with("❌ Health check failed with error: Unexpected error")
        mock_sys.exit.assert_called_once_with(1)


class TestModuleBehavior:
    """Test module-level behavior."""

    @patch("healthcheck.main")
    def test_main_called_when_run_directly(self, mock_main):
        """Test that main is called when module is run directly."""
        # This test verifies the if __name__ == "__main__" behavior
        # We can't easily test this directly, but we can verify the main function exists
        # and is callable
        assert callable(healthcheck.main)

        # Test that we can call main without errors (mocked)
        healthcheck.main()
        mock_main.assert_called_once()

    def test_all_functions_exist(self):
        """Test that all expected functions are available."""
        expected_functions = ["check_database", "check_redis", "check_external_services", "run_health_check", "main"]

        for func_name in expected_functions:
            assert hasattr(healthcheck, func_name)
            assert callable(getattr(healthcheck, func_name))
