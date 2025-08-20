"""
Tests for Django management commands
"""

import sys
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from apps.authentication.models import UserSession


class TestCheckDbHealthCommand(TestCase):
    """Test cases for check_db_health management command"""

    def setUp(self):
        self.out = StringIO()
        self.err = StringIO()

    def tearDown(self):
        # Clean up any patches
        pass

    def test_successful_health_check(self):
        """Test successful database health check"""
        # Test the command behavior without sys.exit by catching the exception
        with patch("config.database_retry.DatabaseHealthCheck.is_healthy", return_value=True):
            try:
                call_command("check_db_health", stdout=self.out, stderr=self.err)
            except SystemExit as e:
                # Verify it exits with code 0 (success)
                self.assertEqual(e.code, 0)

                output = self.out.getvalue()
                self.assertIn("Database is healthy", output)
            else:
                self.fail("Expected SystemExit to be raised")

    @patch("config.database_retry.DatabaseHealthCheck.is_healthy")
    @patch("apps.authentication.management.commands.check_db_health.sys.exit")
    def test_failed_health_check_after_retries(self, mock_exit, mock_is_healthy):
        """Test failed database health check after all retries"""
        mock_is_healthy.return_value = False

        call_command("check_db_health", "--retry-count=2", stdout=self.out, stderr=self.err)

        output = self.out.getvalue()
        self.assertIn("Database is unhealthy after 2 attempts", output)
        mock_exit.assert_called_once_with(1)

    @patch("config.database_retry.DatabaseHealthCheck.is_healthy")
    @patch("apps.authentication.management.commands.check_db_health.sys.exit")
    def test_health_check_with_exception(self, mock_exit, mock_is_healthy):
        """Test health check with exception"""
        mock_is_healthy.side_effect = Exception("Database connection error")

        call_command("check_db_health", "--retry-count=1", stdout=self.out, stderr=self.err)

        output = self.out.getvalue()
        self.assertIn("Database health check error", output)
        self.assertIn("Database connection error", output)
        mock_exit.assert_called_once_with(1)

    def test_no_cache_option(self):
        """Test --no-cache option"""
        with patch("config.database_retry.DatabaseHealthCheck.is_healthy", return_value=True) as mock_is_healthy:
            try:
                call_command("check_db_health", "--no-cache", stdout=self.out, stderr=self.err)
            except SystemExit as e:
                # Verify it exits with code 0 (success)
                self.assertEqual(e.code, 0)
                mock_is_healthy.assert_called_with(use_cache=False)
            else:
                self.fail("Expected SystemExit to be raised")


class TestCleanupSessionsCommand(TestCase):
    """Test cases for cleanup_sessions management command"""

    def setUp(self):
        self.out = StringIO()
        self.err = StringIO()

    def test_cleanup_with_no_expired_sessions(self):
        """Test cleanup when no expired sessions exist"""
        # Mock the cleanup method to avoid database dependency
        with patch("apps.authentication.models.UserSession.objects.filter") as mock_filter:
            mock_queryset = MagicMock()
            mock_queryset.count.return_value = 0
            mock_filter.return_value = mock_queryset

            call_command("cleanup_sessions", stdout=self.out, stderr=self.err)
            output = self.out.getvalue()
            self.assertIn("No expired sessions found", output)

    def test_cleanup_with_expired_sessions_dry_run(self):
        """Test dry run mode with expired sessions"""
        # Mock the cleanup query to simulate expired sessions
        with patch("apps.authentication.models.UserSession.objects.filter") as mock_filter:
            mock_queryset = MagicMock()
            mock_queryset.count.return_value = 1
            mock_filter.return_value = mock_queryset

            call_command("cleanup_sessions", "--dry-run", stdout=self.out, stderr=self.err)

            output = self.out.getvalue()
            self.assertIn("DRY RUN: Would delete 1 expired sessions", output)
            # Verify delete was not called in dry run
            mock_queryset.delete.assert_not_called()

    def test_cleanup_with_expired_sessions_actual(self):
        """Test actual cleanup of expired sessions"""
        # Mock the cleanup to simulate successful deletion
        with patch("apps.authentication.models.UserSession.objects.filter") as mock_filter:
            with patch("apps.authentication.models.UserSession.cleanup_expired_sessions") as mock_cleanup:
                mock_queryset = MagicMock()
                mock_queryset.count.return_value = 1
                mock_filter.return_value = mock_queryset
                mock_cleanup.return_value = 1  # Return count of deleted sessions

                call_command("cleanup_sessions", stdout=self.out, stderr=self.err)

                output = self.out.getvalue()
                self.assertIn("Successfully cleaned up 1 expired sessions", output)
                mock_cleanup.assert_called_once()

    def test_cleanup_with_exception(self):
        """Test cleanup with exception"""
        # Mock cleanup to raise an exception
        with patch("apps.authentication.models.UserSession.objects.filter") as mock_filter:
            mock_queryset = MagicMock()
            mock_queryset.count.return_value = 1
            mock_filter.return_value = mock_queryset

            # Make the cleanup operation fail
            mock_queryset.delete.side_effect = Exception("Cleanup failed")

            with self.assertRaises(Exception):
                call_command("cleanup_sessions", stdout=self.out, stderr=self.err)

            output = self.out.getvalue()
            self.assertIn("Error cleaning up sessions", output)


class TestDebugUsersCommand(TestCase):
    """Test cases for debug_users management command"""

    def setUp(self):
        self.out = StringIO()
        self.err = StringIO()

    @patch("builtins.input", return_value="")
    def test_debug_users_no_users(self, mock_input):
        """Test debug_users command with no users"""
        with patch("django.contrib.auth.get_user_model") as mock_get_user_model:
            mock_user_class = MagicMock()
            mock_user_class.objects.count.return_value = 0
            mock_user_class.objects.all.return_value = []
            mock_get_user_model.return_value = mock_user_class

            call_command("debug_users", stdout=self.out, stderr=self.err)

            output = self.out.getvalue()
            self.assertIn("Total users in database: 0", output)

    @patch("builtins.input", return_value="")
    def test_debug_users_with_users(self, mock_input):
        """Test debug_users command with existing users"""
        with patch("django.contrib.auth.get_user_model") as mock_get_user_model:
            mock_user = MagicMock()
            mock_user.email = "test@example.com"
            mock_user.first_name = "Test"
            mock_user.last_name = "User"
            mock_user.is_active = True
            mock_user.date_joined = timezone.now()

            mock_user_class = MagicMock()
            mock_user_class.objects.count.return_value = 1
            mock_user_class.objects.all.return_value = [mock_user]
            mock_get_user_model.return_value = mock_user_class

            call_command("debug_users", stdout=self.out, stderr=self.err)

            output = self.out.getvalue()
            self.assertIn("Total users in database: 1", output)
            self.assertIn("Email: test@example.com", output)
            self.assertIn("First name: Test", output)

    @patch("builtins.input", return_value="test@example.com")
    def test_debug_users_email_lookup_found(self, mock_input):
        """Test debug_users command with email lookup - user found"""
        with patch("django.contrib.auth.get_user_model") as mock_get_user_model:
            mock_user = MagicMock()
            mock_user.email = "test@example.com"
            mock_user.first_name = "Test"
            mock_user.last_name = "User"
            mock_user.is_active = True
            mock_user.date_joined = timezone.now()
            mock_user.check_password.return_value = True

            mock_user_class = MagicMock()
            mock_user_class.objects.count.return_value = 1
            mock_user_class.objects.all.return_value = [mock_user]
            mock_user_class.objects.get.return_value = mock_user
            mock_get_user_model.return_value = mock_user_class

            call_command("debug_users", stdout=self.out, stderr=self.err)

            output = self.out.getvalue()
            self.assertIn("Found user:", output)
            self.assertIn("Password check available:", output)

    @patch("builtins.input", return_value="notfound@example.com")
    def test_debug_users_email_lookup_not_found(self, mock_input):
        """Test debug_users command with email lookup - user not found"""
        from django.contrib.auth.models import User

        with patch("django.contrib.auth.get_user_model") as mock_get_user_model:
            mock_user_class = MagicMock()
            mock_user_class.objects.count.return_value = 0
            mock_user_class.objects.all.return_value = []
            mock_user_class.objects.get.side_effect = User.DoesNotExist()
            mock_get_user_model.return_value = mock_user_class

            call_command("debug_users", stdout=self.out, stderr=self.err)

            output = self.out.getvalue()
            self.assertIn("User with email 'notfound@example.com' not found", output)


class TestMigrateToAuthSchemaCommand(TestCase):
    """Test cases for migrate_to_auth_schema management command"""

    def setUp(self):
        self.out = StringIO()
        self.err = StringIO()

    @patch("django.db.connection.cursor")
    def test_migrate_to_auth_schema_dry_run(self, mock_cursor):
        """Test migrate_to_auth_schema command in dry run mode"""
        mock_cursor_obj = MagicMock()
        mock_cursor.return_value.__enter__.return_value = mock_cursor_obj
        mock_cursor_obj.fetchall.return_value = []

        call_command("migrate_to_auth_schema", "--dry-run", stdout=self.out, stderr=self.err)

        output = self.out.getvalue()
        self.assertIn("DRY RUN MODE", output)
        self.assertIn("Ensuring auth schema exists", output)

    @patch("django.db.connection.cursor")
    def test_migrate_to_auth_schema_with_tables(self, mock_cursor):
        """Test migrate_to_auth_schema command with existing tables"""
        mock_cursor_obj = MagicMock()
        mock_cursor.return_value.__enter__.return_value = mock_cursor_obj

        # Mock different return values for different queries - need more side_effect values
        mock_cursor_obj.fetchall.side_effect = [
            [("authentication_user",), ("companies",)],  # public tables
            [("users",), ("companies",)],  # auth tables
            [],  # constraints query for authentication_user
            [],  # constraints query for companies
        ]

        call_command("migrate_to_auth_schema", stdout=self.out, stderr=self.err)

        output = self.out.getvalue()
        self.assertIn("Tables in public:", output)
        self.assertIn("Tables in auth:", output)
        self.assertIn("Migration to auth schema completed successfully", output)


class TestSetupCiDbCommand(TestCase):
    """Test cases for setup_ci_db management command"""

    def setUp(self):
        self.out = StringIO()
        self.err = StringIO()

    @patch("django.db.connection.cursor")
    def test_setup_ci_db_basic(self, mock_cursor):
        """Test basic setup_ci_db command"""
        mock_cursor_obj = MagicMock()
        mock_cursor.return_value.__enter__.return_value = mock_cursor_obj
        mock_cursor_obj.fetchone.return_value = (1,)

        call_command("setup_ci_db", stdout=self.out, stderr=self.err)

        output = self.out.getvalue()
        self.assertIn("Current database configuration:", output)
        self.assertIn("Database setup completed for CI environment", output)

    @patch("django.db.connection.cursor")
    def test_setup_ci_db_with_schema_creation(self, mock_cursor):
        """Test setup_ci_db command with schema creation"""
        mock_cursor_obj = MagicMock()
        mock_cursor.return_value.__enter__.return_value = mock_cursor_obj
        mock_cursor_obj.fetchone.return_value = (1,)

        call_command("setup_ci_db", "--create-schema", stdout=self.out, stderr=self.err)

        output = self.out.getvalue()
        self.assertIn("Creating auth schema if it does not exist", output)
        self.assertIn("Auth schema created or already exists", output)

    @patch("django.db.connection.cursor")
    def test_setup_ci_db_connection_failure(self, mock_cursor):
        """Test setup_ci_db command with database connection failure"""
        mock_cursor_obj = MagicMock()
        mock_cursor.return_value.__enter__.return_value = mock_cursor_obj
        mock_cursor_obj.execute.side_effect = Exception("Connection failed")

        with self.assertRaises(Exception):
            call_command("setup_ci_db", stdout=self.out, stderr=self.err)

        output = self.out.getvalue()
        self.assertIn("Database connection failed", output)

    @patch("django.db.connection.cursor")
    def test_setup_ci_db_schema_creation_failure(self, mock_cursor):
        """Test setup_ci_db command with schema creation failure"""
        mock_cursor_obj = MagicMock()
        mock_cursor.return_value.__enter__.return_value = mock_cursor_obj

        # Make schema creation fail, but connection check succeed
        def execute_side_effect(sql):
            if "CREATE SCHEMA" in sql:
                raise Exception("Schema creation failed")
            # For connection check
            return None

        mock_cursor_obj.execute.side_effect = execute_side_effect
        mock_cursor_obj.fetchone.return_value = (1,)

        call_command("setup_ci_db", "--create-schema", stdout=self.out, stderr=self.err)

        output = self.out.getvalue()
        self.assertIn("Error creating auth schema", output)
        self.assertIn("Continuing without auth schema", output)
