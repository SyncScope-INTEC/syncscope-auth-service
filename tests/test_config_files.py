"""
Tests for config files with 0% coverage
"""

import os
from unittest.mock import MagicMock, patch

import pytest
from django.test import TestCase, override_settings


class TestASGIConfig(TestCase):
    """Test cases for config/asgi.py"""

    def test_asgi_application_import(self):
        """Test that ASGI application can be imported"""
        from config.asgi import application

        self.assertIsNotNone(application)

    @patch.dict(os.environ, {"DJANGO_SETTINGS_MODULE": "config.settings"})
    def test_asgi_django_settings_module(self):
        """Test that DJANGO_SETTINGS_MODULE is set correctly"""
        # Re-import to test the setdefault behavior
        import importlib

        from config import asgi

        importlib.reload(asgi)
        self.assertEqual(os.environ.get("DJANGO_SETTINGS_MODULE"), "config.settings")


class TestWSGIConfig(TestCase):
    """Test cases for config/wsgi.py"""

    def test_wsgi_application_import(self):
        """Test that WSGI application can be imported"""
        from config.wsgi import application

        self.assertIsNotNone(application)

    @patch.dict(os.environ, {"DJANGO_SETTINGS_MODULE": "config.settings"})
    def test_wsgi_django_settings_module(self):
        """Test that DJANGO_SETTINGS_MODULE is set correctly"""
        # Re-import to test the setdefault behavior
        import importlib

        from config import wsgi

        importlib.reload(wsgi)
        self.assertEqual(os.environ.get("DJANGO_SETTINGS_MODULE"), "config.settings")


class TestDatabaseConfig(TestCase):
    """Test cases for config/database.py"""

    @patch.dict(os.environ, {"DATABASE_URL": "postgres://user:pass@localhost:5432/testdb"})
    @patch("config.database.dj_database_url.parse")
    def test_get_database_config_with_database_url(self, mock_parse):
        """Test get_database_config with DATABASE_URL environment variable"""
        mock_parse.return_value = {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": "testdb",
            "USER": "user",
            "PASSWORD": "pass",
            "HOST": "localhost",
            "PORT": "5432",
        }

        from config.database import get_database_config

        config = get_database_config()

        self.assertIn("OPTIONS", config)
        self.assertEqual(config["OPTIONS"]["options"], "-c search_path=auth")
        mock_parse.assert_called_once_with("postgres://user:pass@localhost:5432/testdb")

    @patch.dict(os.environ, {}, clear=True)
    @patch("config.database.config")
    def test_get_database_config_without_database_url(self, mock_config):
        """Test get_database_config without DATABASE_URL (fallback)"""
        mock_config.side_effect = lambda key, default=None, cast=None: {
            "DB_NAME": "test_db",
            "DB_USER": "test_user",
            "DB_PASSWORD": "test_pass",
            "DB_HOST": "localhost",
            "DB_PORT": 5432,
        }.get(key, default)

        from config.database import get_database_config

        config = get_database_config()

        self.assertEqual(config["ENGINE"], "django.db.backends.postgresql")
        self.assertEqual(config["NAME"], "test_db")
        self.assertEqual(config["USER"], "test_user")
        self.assertEqual(config["PASSWORD"], "test_pass")
        self.assertEqual(config["HOST"], "localhost")
        self.assertEqual(config["PORT"], 5432)
        self.assertEqual(config["OPTIONS"]["options"], "-c search_path=auth")

    @patch("builtins.print")
    @patch("django.conf.settings")
    @patch("psycopg2.connect")
    def test_create_auth_schema_if_not_exists_success(self, mock_connect, mock_settings, mock_print):
        """Test successful auth schema creation"""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor

        mock_settings.DATABASES = {
            "default": {"HOST": "localhost", "PORT": "5432", "USER": "user", "PASSWORD": "pass", "NAME": "testdb"}
        }

        from config.database import create_auth_schema_if_not_exists

        create_auth_schema_if_not_exists()

        mock_connect.assert_called_once_with(host="localhost", port="5432", user="user", password="pass", database="testdb")
        mock_cursor.execute.assert_called_once_with("CREATE SCHEMA IF NOT EXISTS auth;")
        mock_print.assert_called_with("✓ Auth schema created or already exists")

    @patch("builtins.print")
    @patch("django.conf.settings")
    @patch("psycopg2.connect")
    def test_create_auth_schema_if_not_exists_failure(self, mock_connect, mock_settings, mock_print):
        """Test auth schema creation failure"""
        mock_connect.side_effect = Exception("Connection failed")

        mock_settings.DATABASES = {
            "default": {"HOST": "localhost", "PORT": "5432", "USER": "user", "PASSWORD": "pass", "NAME": "testdb"}
        }

        from config.database import create_auth_schema_if_not_exists

        create_auth_schema_if_not_exists()

        mock_print.assert_any_call("Warning: Could not create auth schema: Connection failed")
        mock_print.assert_any_call("Make sure to create the 'auth' schema manually in your PostgreSQL database")


class TestServerlessConfig(TestCase):
    """Test cases for config/serverless.py"""

    def test_setup_serverless_environment(self):
        """Test serverless environment setup"""
        with patch("config.serverless.configure_connection_pool") as mock_configure_pool:
            with patch("config.serverless.settings") as mock_settings:
                with patch("config.serverless.logger") as mock_logger:
                    # Set up mock settings attributes
                    mock_settings.REST_FRAMEWORK = {}
                    mock_settings.SIMPLE_JWT = {}
                    mock_settings.INSTALLED_APPS = ["debug_toolbar", "other_app"]
                    mock_settings.DEBUG = False
                    mock_settings.LOGGING = {"handlers": {"console": {}}}

                    from config.serverless import setup_serverless_environment

                    setup_serverless_environment()

                    # Verify configuration updates
                    self.assertEqual(mock_settings.REST_FRAMEWORK["DEFAULT_TIMEOUT"], 30)
                    self.assertEqual(mock_settings.INSTALLED_APPS, ["other_app"])
                    mock_configure_pool.assert_called_once()
                    mock_logger.info.assert_called_with("✓ Serverless environment configured")

    def test_validate_serverless_config_valid(self):
        """Test serverless configuration validation - valid config"""
        with patch("config.serverless.settings") as mock_settings:
            with patch("config.serverless.logger") as mock_logger:
                mock_settings.DATABASES = {"default": {"CONN_MAX_AGE": 0}}
                mock_settings.CACHES = {"default": {"LOCATION": "redis://localhost:6379"}}
                mock_settings.SECRET_KEY = "valid-secret-key"
                mock_settings.DEBUG = False

                from config.serverless import validate_serverless_config

                with patch.dict(os.environ, {"RAILWAY_ENVIRONMENT": "development"}):
                    is_valid, issues = validate_serverless_config()

                self.assertTrue(is_valid)
                self.assertEqual(issues, [])
                mock_logger.info.assert_called_with("✓ Serverless configuration validated")

    def test_validate_serverless_config_invalid(self):
        """Test serverless configuration validation - invalid config"""
        with patch("config.serverless.settings") as mock_settings:
            with patch("config.serverless.logger") as mock_logger:
                mock_settings.DATABASES = {"default": {"CONN_MAX_AGE": 300}}
                mock_settings.CACHES = {"default": {"LOCATION": "locmem://default"}}
                mock_settings.SECRET_KEY = "django-insecure-change-me-in-production"
                mock_settings.DEBUG = True

                from config.serverless import validate_serverless_config

                with patch.dict(os.environ, {"RAILWAY_ENVIRONMENT": "production"}):
                    is_valid, issues = validate_serverless_config()

                self.assertFalse(is_valid)
                self.assertEqual(len(issues), 4)
                self.assertIn("CONN_MAX_AGE should be 0 for serverless", issues)
                self.assertIn("Redis cache is recommended for serverless", issues)
                self.assertIn("SECRET_KEY should be changed for production", issues)
                self.assertIn("DEBUG should be False in production", issues)

    @patch("django.core.cache.cache")
    @patch("django.db.connection")
    def test_get_serverless_metrics(self, mock_connection, mock_cache):
        """Test serverless metrics collection"""
        mock_connection.queries = ["query1", "query2"]
        mock_connection.vendor = "postgresql"
        mock_cache.set.return_value = None
        mock_cache.get.return_value = "value"

        from config.serverless import get_serverless_metrics

        with patch("time.time", side_effect=[1000.0, 1000.1]):  # 100ms latency
            metrics = get_serverless_metrics()

        self.assertEqual(metrics["database_queries"], 2)
        self.assertEqual(metrics["database_vendor"], "postgresql")
        self.assertEqual(metrics["cache_latency_ms"], 100.0)

    @patch("django.core.cache.cache")
    @patch("django.db.connection")
    def test_get_serverless_metrics_cache_failure(self, mock_connection, mock_cache):
        """Test serverless metrics collection with cache failure"""
        mock_connection.queries = []
        mock_connection.vendor = "postgresql"
        mock_cache.set.side_effect = Exception("Cache unavailable")

        from config.serverless import get_serverless_metrics

        metrics = get_serverless_metrics()

        self.assertEqual(metrics["database_queries"], 0)
        self.assertEqual(metrics["database_vendor"], "postgresql")
        self.assertIsNone(metrics["cache_latency_ms"])

    def test_auto_configure_on_import(self):
        """Test that serverless environment is auto-configured on import"""
        # Remove the module if it's already imported
        import sys

        if "config.serverless" in sys.modules:
            del sys.modules["config.serverless"]

        with patch.dict(os.environ, {"SERVERLESS_ENV": "true"}):
            with patch("config.serverless.setup_serverless_environment") as mock_setup:
                # Import the module which should trigger auto-configuration
                import config.serverless

                mock_setup.assert_called_once()

    @patch.dict(os.environ, {"SERVERLESS_ENV": "false"})
    @patch("config.serverless.setup_serverless_environment")
    def test_no_auto_configure_when_disabled(self, mock_setup):
        """Test that serverless environment is not auto-configured when disabled"""
        # Re-import the module
        import importlib

        import config.serverless

        importlib.reload(config.serverless)

        mock_setup.assert_not_called()
