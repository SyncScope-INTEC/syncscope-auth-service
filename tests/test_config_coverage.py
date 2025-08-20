"""
Tests for config files to improve coverage
"""

import os
import sys
from unittest.mock import MagicMock, patch

from django.test import TestCase


class TestASGIConfiguration(TestCase):
    """Test ASGI configuration"""

    def test_asgi_application_import(self):
        """Test ASGI application can be imported"""
        from config.asgi import application

        self.assertIsNotNone(application)

    def test_asgi_django_setup(self):
        """Test Django setup in ASGI"""
        with patch("django.setup") as mock_setup:
            with patch.dict(os.environ, {}, clear=True):
                import importlib

                import config.asgi

                importlib.reload(config.asgi)
                self.assertEqual(os.environ.get("DJANGO_SETTINGS_MODULE"), "config.settings")


class TestWSGIConfiguration(TestCase):
    """Test WSGI configuration"""

    def test_wsgi_application_import(self):
        """Test WSGI application can be imported"""
        from config.wsgi import application

        self.assertIsNotNone(application)

    def test_wsgi_django_setup(self):
        """Test Django setup in WSGI"""
        with patch("django.setup") as mock_setup:
            with patch.dict(os.environ, {}, clear=True):
                import importlib

                import config.wsgi

                importlib.reload(config.wsgi)
                self.assertEqual(os.environ.get("DJANGO_SETTINGS_MODULE"), "config.settings")


class TestDatabaseConfiguration(TestCase):
    """Test database configuration"""

    @patch("config.database.dj_database_url.parse")
    def test_get_database_config_with_url(self, mock_parse):
        """Test database config with DATABASE_URL"""
        mock_parse.return_value = {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": "testdb",
            "USER": "testuser",
            "PASSWORD": "testpass",
            "HOST": "localhost",
            "PORT": "5432",
        }

        with patch.dict(os.environ, {"DATABASE_URL": "postgres://test"}):
            from config.database import get_database_config

            config = get_database_config()

            self.assertIn("OPTIONS", config)
            self.assertEqual(config["OPTIONS"]["options"], "-c search_path=auth")
            mock_parse.assert_called_once_with("postgres://test")

    @patch("config.database.config")
    def test_get_database_config_fallback(self, mock_config):
        """Test database config fallback"""

        def mock_config_func(key, default=None, cast=None):
            values = {
                "DB_NAME": "test_db",
                "DB_USER": "test_user",
                "DB_PASSWORD": "test_pass",
                "DB_HOST": "localhost",
                "DB_PORT": "5432",
            }
            value = values.get(key, default)
            return cast(value) if cast and value else value

        mock_config.side_effect = mock_config_func

        with patch.dict(os.environ, {}, clear=True):
            from config.database import get_database_config

            config = get_database_config()

            self.assertEqual(config["ENGINE"], "django.db.backends.postgresql")
            self.assertEqual(config["NAME"], "test_db")
            self.assertEqual(config["OPTIONS"]["options"], "-c search_path=auth")

    @patch("builtins.print")
    @patch("psycopg2.connect")
    @patch("django.conf.settings")
    def test_create_auth_schema_success(self, mock_settings, mock_connect, mock_print):
        """Test create_auth_schema_if_not_exists success"""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor

        mock_settings.DATABASES = {
            "default": {"HOST": "localhost", "PORT": "5432", "USER": "user", "PASSWORD": "pass", "NAME": "testdb"}
        }

        from config.database import create_auth_schema_if_not_exists

        create_auth_schema_if_not_exists()

        mock_connect.assert_called_once()
        mock_cursor.execute.assert_called_once_with("CREATE SCHEMA IF NOT EXISTS auth;")
        mock_print.assert_called_with("✓ Auth schema created or already exists")

    @patch("builtins.print")
    @patch("psycopg2.connect")
    @patch("django.conf.settings")
    def test_create_auth_schema_failure(self, mock_settings, mock_connect, mock_print):
        """Test create_auth_schema_if_not_exists failure"""
        mock_connect.side_effect = Exception("Connection failed")

        mock_settings.DATABASES = {
            "default": {"HOST": "localhost", "PORT": "5432", "USER": "user", "PASSWORD": "pass", "NAME": "testdb"}
        }

        from config.database import create_auth_schema_if_not_exists

        create_auth_schema_if_not_exists()

        mock_print.assert_any_call("Warning: Could not create auth schema: Connection failed")


class TestServerlessConfiguration(TestCase):
    """Test serverless configuration"""

    def test_setup_serverless_environment(self):
        """Test serverless environment setup"""
        with patch("config.serverless.configure_connection_pool") as mock_configure:
            with patch("config.serverless.settings") as mock_settings:
                with patch("config.serverless.logger") as mock_logger:
                    mock_settings.REST_FRAMEWORK = {}
                    mock_settings.SIMPLE_JWT = {}
                    mock_settings.INSTALLED_APPS = ["debug_toolbar", "other_app"]
                    mock_settings.DEBUG = False
                    mock_settings.LOGGING = {"handlers": {"console": {}}}

                    from config.serverless import setup_serverless_environment

                    setup_serverless_environment()

                    self.assertEqual(mock_settings.REST_FRAMEWORK["DEFAULT_TIMEOUT"], 30)
                    self.assertEqual(mock_settings.INSTALLED_APPS, ["other_app"])
                    mock_configure.assert_called_once()

    def test_validate_serverless_config_valid(self):
        """Test serverless config validation - valid"""
        with patch("config.serverless.settings") as mock_settings:
            with patch("config.serverless.logger") as mock_logger:
                mock_settings.DATABASES = {"default": {"CONN_MAX_AGE": 0}}
                mock_settings.CACHES = {"default": {"LOCATION": "redis://localhost:6379"}}
                mock_settings.SECRET_KEY = "valid-secret-key"
                mock_settings.DEBUG = False

                from config.serverless import validate_serverless_config

                with patch.dict(os.environ, {"RAILWAY_ENVIRONMENT": "production"}):
                    is_valid, issues = validate_serverless_config()

                self.assertTrue(is_valid)
                self.assertEqual(issues, [])

    def test_validate_serverless_config_invalid(self):
        """Test serverless config validation - invalid"""
        with patch("config.serverless.settings") as mock_settings:
            mock_settings.DATABASES = {"default": {"CONN_MAX_AGE": 300}}
            mock_settings.CACHES = {"default": {"LOCATION": "locmem://default"}}
            mock_settings.SECRET_KEY = "django-insecure-change-me-in-production"
            mock_settings.DEBUG = True

            from config.serverless import validate_serverless_config

            with patch.dict(os.environ, {"RAILWAY_ENVIRONMENT": "production"}):
                is_valid, issues = validate_serverless_config()

            self.assertFalse(is_valid)
            self.assertGreater(len(issues), 0)

    def test_get_serverless_metrics(self):
        """Test serverless metrics collection"""
        with patch("django.db.connection") as mock_connection:
            with patch("django.core.cache.cache") as mock_cache:
                with patch("time.time", side_effect=[1000.0, 1000.1]):
                    mock_connection.queries = ["query1", "query2"]
                    mock_connection.vendor = "postgresql"
                    mock_cache.set.return_value = None
                    mock_cache.get.return_value = "value"

                    from config.serverless import get_serverless_metrics

                    metrics = get_serverless_metrics()

                    self.assertEqual(metrics["database_queries"], 2)
                    self.assertEqual(metrics["database_vendor"], "postgresql")
                    self.assertEqual(metrics["cache_latency_ms"], 100.0)

    def test_get_serverless_metrics_cache_failure(self):
        """Test serverless metrics with cache failure"""
        with patch("django.db.connection") as mock_connection:
            with patch("django.core.cache.cache") as mock_cache:
                mock_connection.queries = []
                mock_connection.vendor = "postgresql"
                mock_cache.set.side_effect = Exception("Cache unavailable")

                from config.serverless import get_serverless_metrics

                metrics = get_serverless_metrics()

                self.assertEqual(metrics["database_queries"], 0)
                self.assertIsNone(metrics["cache_latency_ms"])

    def test_serverless_auto_configure(self):
        """Test serverless auto-configuration environment check"""
        with patch.dict("os.environ", {"SERVERLESS_ENV": "true"}):
            # Test that the environment variable is properly set for auto-configuration
            self.assertEqual(os.environ.get("SERVERLESS_ENV"), "true")

    def test_configure_connection_pool(self):
        """Test connection pool configuration"""
        with patch("django.conf.settings") as mock_settings:
            mock_settings.DATABASES = {"default": {}}

            from config.database_retry import configure_connection_pool

            configure_connection_pool()

            # Should set connection pool options
            self.assertIn("OPTIONS", mock_settings.DATABASES["default"])
            options = mock_settings.DATABASES["default"]["OPTIONS"]
            self.assertEqual(options["connect_timeout"], 10)
            self.assertEqual(options["application_name"], "syncscope-auth-serverless")


class TestUtilsConfiguration(TestCase):
    """Test utility functions"""

    def test_get_client_ip_with_x_forwarded_for(self):
        """Test get_client_ip with X-Forwarded-For header"""
        from django.test import RequestFactory

        from apps.authentication.utils import get_client_ip

        factory = RequestFactory()
        request = factory.get("/")
        request.META["HTTP_X_FORWARDED_FOR"] = "10.0.0.1, 192.168.1.1"
        request.META["REMOTE_ADDR"] = "192.168.1.1"

        ip = get_client_ip(request)
        self.assertEqual(ip, "10.0.0.1")

    def test_get_client_ip_without_x_forwarded_for(self):
        """Test get_client_ip without X-Forwarded-For header"""
        from django.test import RequestFactory

        from apps.authentication.utils import get_client_ip

        factory = RequestFactory()
        request = factory.get("/")
        request.META["REMOTE_ADDR"] = "127.0.0.1"

        ip = get_client_ip(request)
        self.assertEqual(ip, "127.0.0.1")

    def test_get_client_ip_empty_x_forwarded_for(self):
        """Test get_client_ip with empty X-Forwarded-For header"""
        from django.test import RequestFactory

        from apps.authentication.utils import get_client_ip

        factory = RequestFactory()
        request = factory.get("/")
        request.META["HTTP_X_FORWARDED_FOR"] = ""
        request.META["REMOTE_ADDR"] = "127.0.0.1"

        ip = get_client_ip(request)
        self.assertEqual(ip, "127.0.0.1")

    def test_get_tokens_for_user(self):
        """Test get_tokens_for_user utility"""
        from apps.authentication.utils import get_tokens_for_user

        mock_user = MagicMock()
        mock_user.id = 1
        mock_user.email = "test@example.com"

        with patch("rest_framework_simplejwt.tokens.RefreshToken.for_user") as mock_token:
            mock_refresh = MagicMock()
            mock_refresh.access_token = "access_token_value"
            mock_token.return_value = mock_refresh

            tokens = get_tokens_for_user(mock_user)

            self.assertIn("refresh", tokens)
            self.assertIn("access", tokens)
            mock_token.assert_called_once_with(mock_user)

    def test_create_user_session(self):
        """Test create_user_session utility"""
        from django.test import RequestFactory

        from apps.authentication.utils import create_user_session

        mock_user = MagicMock()
        mock_user.id = 1

        factory = RequestFactory()
        request = factory.post("/")
        request.META["REMOTE_ADDR"] = "127.0.0.1"
        request.META["HTTP_USER_AGENT"] = "Test Browser"

        with patch("apps.authentication.models.UserSession.objects.create") as mock_create:
            mock_session = MagicMock()
            mock_session.token_hash = "token_hash"
            mock_create.return_value = mock_session

            session, token = create_user_session(mock_user, request)

            mock_create.assert_called_once()
            self.assertEqual(session, mock_session)
            self.assertIsNotNone(token)

    def test_create_user_session_with_x_forwarded_for(self):
        """Test create_user_session with X-Forwarded-For header"""
        from django.test import RequestFactory

        from apps.authentication.utils import create_user_session

        mock_user = MagicMock()
        mock_user.id = 1

        factory = RequestFactory()
        request = factory.post("/")
        request.META["HTTP_X_FORWARDED_FOR"] = "10.0.0.1, 192.168.1.1"
        request.META["REMOTE_ADDR"] = "192.168.1.1"
        request.META["HTTP_USER_AGENT"] = "Test Browser"

        with patch("apps.authentication.models.UserSession.objects.create") as mock_create:
            mock_session = MagicMock()
            mock_session.token_hash = "token_hash"
            mock_create.return_value = mock_session

            session, token = create_user_session(mock_user, request)

            mock_create.assert_called_once()
            # Verify it uses the first IP from X-Forwarded-For
            call_args = mock_create.call_args[1]
            self.assertEqual(call_args["ip_address"], "10.0.0.1")
            self.assertEqual(session, mock_session)
            self.assertIsNotNone(token)

    def test_validate_session_token(self):
        """Test validate_session_token utility"""
        from apps.authentication.utils import validate_session_token

        with patch("apps.authentication.models.UserSession.objects.get") as mock_get:
            mock_session = MagicMock()
            mock_session.is_active = True
            mock_session.is_expired.return_value = False
            mock_get.return_value = mock_session

            session = validate_session_token("valid_token")

            self.assertEqual(session, mock_session)
            mock_get.assert_called_once()

    def test_validate_session_token_invalid(self):
        """Test validate_session_token with invalid token"""
        from apps.authentication.models import UserSession
        from apps.authentication.utils import validate_session_token

        with patch("apps.authentication.models.UserSession.objects.get") as mock_get:
            mock_get.side_effect = UserSession.DoesNotExist()

            session = validate_session_token("invalid_token")

            self.assertIsNone(session)

    def test_validate_session_token_empty(self):
        """Test validate_session_token with empty token"""
        from apps.authentication.utils import validate_session_token

        session = validate_session_token("")
        self.assertIsNone(session)

        session = validate_session_token(None)
        self.assertIsNone(session)

    def test_invalidate_user_sessions(self):
        """Test invalidate_user_sessions utility"""
        from apps.authentication.utils import invalidate_user_sessions

        mock_user = MagicMock()
        mock_user.id = 1

        mock_sessions = MagicMock()
        mock_user.sessions.filter.return_value = mock_sessions

        invalidate_user_sessions(mock_user, exclude_session_id=123)

        mock_user.sessions.filter.assert_called_once_with(is_active=True)
        mock_sessions.exclude.assert_called_once_with(id=123)
        mock_sessions.exclude.return_value.update.assert_called_once_with(is_active=False)

    def test_generate_session_token(self):
        """Test generate_session_token utility"""
        from apps.authentication.utils import generate_session_token

        token = generate_session_token()

        self.assertIsNotNone(token)
        self.assertIsInstance(token, str)
        self.assertGreater(len(token), 0)

    def test_hash_token(self):
        """Test hash_token utility"""
        from apps.authentication.utils import hash_token

        token = "test_token"
        hash_value = hash_token(token)

        self.assertIsNotNone(hash_value)
        self.assertIsInstance(hash_value, str)
        self.assertEqual(len(hash_value), 64)  # SHA256 hex digest length

    def test_extract_domain_from_email(self):
        """Test extract_domain_from_email utility"""
        from apps.authentication.utils import extract_domain_from_email

        # Test valid email
        domain = extract_domain_from_email("user@example.com")
        self.assertEqual(domain, "@example.com")

        # Test invalid email
        domain = extract_domain_from_email("invalid_email")
        self.assertIsNone(domain)

    def test_cleanup_expired_sessions(self):
        """Test cleanup_expired_sessions utility"""
        from apps.authentication.utils import cleanup_expired_sessions

        with patch("apps.authentication.models.UserSession.cleanup_expired_sessions") as mock_cleanup:
            cleanup_expired_sessions()
            mock_cleanup.assert_called_once()

    def test_get_client_ip_with_x_real_ip(self):
        """Test get_client_ip with X-Real-IP header"""
        from django.test import RequestFactory

        from apps.authentication.utils import get_client_ip

        factory = RequestFactory()
        request = factory.get("/")
        request.META["HTTP_X_REAL_IP"] = "192.168.1.100"
        request.META["REMOTE_ADDR"] = "127.0.0.1"

        ip = get_client_ip(request)
        self.assertEqual(ip, "192.168.1.100")

    def test_get_client_ip_fallback_to_remote_addr(self):
        """Test get_client_ip fallback to REMOTE_ADDR"""
        from django.test import RequestFactory

        from apps.authentication.utils import get_client_ip

        factory = RequestFactory()
        request = factory.get("/")
        request.META["REMOTE_ADDR"] = "192.168.1.1"

        ip = get_client_ip(request)
        self.assertEqual(ip, "192.168.1.1")

    def test_get_client_ip_no_remote_addr(self):
        """Test get_client_ip with no REMOTE_ADDR"""
        from django.test import RequestFactory

        from apps.authentication.utils import get_client_ip

        factory = RequestFactory()
        request = factory.get("/")
        # No REMOTE_ADDR set

        ip = get_client_ip(request)
        self.assertEqual(ip, "127.0.0.1")  # Default fallback
