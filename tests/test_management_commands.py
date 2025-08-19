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

    @patch('apps.authentication.management.commands.check_db_health.DatabaseHealthCheck.is_healthy')
    @patch('sys.exit')
    def test_successful_health_check(self, mock_exit, mock_is_healthy):
        """Test successful database health check"""
        mock_is_healthy.return_value = True
        
        call_command('check_db_health', stdout=self.out, stderr=self.err)
        
        output = self.out.getvalue()
        self.assertIn('Database is healthy', output)
        mock_exit.assert_called_once_with(0)

    @patch('apps.authentication.management.commands.check_db_health.DatabaseHealthCheck.is_healthy')
    @patch('sys.exit')
    def test_failed_health_check_after_retries(self, mock_exit, mock_is_healthy):
        """Test failed database health check after all retries"""
        mock_is_healthy.return_value = False
        
        call_command('check_db_health', '--retry-count=2', stdout=self.out, stderr=self.err)
        
        output = self.out.getvalue()
        self.assertIn('Database is unhealthy after 2 attempts', output)
        mock_exit.assert_called_once_with(1)

    @patch('apps.authentication.management.commands.check_db_health.DatabaseHealthCheck.is_healthy')
    @patch('sys.exit')
    def test_health_check_with_exception(self, mock_exit, mock_is_healthy):
        """Test health check with exception"""
        mock_is_healthy.side_effect = Exception("Database connection error")
        
        call_command('check_db_health', '--retry-count=1', stdout=self.out, stderr=self.err)
        
        output = self.out.getvalue()
        self.assertIn('Database health check error', output)
        self.assertIn('Database connection error', output)
        mock_exit.assert_called_once_with(1)

    @patch('apps.authentication.management.commands.check_db_health.DatabaseHealthCheck.is_healthy')
    @patch('sys.exit')
    def test_no_cache_option(self, mock_exit, mock_is_healthy):
        """Test --no-cache option"""
        mock_is_healthy.return_value = True
        
        call_command('check_db_health', '--no-cache', stdout=self.out, stderr=self.err)
        
        mock_is_healthy.assert_called_with(use_cache=False)
        mock_exit.assert_called_once_with(0)


class TestCleanupSessionsCommand(TestCase):
    """Test cases for cleanup_sessions management command"""

    def setUp(self):
        self.out = StringIO()
        self.err = StringIO()

    def test_cleanup_with_no_expired_sessions(self):
        """Test cleanup when no expired sessions exist"""
        call_command('cleanup_sessions', stdout=self.out, stderr=self.err)
        
        output = self.out.getvalue()
        self.assertIn('No expired sessions found', output)

    def test_cleanup_with_expired_sessions_dry_run(self):
        """Test dry run mode with expired sessions"""
        # Create an expired session
        past_time = timezone.now() - timezone.timedelta(hours=1)
        UserSession.objects.create(
            user_id=1,
            session_key='test_session',
            expires_at=past_time
        )
        
        call_command('cleanup_sessions', '--dry-run', stdout=self.out, stderr=self.err)
        
        output = self.out.getvalue()
        self.assertIn('DRY RUN: Would delete 1 expired sessions', output)
        # Verify session wasn't actually deleted
        self.assertEqual(UserSession.objects.count(), 1)

    @patch('apps.authentication.models.UserSession.cleanup_expired_sessions')
    def test_cleanup_with_expired_sessions_actual(self, mock_cleanup):
        """Test actual cleanup of expired sessions"""
        # Create an expired session
        past_time = timezone.now() - timezone.timedelta(hours=1)
        UserSession.objects.create(
            user_id=1,
            session_key='test_session',
            expires_at=past_time
        )
        
        call_command('cleanup_sessions', stdout=self.out, stderr=self.err)
        
        output = self.out.getvalue()
        self.assertIn('Successfully cleaned up 1 expired sessions', output)
        mock_cleanup.assert_called_once()

    @patch('apps.authentication.models.UserSession.cleanup_expired_sessions')
    def test_cleanup_with_exception(self, mock_cleanup):
        """Test cleanup with exception"""
        mock_cleanup.side_effect = Exception("Cleanup failed")
        
        # Create an expired session
        past_time = timezone.now() - timezone.timedelta(hours=1)
        UserSession.objects.create(
            user_id=1,
            session_key='test_session',
            expires_at=past_time
        )
        
        with self.assertRaises(Exception):
            call_command('cleanup_sessions', stdout=self.out, stderr=self.err)
        
        output = self.out.getvalue()
        self.assertIn('Error cleaning up sessions', output)


class TestDebugUsersCommand(TestCase):
    """Test cases for debug_users management command"""

    def setUp(self):
        self.out = StringIO()
        self.err = StringIO()

    @patch('builtins.input', return_value='')
    def test_debug_users_no_users(self, mock_input):
        """Test debug_users command with no users"""
        call_command('debug_users', stdout=self.out, stderr=self.err)
        
        output = self.out.getvalue()
        self.assertIn('Total users in database: 0', output)

    @patch('builtins.input', return_value='')
    def test_debug_users_with_users(self, mock_input):
        """Test debug_users command with existing users"""
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        user = User.objects.create_user(
            email='test@example.com',
            password='testpass',
            first_name='Test',
            last_name='User'
        )
        
        call_command('debug_users', stdout=self.out, stderr=self.err)
        
        output = self.out.getvalue()
        self.assertIn('Total users in database: 1', output)
        self.assertIn('Email: test@example.com', output)
        self.assertIn('First name: Test', output)

    @patch('builtins.input', return_value='test@example.com')
    def test_debug_users_email_lookup_found(self, mock_input):
        """Test debug_users command with email lookup - user found"""
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        user = User.objects.create_user(
            email='test@example.com',
            password='testpass',
            first_name='Test',
            last_name='User'
        )
        
        call_command('debug_users', stdout=self.out, stderr=self.err)
        
        output = self.out.getvalue()
        self.assertIn('Found user:', output)
        self.assertIn('Password check available:', output)

    @patch('builtins.input', return_value='notfound@example.com')
    def test_debug_users_email_lookup_not_found(self, mock_input):
        """Test debug_users command with email lookup - user not found"""
        call_command('debug_users', stdout=self.out, stderr=self.err)
        
        output = self.out.getvalue()
        self.assertIn("User with email 'notfound@example.com' not found", output)


class TestMigrateToAuthSchemaCommand(TestCase):
    """Test cases for migrate_to_auth_schema management command"""

    def setUp(self):
        self.out = StringIO()
        self.err = StringIO()

    @patch('django.db.connection.cursor')
    def test_migrate_to_auth_schema_dry_run(self, mock_cursor):
        """Test migrate_to_auth_schema command in dry run mode"""
        mock_cursor_obj = MagicMock()
        mock_cursor.return_value.__enter__.return_value = mock_cursor_obj
        mock_cursor_obj.fetchall.return_value = []
        
        call_command('migrate_to_auth_schema', '--dry-run', stdout=self.out, stderr=self.err)
        
        output = self.out.getvalue()
        self.assertIn('DRY RUN MODE', output)
        self.assertIn('Ensuring auth schema exists', output)

    @patch('django.db.connection.cursor')
    def test_migrate_to_auth_schema_with_tables(self, mock_cursor):
        """Test migrate_to_auth_schema command with existing tables"""
        mock_cursor_obj = MagicMock()
        mock_cursor.return_value.__enter__.return_value = mock_cursor_obj
        
        # Mock different return values for different queries
        mock_cursor_obj.fetchall.side_effect = [
            [('authentication_user',), ('companies',)],  # public tables
            [('users',), ('companies',)]  # auth tables
        ]
        
        call_command('migrate_to_auth_schema', stdout=self.out, stderr=self.err)
        
        output = self.out.getvalue()
        self.assertIn('Tables in public:', output)
        self.assertIn('Tables in auth:', output)
        self.assertIn('Migration to auth schema completed successfully', output)


class TestSetupCiDbCommand(TestCase):
    """Test cases for setup_ci_db management command"""

    def setUp(self):
        self.out = StringIO()
        self.err = StringIO()

    @patch('django.db.connection.cursor')
    def test_setup_ci_db_basic(self, mock_cursor):
        """Test basic setup_ci_db command"""
        mock_cursor_obj = MagicMock()
        mock_cursor.return_value.__enter__.return_value = mock_cursor_obj
        mock_cursor_obj.fetchone.return_value = (1,)
        
        call_command('setup_ci_db', stdout=self.out, stderr=self.err)
        
        output = self.out.getvalue()
        self.assertIn('Current database configuration:', output)
        self.assertIn('Database setup completed for CI environment', output)

    @patch('django.db.connection.cursor')
    def test_setup_ci_db_with_schema_creation(self, mock_cursor):
        """Test setup_ci_db command with schema creation"""
        mock_cursor_obj = MagicMock()
        mock_cursor.return_value.__enter__.return_value = mock_cursor_obj
        mock_cursor_obj.fetchone.return_value = (1,)
        
        call_command('setup_ci_db', '--create-schema', stdout=self.out, stderr=self.err)
        
        output = self.out.getvalue()
        self.assertIn('Creating auth schema if it does not exist', output)
        self.assertIn('Auth schema created or already exists', output)

    @patch('django.db.connection.cursor')
    def test_setup_ci_db_connection_failure(self, mock_cursor):
        """Test setup_ci_db command with database connection failure"""
        mock_cursor_obj = MagicMock()
        mock_cursor.return_value.__enter__.return_value = mock_cursor_obj
        mock_cursor_obj.execute.side_effect = Exception("Connection failed")
        
        with self.assertRaises(Exception):
            call_command('setup_ci_db', stdout=self.out, stderr=self.err)
        
        output = self.out.getvalue()
        self.assertIn('Database connection failed', output)

    @patch('django.db.connection.cursor')
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
        
        call_command('setup_ci_db', '--create-schema', stdout=self.out, stderr=self.err)
        
        output = self.out.getvalue()
        self.assertIn('Error creating auth schema', output)
        self.assertIn('Continuing without auth schema', output)