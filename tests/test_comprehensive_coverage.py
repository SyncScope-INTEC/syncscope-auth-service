"""
Comprehensive tests designed to achieve 80%+ coverage by testing actual code execution paths
"""

import os
import sys
from io import StringIO
from unittest.mock import MagicMock, call, patch

from django.core.management import call_command
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient


class TestManagementCommandsExecution(TestCase):
    """Test management commands with actual execution paths"""

    def setUp(self):
        self.out = StringIO()
        self.err = StringIO()

    def test_check_db_health_command_execution(self):
        """Test check_db_health command actual execution"""
        # Mock the health check to return healthy
        with patch("config.database_retry.DatabaseHealthCheck.is_healthy", return_value=True):
            try:
                call_command("check_db_health", stdout=self.out, stderr=self.err)
            except SystemExit as e:
                # Command calls sys.exit(0) on success
                self.assertEqual(e.code, 0)
                output = self.out.getvalue()
                self.assertIn("Database is healthy", output)
            else:
                self.fail("Expected SystemExit to be raised")

    def test_setup_ci_db_command_execution(self):
        """Test setup_ci_db command actual execution"""
        with patch("django.db.connection.cursor") as mock_cursor:
            mock_cursor_obj = MagicMock()
            mock_cursor.return_value.__enter__.return_value = mock_cursor_obj
            mock_cursor_obj.fetchone.return_value = (1,)
            mock_cursor_obj.fetchall.return_value = [
                ("authentication_user",),
                ("authentication_usersession",),
                ("authentication_company",),
            ]

            with patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}):
                call_command("setup_ci_db", "--force-public-schema", stdout=self.out, stderr=self.err)

            output = self.out.getvalue()
            self.assertIn("CI environment detected", output)
            self.assertIn("Database setup completed", output)

    def test_cleanup_sessions_command_with_mocked_sessions(self):
        """Test cleanup_sessions command with mocked session objects"""
        # Mock the UserSession queryset behavior
        with patch("apps.authentication.models.UserSession.objects.filter") as mock_filter:
            with patch("apps.authentication.models.UserSession.cleanup_expired_sessions") as mock_cleanup:
                mock_queryset = MagicMock()
                mock_queryset.count.return_value = 2
                mock_filter.return_value = mock_queryset
                mock_cleanup.return_value = 2

                call_command("cleanup_sessions", stdout=self.out, stderr=self.err)

                output = self.out.getvalue()
                self.assertIn("Successfully cleaned up 2 expired sessions", output)
                mock_cleanup.assert_called_once()


class TestSerializersWithRealValidation(TestCase):
    """Test serializers with real validation logic"""

    def test_user_login_serializer_real_validation(self):
        """Test UserLoginSerializer with real validation paths"""
        from apps.authentication.serializers import UserLoginSerializer

        # Test empty email/password validation (triggers field-level validation)
        serializer = UserLoginSerializer(data={"email": "", "password": ""})
        self.assertFalse(serializer.is_valid())
        self.assertIn("blank", str(serializer.errors))

        # Test missing email/password validation (triggers serializer-level validation)
        serializer2 = UserLoginSerializer(data={})
        self.assertFalse(serializer2.is_valid())
        # When both are missing, it should trigger the custom validation

        # Test with valid format but missing password
        serializer3 = UserLoginSerializer(data={"email": "test@example.com"})
        self.assertFalse(serializer3.is_valid())

    def test_password_change_serializer_validation_paths(self):
        """Test PasswordChangeSerializer validation with different paths"""
        from rest_framework.serializers import ValidationError

        from apps.authentication.serializers import PasswordChangeSerializer

        # Test password mismatch
        mock_request = MagicMock()
        mock_user = MagicMock()
        mock_user.check_password.return_value = True
        mock_request.user = mock_user

        data = {"old_password": "oldpass123", "new_password": "newpass123", "new_password_confirm": "different123"}

        serializer = PasswordChangeSerializer(data=data, context={"request": mock_request})
        self.assertFalse(serializer.is_valid())
        self.assertIn("New passwords don't match", str(serializer.errors))

        # Test incorrect old password
        mock_user.check_password.return_value = False
        serializer2 = PasswordChangeSerializer(context={"request": mock_request})

        with self.assertRaises(ValidationError):
            serializer2.validate_old_password("wrongpass")

    def test_user_registration_serializer_validation(self):
        """Test UserRegistrationSerializer validation paths"""
        from apps.authentication.serializers import UserRegistrationSerializer

        # Test password mismatch with strong passwords to avoid Django validation
        data = {
            "email": "test@example.com",
            "first_name": "Test",
            "last_name": "User",
            "password": "VeryStrong123Pass!@#",
            "password_confirm": "DifferentStrong123Pass!@#",
        }

        serializer = UserRegistrationSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("Passwords don't match", str(serializer.errors))

    def test_company_serializer_domain_validation(self):
        """Test CompanySerializer domain validation logic"""
        from apps.authentication.serializers import CompanySerializer

        # Test domain without @ - should add @
        data = {"name": "Test Company", "domain": "example.com"}
        serializer = CompanySerializer(data=data)
        if serializer.is_valid():
            self.assertEqual(serializer.validated_data["domain"], "@example.com")

        # Test domain with @ - should keep @
        data2 = {"name": "Test Company", "domain": "@example.com"}
        serializer2 = CompanySerializer(data=data2)
        if serializer2.is_valid():
            self.assertEqual(serializer2.validated_data["domain"], "@example.com")


class TestViewsRealExecution(TestCase):
    """Test views with real execution paths"""

    def test_api_home_view_template_fallback(self):
        """Test api_home view template fallback mechanism"""
        from apps.authentication.views import api_home

        factory = RequestFactory()
        request = factory.get("/api/")

        # Mock template loading to fail, triggering fallback
        with patch("apps.authentication.views.loader.get_template") as mock_template:
            mock_template.side_effect = Exception("Template not found")

            response = api_home(request)

            # Should return JSON response as fallback
            self.assertEqual(response.status_code, 200)
            self.assertIn("main_routes", response.data)
            self.assertIn("service_info", response.data)

    def test_logout_view_token_error_handling(self):
        """Test LogoutView TokenError exception handling"""
        from rest_framework_simplejwt.exceptions import TokenError

        client = APIClient()

        # Mock authenticated user
        with patch("django.contrib.auth.get_user_model") as mock_get_user_model:
            mock_user_class = MagicMock()
            mock_user = MagicMock()
            mock_user.id = 1
            mock_user_class.objects.create_user.return_value = mock_user
            mock_get_user_model.return_value = mock_user_class

            client.force_authenticate(user=mock_user)

            # Mock RefreshToken to raise TokenError
            with patch("apps.authentication.views.RefreshToken") as mock_refresh_token:
                mock_refresh_token.side_effect = TokenError("Invalid token")

                response = client.post("/api/auth/logout/", {"refresh_token": "invalid"})

                # Should handle TokenError gracefully
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.data["message"], "Logout completed")


class TestDatabaseConfigRealPaths(TestCase):
    """Test database configuration with real execution paths"""

    @patch("config.database.dj_database_url.parse")
    def test_get_database_config_with_database_url(self, mock_parse):
        """Test get_database_config with DATABASE_URL"""
        mock_parse.return_value = {"ENGINE": "django.db.backends.postgresql", "NAME": "testdb"}

        with patch.dict(os.environ, {"DATABASE_URL": "postgres://user:pass@localhost/testdb"}):
            from config.database import get_database_config

            config = get_database_config()

            self.assertIn("OPTIONS", config)
            self.assertEqual(config["OPTIONS"]["options"], "-c search_path=auth")
            mock_parse.assert_called_once_with("postgres://user:pass@localhost/testdb")

    @patch("config.database.config")
    def test_get_database_config_fallback(self, mock_config):
        """Test get_database_config fallback to environment variables"""
        # Mock environment variable lookup
        mock_config.side_effect = lambda key, default=None, cast=None: {
            "DB_NAME": "fallback_db",
            "DB_USER": "fallback_user",
            "DB_PASSWORD": "fallback_pass",
            "DB_HOST": "fallback_host",
            "DB_PORT": 5432,
        }.get(key, default)

        with patch.dict(os.environ, {}, clear=True):
            from config.database import get_database_config

            config = get_database_config()

            self.assertEqual(config["ENGINE"], "django.db.backends.postgresql")
            self.assertEqual(config["NAME"], "fallback_db")
            self.assertEqual(config["USER"], "fallback_user")
            self.assertEqual(config["OPTIONS"]["options"], "-c search_path=auth")

    @patch("builtins.print")
    @patch("psycopg2.connect")
    @patch("django.conf.settings")
    def test_create_auth_schema_success(self, mock_settings, mock_connect, mock_print):
        """Test create_auth_schema_if_not_exists success path"""
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
        """Test create_auth_schema_if_not_exists failure path"""
        mock_connect.side_effect = Exception("Connection failed")

        mock_settings.DATABASES = {
            "default": {"HOST": "localhost", "PORT": "5432", "USER": "user", "PASSWORD": "pass", "NAME": "testdb"}
        }

        from config.database import create_auth_schema_if_not_exists

        create_auth_schema_if_not_exists()

        mock_print.assert_any_call("Warning: Could not create auth schema: Connection failed")


class TestServerlessConfigExecution(TestCase):
    """Test serverless configuration with real execution"""

    def test_setup_serverless_environment(self):
        """Test setup_serverless_environment execution"""
        with patch("config.serverless.configure_connection_pool") as mock_configure:
            with patch("config.serverless.settings") as mock_settings:
                with patch("config.serverless.logger") as mock_logger:
                    # Set up mock settings
                    mock_settings.REST_FRAMEWORK = {}
                    mock_settings.SIMPLE_JWT = {}
                    mock_settings.INSTALLED_APPS = ["debug_toolbar", "other_app"]
                    mock_settings.DEBUG = False
                    mock_settings.LOGGING = {"handlers": {"console": {}}}

                    from config.serverless import setup_serverless_environment

                    setup_serverless_environment()

                    # Verify configuration was applied
                    self.assertEqual(mock_settings.REST_FRAMEWORK["DEFAULT_TIMEOUT"], 30)
                    self.assertEqual(mock_settings.INSTALLED_APPS, ["other_app"])
                    mock_configure.assert_called_once()
                    mock_logger.info.assert_called_with("✓ Serverless environment configured")

    def test_validate_serverless_config_valid(self):
        """Test validate_serverless_config with valid configuration"""
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
        """Test validate_serverless_config with invalid configuration"""
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
                self.assertGreater(len(issues), 0)
                self.assertIn("CONN_MAX_AGE should be 0", " ".join(issues))


class TestUtilityFunctionsExecution(TestCase):
    """Test utility functions with real execution"""

    def test_get_client_ip_with_forwarded_for(self):
        """Test get_client_ip with X-Forwarded-For header"""
        from apps.authentication.utils import get_client_ip

        factory = RequestFactory()
        request = factory.get("/")
        request.META["HTTP_X_FORWARDED_FOR"] = "10.0.0.1, 192.168.1.1"
        request.META["REMOTE_ADDR"] = "192.168.1.1"

        ip = get_client_ip(request)
        self.assertEqual(ip, "10.0.0.1")

    def test_get_client_ip_without_forwarded_for(self):
        """Test get_client_ip without X-Forwarded-For header"""
        from apps.authentication.utils import get_client_ip

        factory = RequestFactory()
        request = factory.get("/")
        request.META["REMOTE_ADDR"] = "127.0.0.1"

        ip = get_client_ip(request)
        self.assertEqual(ip, "127.0.0.1")


class TestDatabaseRetryDecorator(TestCase):
    """Test database retry decorator execution"""

    def test_database_retry_success(self):
        """Test database_retry decorator with successful execution"""
        from config.database_retry import database_retry

        @database_retry(max_retries=2)
        def successful_function():
            return "success"

        result = successful_function()
        self.assertEqual(result, "success")

    def test_database_retry_with_failures_then_success(self):
        """Test database_retry decorator with failures then success"""
        from config.database_retry import database_retry

        call_count = 0

        @database_retry(max_retries=3)
        def flaky_function():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("Temporary failure")
            return "success"

        with patch("config.database_retry.logger") as mock_logger:
            result = flaky_function()

        self.assertEqual(result, "success")
        self.assertEqual(call_count, 3)
        # Should have logged warnings for retries
        self.assertTrue(mock_logger.warning.called)

    def test_database_retry_max_retries_exceeded(self):
        """Test database_retry decorator when max retries exceeded"""
        from config.database_retry import database_retry

        @database_retry(max_retries=2)
        def always_failing_function():
            raise Exception("Always fails")

        with patch("config.database_retry.logger") as mock_logger:
            with self.assertRaises(Exception):
                always_failing_function()

        # Should have logged warnings for retries
        self.assertTrue(mock_logger.warning.called)


class TestManageDbScriptExecution(TestCase):
    """Test manage_db.py script execution paths"""

    @patch("manage_db.setup_django")
    @patch("config.database.create_auth_schema_if_not_exists")
    @patch("builtins.print")
    def test_create_auth_schema_function(self, mock_print, mock_create_schema, mock_setup):
        """Test create_auth_schema function execution"""
        from manage_db import create_auth_schema

        result = create_auth_schema()

        mock_setup.assert_called_once()
        mock_create_schema.assert_called_once()
        self.assertTrue(result)

    @patch("manage_db.execute_from_command_line")
    @patch("builtins.print")
    def test_run_migrations_function(self, mock_print, mock_execute):
        """Test run_migrations function execution"""
        from manage_db import run_migrations

        result = run_migrations()

        self.assertTrue(result)
        # Should call migrate twice (makemigrations and migrate)
        self.assertEqual(mock_execute.call_count, 2)

    @patch("manage_db.execute_from_command_line")
    @patch("builtins.print")
    def test_create_superuser_function(self, mock_print, mock_execute):
        """Test create_superuser function execution"""
        from manage_db import create_superuser

        result = create_superuser()

        self.assertTrue(result)
        mock_execute.assert_called_once()

    def test_main_function_no_args(self):
        """Test main function with no arguments"""
        original_argv = sys.argv[:]
        sys.argv = ["manage_db.py"]

        try:
            with patch("builtins.print") as mock_print:
                from manage_db import main

                main()

                # Should print usage information
                self.assertTrue(mock_print.called)
                usage_printed = any("Usage:" in str(call) for call in mock_print.call_args_list)
                self.assertTrue(usage_printed)
        finally:
            sys.argv = original_argv

    @patch("manage_db.create_auth_schema")
    def test_main_function_schema_command(self, mock_create_schema):
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
    def test_main_function_migrate_command(self, mock_migrate):
        """Test main function with migrate command"""
        original_argv = sys.argv[:]
        sys.argv = ["manage_db.py", "migrate"]

        try:
            from manage_db import main

            main()

            mock_migrate.assert_called_once()
        finally:
            sys.argv = original_argv
