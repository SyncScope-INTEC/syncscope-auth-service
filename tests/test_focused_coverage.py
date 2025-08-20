"""
Focused tests to achieve 80%+ coverage by targeting specific uncovered code
"""

import os
import sys
from io import StringIO
from unittest.mock import MagicMock, call, patch

from django.test import TestCase, override_settings


class TestConfigFilesCoverage(TestCase):
    """Test config files to improve coverage"""

    def test_asgi_import_and_setup(self):
        """Test ASGI module import and setup"""
        # Import and test the module
        import config.asgi

        self.assertTrue(hasattr(config.asgi, "application"))

        # Test Django setup is called
        with patch("django.setup") as mock_setup:
            with patch.dict(os.environ, {}, clear=True):
                import importlib

                importlib.reload(config.asgi)
                # Module should set DJANGO_SETTINGS_MODULE
                self.assertEqual(os.environ.get("DJANGO_SETTINGS_MODULE"), "config.settings")

    def test_wsgi_import_and_setup(self):
        """Test WSGI module import and setup"""
        # Import and test the module
        import config.wsgi

        self.assertTrue(hasattr(config.wsgi, "application"))

        # Test Django setup behavior
        with patch("django.setup") as mock_setup:
            with patch.dict(os.environ, {}, clear=True):
                import importlib

                importlib.reload(config.wsgi)
                # Module should set DJANGO_SETTINGS_MODULE
                self.assertEqual(os.environ.get("DJANGO_SETTINGS_MODULE"), "config.settings")

    @patch("config.database.dj_database_url.parse")
    def test_database_config_with_url(self, mock_parse):
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
    def test_database_config_without_url(self, mock_config):
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

    def test_serverless_setup_environment(self):
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
                    mock_logger.info.assert_called_with("✓ Serverless environment configured")

    def test_serverless_validate_config_valid(self):
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

    def test_serverless_validate_config_invalid(self):
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

    def test_serverless_get_metrics(self):
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

    def test_serverless_get_metrics_cache_failure(self):
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
        """Test serverless auto-configuration"""
        # Remove module if already imported
        if "config.serverless" in sys.modules:
            del sys.modules["config.serverless"]

        with patch.dict(os.environ, {"SERVERLESS_ENV": "true"}):
            with patch("config.serverless.setup_serverless_environment") as mock_setup:
                import config.serverless

                mock_setup.assert_called_once()


class TestManageDbCoverage(TestCase):
    """Test manage_db.py for coverage"""

    @patch("manage_db.os.environ.setdefault")
    @patch("manage_db.django.setup")
    def test_setup_django(self, mock_django_setup, mock_setdefault):
        """Test setup_django function"""
        from manage_db import setup_django

        setup_django()

        mock_setdefault.assert_called_once_with("DJANGO_SETTINGS_MODULE", "config.settings")
        mock_django_setup.assert_called_once()

    @patch("manage_db.setup_django")
    @patch("config.database.create_auth_schema_if_not_exists")
    @patch("builtins.print")
    def test_create_auth_schema(self, mock_print, mock_create_schema, mock_setup):
        """Test create_auth_schema function"""
        from manage_db import create_auth_schema

        result = create_auth_schema()

        mock_setup.assert_called_once()
        mock_create_schema.assert_called_once()
        self.assertTrue(result)
        mock_print.assert_called_with("✓ Auth schema setup completed")

    @patch("manage_db.setup_django")
    @patch("config.database.create_auth_schema_if_not_exists")
    @patch("builtins.print")
    def test_create_auth_schema_failure(self, mock_print, mock_create_schema, mock_setup):
        """Test create_auth_schema function with failure"""
        mock_create_schema.side_effect = Exception("Schema creation failed")

        from manage_db import create_auth_schema

        result = create_auth_schema()

        self.assertFalse(result)
        mock_print.assert_any_call("❌ Failed to create auth schema: Schema creation failed")

    @patch("manage_db.setup_django")
    @patch("manage_db.execute_from_command_line")
    @patch("builtins.print")
    def test_run_migrations(self, mock_print, mock_execute, mock_setup):
        """Test run_migrations function"""
        from manage_db import run_migrations

        result = run_migrations()

        mock_setup.assert_called_once()
        self.assertTrue(result)
        # Should call execute_from_command_line twice
        self.assertEqual(mock_execute.call_count, 2)

    @patch("manage_db.setup_django")
    @patch("manage_db.execute_from_command_line")
    @patch("builtins.print")
    def test_run_migrations_failure(self, mock_print, mock_execute, mock_setup):
        """Test run_migrations function with failure"""
        mock_execute.side_effect = Exception("Migration failed")

        from manage_db import run_migrations

        result = run_migrations()

        self.assertFalse(result)
        mock_print.assert_any_call("❌ Failed to run migrations: Migration failed")

    @patch("manage_db.setup_django")
    @patch("manage_db.execute_from_command_line")
    @patch("builtins.print")
    def test_create_superuser(self, mock_print, mock_execute, mock_setup):
        """Test create_superuser function"""
        from manage_db import create_superuser

        result = create_superuser()

        mock_setup.assert_called_once()
        self.assertTrue(result)
        mock_execute.assert_called_once()

    @patch("manage_db.setup_django")
    @patch("manage_db.execute_from_command_line")
    @patch("builtins.print")
    def test_create_superuser_failure(self, mock_print, mock_execute, mock_setup):
        """Test create_superuser function with failure"""
        mock_execute.side_effect = Exception("Superuser creation failed")

        from manage_db import create_superuser

        result = create_superuser()

        self.assertFalse(result)
        mock_print.assert_any_call("❌ Failed to create superuser: Superuser creation failed")

    def test_main_no_args(self):
        """Test main function with no arguments"""
        original_argv = sys.argv[:]
        sys.argv = ["manage_db.py"]

        try:
            with patch("builtins.print") as mock_print:
                from manage_db import main

                main()

                # Should print usage
                self.assertTrue(mock_print.called)
                usage_calls = [call for call in mock_print.call_args_list if "Usage:" in str(call)]
                self.assertTrue(len(usage_calls) > 0)
        finally:
            sys.argv = original_argv

    @patch("manage_db.create_auth_schema")
    def test_main_schema_command(self, mock_create_schema):
        """Test main function with schema command"""
        original_argv = sys.argv[:]
        sys.argv = ["manage_db.py", "schema"]

        try:
            from manage_db import main

            main()

            mock_create_schema.assert_called_once()
        finally:
            sys.argv = original_argv

    @patch("manage_db.run_migrations")
    def test_main_migrate_command(self, mock_migrate):
        """Test main function with migrate command"""
        original_argv = sys.argv[:]
        sys.argv = ["manage_db.py", "migrate"]

        try:
            from manage_db import main

            main()

            mock_migrate.assert_called_once()
        finally:
            sys.argv = original_argv

    @patch("manage_db.create_superuser")
    def test_main_superuser_command(self, mock_superuser):
        """Test main function with superuser command"""
        original_argv = sys.argv[:]
        sys.argv = ["manage_db.py", "superuser"]

        try:
            from manage_db import main

            main()

            mock_superuser.assert_called_once()
        finally:
            sys.argv = original_argv

    @patch("manage_db.create_auth_schema")
    @patch("manage_db.run_migrations")
    @patch("manage_db.create_superuser")
    def test_main_all_command(self, mock_superuser, mock_migrate, mock_schema):
        """Test main function with all command"""
        original_argv = sys.argv[:]
        sys.argv = ["manage_db.py", "all"]

        try:
            from manage_db import main

            main()

            mock_schema.assert_called_once()
            mock_migrate.assert_called_once()
            mock_superuser.assert_called_once()
        finally:
            sys.argv = original_argv


class TestUtilsCoverage(TestCase):
    """Test utility functions for coverage"""

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


class TestDatabaseRetryCoverage(TestCase):
    """Test database retry decorator for coverage"""

    def test_database_retry_success(self):
        """Test database_retry decorator success path"""
        from config.database_retry import database_retry

        @database_retry(max_retries=2)
        def successful_function():
            return "success"

        result = successful_function()
        self.assertEqual(result, "success")

    def test_database_retry_failure_then_success(self):
        """Test database_retry with failure then success"""
        from config.database_retry import database_retry

        call_count = 0

        @database_retry(max_retries=3)
        def flaky_function():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise Exception("Temporary failure")
            return "success"

        with patch("config.database_retry.logger") as mock_logger:
            with patch("time.sleep"):  # Mock sleep to speed up test
                result = flaky_function()

        self.assertEqual(result, "success")
        self.assertEqual(call_count, 2)

    def test_database_retry_max_retries_exceeded(self):
        """Test database_retry when max retries exceeded"""
        from config.database_retry import database_retry

        @database_retry(max_retries=2)
        def always_failing_function():
            raise Exception("Always fails")

        with patch("config.database_retry.logger") as mock_logger:
            with patch("time.sleep"):  # Mock sleep to speed up test
                with self.assertRaises(Exception):
                    always_failing_function()
