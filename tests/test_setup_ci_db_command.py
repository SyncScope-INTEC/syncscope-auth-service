"""
Tests for setup_ci_db management command
"""

import os
from io import StringIO
from unittest.mock import MagicMock, Mock, patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import TestCase, override_settings

from apps.authentication.management.commands.setup_ci_db import Command


class TestSetupCiDbCommand(TestCase):
    """Test cases for setup_ci_db management command"""

    def setUp(self):
        """Set up test environment"""
        self.out = StringIO()
        self.err = StringIO()
        self.command = Command()
        self.command.stdout = self.out
        self.command.stderr = self.err

    def call_command_with_output(self, *args, **kwargs):
        """Helper to call command and capture output"""
        kwargs.update({"stdout": self.out, "stderr": self.err})
        call_command("setup_ci_db", *args, **kwargs)
        return self.out.getvalue(), self.err.getvalue()

    @override_settings(
        DATABASES={
            "default": {
                "ENGINE": "django.db.backends.postgresql",
                "NAME": "test_db",
                "HOST": "localhost",
                "PORT": "5432",
                "USER": "test_user",
                "OPTIONS": {"options": "-c search_path=auth"},
            }
        }
    )
    def test_show_database_config_with_auth_schema(self):
        """Test showing database configuration with auth schema"""
        stdout, _ = self.call_command_with_output()

        self.assertIn("Current database configuration:", stdout)
        self.assertIn("Engine: django.db.backends.postgresql", stdout)
        self.assertIn("Name: test_db", stdout)
        self.assertIn("Host: localhost", stdout)
        self.assertIn("Port: 5432", stdout)
        self.assertIn("User: test_user", stdout)
        self.assertIn("PostgreSQL options: -c search_path=auth", stdout)
        self.assertIn("⚠️  Using auth schema", stdout)

    @override_settings(
        DATABASES={
            "default": {
                "ENGINE": "django.db.backends.postgresql",
                "NAME": "test_db",
                "HOST": "localhost",
                "PORT": "5432",
                "USER": "test_user",
                "OPTIONS": {},
            }
        }
    )
    def test_show_database_config_without_options(self):
        """Test showing database configuration without options"""
        stdout, _ = self.call_command_with_output()

        self.assertIn("Current database configuration:", stdout)
        self.assertIn("No PostgreSQL options set", stdout)

    @override_settings(
        DATABASES={
            "default": {
                "ENGINE": "django.db.backends.postgresql",
                "NAME": "test_db",
                "HOST": "localhost",
                "PORT": "5432",
                "USER": "test_user",
                "OPTIONS": {"options": "-c timezone=UTC"},
            }
        }
    )
    def test_show_database_config_with_public_schema(self):
        """Test showing database configuration with public schema"""
        stdout, _ = self.call_command_with_output()

        self.assertIn("PostgreSQL options: -c timezone=UTC", stdout)
        self.assertIn("✓ Using public schema (recommended for CI)", stdout)

    def test_create_auth_schema_success(self):
        """Test successful auth schema creation"""
        with patch("apps.authentication.management.commands.setup_ci_db.connection") as mock_connection:
            mock_cursor = MagicMock()
            mock_connection.cursor.return_value.__enter__.return_value = mock_cursor

            # Mock the database connection check
            mock_cursor.fetchone.return_value = (1,)
            mock_cursor.fetchall.return_value = [("users",), ("user_sessions",), ("companies",)]

            self.command.create_auth_schema()
            output = self.out.getvalue()

            mock_cursor.execute.assert_called_with("CREATE SCHEMA IF NOT EXISTS auth;")
            self.assertIn("Creating auth schema if it does not exist...", output)
            self.assertIn("✓ Auth schema created or already exists", output)

    def test_create_auth_schema_failure(self):
        """Test auth schema creation failure"""
        with patch("apps.authentication.management.commands.setup_ci_db.connection") as mock_connection:
            mock_cursor = MagicMock()
            mock_cursor.execute.side_effect = Exception("Permission denied")
            mock_connection.cursor.return_value.__enter__.return_value = mock_cursor

            self.command.create_auth_schema()
            output = self.out.getvalue()

            self.assertIn("❌ Error creating auth schema: Permission denied", output)
            self.assertIn("⚠️  Continuing without auth schema (using public schema)", output)

    def test_check_database_connection_success(self):
        """Test successful database connection check"""
        with patch("apps.authentication.management.commands.setup_ci_db.connection") as mock_connection:
            mock_cursor = MagicMock()
            mock_cursor.fetchone.return_value = (1,)
            mock_connection.cursor.return_value.__enter__.return_value = mock_cursor

            self.command.check_database_connection()
            output = self.out.getvalue()

            mock_cursor.execute.assert_called_with("SELECT 1")
            self.assertIn("Checking database connection...", output)
            self.assertIn("✓ Database connection successful", output)

    def test_check_database_connection_failure(self):
        """Test database connection failure"""
        with patch("apps.authentication.management.commands.setup_ci_db.connection") as mock_connection:
            mock_cursor = MagicMock()
            mock_cursor.execute.side_effect = Exception("Connection failed")
            mock_connection.cursor.return_value.__enter__.return_value = mock_cursor

            with self.assertRaises(Exception):
                self.command.check_database_connection()

    def test_check_database_connection_unexpected_result(self):
        """Test database connection with unexpected result"""
        with patch("apps.authentication.management.commands.setup_ci_db.connection") as mock_connection:
            mock_cursor = MagicMock()
            mock_cursor.fetchone.return_value = (0,)
            mock_connection.cursor.return_value.__enter__.return_value = mock_cursor

            with self.assertRaises(Exception) as context:
                self.command.check_database_connection()

            self.assertIn("Unexpected result from test query", str(context.exception))

    @patch.dict(os.environ, {"CI": "true"})
    @override_settings(
        DATABASES={
            "default": {
                "ENGINE": "django.db.backends.postgresql",
                "NAME": "test_db",
                "OPTIONS": {"options": "-c search_path=auth"},
            }
        }
    )
    def test_should_use_auth_schema_ci_with_auth_configured(self):
        """Test schema detection in CI with auth schema configured"""
        result = self.command.should_use_auth_schema()
        output = self.out.getvalue()

        self.assertTrue(result)
        self.assertIn("🔍 CI environment detected", output)
        self.assertIn("📋 Auth schema is configured, attempting to use it", output)

    @patch.dict(os.environ, {"CI": "true"})
    @override_settings(
        DATABASES={
            "default": {
                "ENGINE": "django.db.backends.postgresql",
                "NAME": "test_db",
                "OPTIONS": {},
            }
        }
    )
    def test_should_use_auth_schema_ci_with_public_configured(self):
        """Test schema detection in CI with public schema configured"""
        result = self.command.should_use_auth_schema()
        output = self.out.getvalue()

        self.assertFalse(result)
        self.assertIn("🔍 CI environment detected", output)
        self.assertIn("📋 Public schema is configured", output)

    @patch.dict(os.environ, {}, clear=True)
    def test_should_use_auth_schema_local_environment(self):
        """Test schema detection in local environment"""
        result = self.command.should_use_auth_schema()
        output = self.out.getvalue()

        self.assertTrue(result)
        self.assertIn("🏠 Local environment detected", output)

    @patch.dict(os.environ, {"GITHUB_ACTIONS": "true"})
    def test_should_use_auth_schema_github_actions(self):
        """Test CI detection with GitHub Actions"""
        result = self.command.should_use_auth_schema()
        output = self.out.getvalue()

        self.assertIn("🔍 CI environment detected", output)

    @patch.dict(os.environ, {"GITLAB_CI": "true"})
    def test_should_use_auth_schema_gitlab_ci(self):
        """Test CI detection with GitLab CI"""
        result = self.command.should_use_auth_schema()
        output = self.out.getvalue()

        self.assertIn("🔍 CI environment detected", output)

    @patch.dict(os.environ, {"TRAVIS": "true"})
    def test_should_use_auth_schema_travis(self):
        """Test CI detection with Travis CI"""
        result = self.command.should_use_auth_schema()
        output = self.out.getvalue()

        self.assertIn("🔍 CI environment detected", output)

    @patch.dict(os.environ, {"CIRCLECI": "true"})
    def test_should_use_auth_schema_circleci(self):
        """Test CI detection with CircleCI"""
        result = self.command.should_use_auth_schema()
        output = self.out.getvalue()

        self.assertIn("🔍 CI environment detected", output)

    def test_setup_public_schema_ci(self):
        """Test setting up public schema for CI"""
        with patch("apps.authentication.management.commands.setup_ci_db.call_command") as mock_call_command:
            with override_settings(
                DATABASES={
                    "default": {
                        "ENGINE": "django.db.backends.postgresql",
                        "NAME": "test_db",
                        "OPTIONS": {"options": "-c search_path=auth"},
                    }
                }
            ):
                self.command.setup_public_schema_ci()
                output = self.out.getvalue()

                self.assertIn("🔧 Setting up CI to use public schema...", output)
                self.assertIn("✓ Temporarily switched to public schema for CI", output)
                mock_call_command.assert_called_with("migrate", verbosity=1, interactive=False)

    def test_run_migrations_success(self):
        """Test successful migration run"""
        with patch("apps.authentication.management.commands.setup_ci_db.call_command") as mock_call_command:
            self.command.run_migrations()
            output = self.out.getvalue()

            self.assertIn("🔄 Running database migrations...", output)
            self.assertIn("✓ Database migrations completed", output)
            mock_call_command.assert_called_with("migrate", verbosity=1, interactive=False)

    def test_run_migrations_failure(self):
        """Test migration failure"""
        with patch("apps.authentication.management.commands.setup_ci_db.call_command") as mock_call_command:
            mock_call_command.side_effect = Exception("Migration failed")

            with self.assertRaises(Exception):
                self.command.run_migrations()

    def test_verify_required_tables_all_exist(self):
        """Test verification when all required tables exist"""
        with patch("apps.authentication.management.commands.setup_ci_db.connection") as mock_connection:
            mock_cursor = MagicMock()
            mock_cursor.fetchall.return_value = [("users",), ("user_sessions",), ("companies",), ("other_table",)]
            mock_connection.cursor.return_value.__enter__.return_value = mock_cursor

            self.command.verify_required_tables()
            output = self.out.getvalue()

            self.assertIn("🔍 Verifying required tables exist...", output)
            self.assertIn("📋 Found 4 tables in current schema", output)
            self.assertIn("✓ users", output)
            self.assertIn("✓ user_sessions", output)
            self.assertIn("✓ companies", output)
            self.assertIn("✅ All required tables found", output)

    def test_verify_required_tables_some_missing(self):
        """Test verification when some required tables are missing"""
        with patch("apps.authentication.management.commands.setup_ci_db.connection") as mock_connection:
            mock_cursor = MagicMock()
            mock_cursor.fetchall.return_value = [("users",), ("other_table",)]
            mock_connection.cursor.return_value.__enter__.return_value = mock_cursor

            self.command.verify_required_tables()
            output = self.out.getvalue()

            self.assertIn("🔍 Verifying required tables exist...", output)
            self.assertIn("📋 Found 2 tables in current schema", output)
            self.assertIn("✓ users", output)
            self.assertIn("❌ user_sessions (missing)", output)
            self.assertIn("❌ companies (missing)", output)
            self.assertIn("⚠️  2 required tables are missing: user_sessions, companies", output)
            self.assertIn("💡 Consider running migrations or checking schema configuration", output)

    def test_verify_required_tables_database_error(self):
        """Test verification when database query fails"""
        with patch("apps.authentication.management.commands.setup_ci_db.connection") as mock_connection:
            mock_cursor = MagicMock()
            mock_cursor.execute.side_effect = Exception("Database error")
            mock_connection.cursor.return_value.__enter__.return_value = mock_cursor

            self.command.verify_required_tables()
            output = self.out.getvalue()

            self.assertIn("⚠️  Could not verify tables: Database error", output)

    def test_full_command_force_public_schema_option(self):
        """Test --force-public-schema option with full command execution"""
        with patch("apps.authentication.management.commands.setup_ci_db.connection") as mock_connection:
            with patch("apps.authentication.management.commands.setup_ci_db.call_command") as mock_call_command:
                mock_cursor = MagicMock()
                mock_cursor.fetchone.return_value = (1,)
                mock_cursor.fetchall.return_value = [("users",), ("user_sessions",), ("companies",)]
                mock_connection.cursor.return_value.__enter__.return_value = mock_cursor

                stdout, _ = self.call_command_with_output("--force-public-schema")

                self.assertIn("🔧 Setting up CI to use public schema...", stdout)
                self.assertIn("✓ Database setup completed for CI environment", stdout)
                mock_call_command.assert_called_with("migrate", verbosity=1, interactive=False)

    def test_full_command_create_schema_and_run_migrations_options(self):
        """Test --create-schema and --run-migrations options together with full command execution"""
        with patch("apps.authentication.management.commands.setup_ci_db.connection") as mock_connection:
            with patch("apps.authentication.management.commands.setup_ci_db.call_command") as mock_call_command:
                mock_cursor = MagicMock()
                mock_cursor.fetchone.return_value = (1,)
                mock_cursor.fetchall.return_value = [("users",), ("user_sessions",), ("companies",)]
                mock_connection.cursor.return_value.__enter__.return_value = mock_cursor

                stdout, _ = self.call_command_with_output("--create-schema", "--run-migrations")

                self.assertIn("Creating auth schema if it does not exist...", stdout)
                self.assertIn("✓ Auth schema created or already exists", stdout)
                self.assertIn("🔄 Running database migrations...", stdout)
                self.assertIn("✓ Database migrations completed", stdout)
                mock_call_command.assert_called_with("migrate", verbosity=1, interactive=False)

    def test_full_command_auth_schema_setup_failure_continues_normally(self):
        """Test that auth schema setup failure is handled gracefully and command continues"""
        with patch("apps.authentication.management.commands.setup_ci_db.connection") as mock_connection:
            with patch("apps.authentication.management.commands.setup_ci_db.call_command") as mock_call_command:
                mock_cursor = MagicMock()
                # Setup side effects for different calls
                call_count = [0]

                def mock_execute(query):
                    call_count[0] += 1
                    if call_count[0] == 1:  # First call to create_auth_schema
                        raise Exception("Permission denied")
                    # Subsequent calls succeed

                mock_cursor.execute.side_effect = mock_execute
                mock_cursor.fetchone.return_value = (1,)
                mock_cursor.fetchall.return_value = [("users",), ("user_sessions",), ("companies",)]
                mock_connection.cursor.return_value.__enter__.return_value = mock_cursor

                stdout, _ = self.call_command_with_output("--create-schema")

                # The create_auth_schema method handles the exception internally
                self.assertIn("❌ Error creating auth schema: Permission denied", stdout)
                self.assertIn("⚠️  Continuing without auth schema (using public schema)", stdout)
                # The command should continue and complete successfully
                self.assertIn("✓ Database setup completed for CI environment", stdout)
                # No migration call should happen because --run-migrations was not specified
                mock_call_command.assert_not_called()

    @patch.dict(os.environ, {}, clear=True)
    def test_full_command_local_environment_uses_auth_schema(self):
        """Test that local environment uses auth schema by default with full command execution"""
        with patch("apps.authentication.management.commands.setup_ci_db.connection") as mock_connection:
            mock_cursor = MagicMock()
            mock_cursor.fetchone.return_value = (1,)
            mock_cursor.fetchall.return_value = [("users",), ("user_sessions",), ("companies",)]
            mock_connection.cursor.return_value.__enter__.return_value = mock_cursor

            stdout, _ = self.call_command_with_output()

            self.assertIn("🏠 Local environment detected", stdout)
            self.assertIn("Creating auth schema if it does not exist...", stdout)
            self.assertIn("✓ Auth schema created or already exists", stdout)

    def test_full_command_completion_message(self):
        """Test that command completion message is always shown"""
        with patch("apps.authentication.management.commands.setup_ci_db.connection") as mock_connection:
            mock_cursor = MagicMock()
            mock_cursor.fetchone.return_value = (1,)
            mock_cursor.fetchall.return_value = [("users",), ("user_sessions",), ("companies",)]
            mock_connection.cursor.return_value.__enter__.return_value = mock_cursor

            stdout, _ = self.call_command_with_output()

            self.assertIn("✓ Database setup completed for CI environment", stdout)

    @override_settings(DEBUG=True)
    def test_show_debug_mode_true(self):
        """Test showing DEBUG mode when True"""
        self.command.show_database_config()
        output = self.out.getvalue()

        self.assertIn("DEBUG mode: True", output)

    @override_settings(DEBUG=False)
    def test_show_debug_mode_false(self):
        """Test showing DEBUG mode when False"""
        self.command.show_database_config()
        output = self.out.getvalue()

        self.assertIn("DEBUG mode: False", output)

    def test_setup_public_schema_strips_auth_option_correctly(self):
        """Test that public schema setup correctly strips auth option from complex options"""
        with patch("apps.authentication.management.commands.setup_ci_db.call_command") as mock_call_command:
            with override_settings(
                DATABASES={
                    "default": {
                        "ENGINE": "django.db.backends.postgresql",
                        "OPTIONS": {"options": "-c search_path=auth -c timezone=UTC"},
                    }
                }
            ):
                self.command.setup_public_schema_ci()
                output = self.out.getvalue()

                self.assertIn("✓ Temporarily switched to public schema for CI", output)
                # Verify that the auth schema option was removed
                from django.conf import settings

                options = settings.DATABASES["default"]["OPTIONS"]["options"]
                self.assertNotIn("search_path=auth", options)
                self.assertIn("timezone=UTC", options)
