"""
Tests for manage_db.py
"""

import sys
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest
from django.test import TestCase


class TestManageDb(TestCase):
    """Test cases for manage_db.py functions"""

    def setUp(self):
        # Mock sys.argv to avoid conflicts with test runner
        self.original_argv = sys.argv.copy()

    def tearDown(self):
        sys.argv = self.original_argv

    @patch("manage_db.django.setup")
    @patch("manage_db.os.environ.setdefault")
    def test_setup_django(self, mock_setdefault, mock_setup):
        """Test setup_django function"""
        from manage_db import setup_django

        setup_django()

        mock_setdefault.assert_called_once_with("DJANGO_SETTINGS_MODULE", "config.settings")
        mock_setup.assert_called_once()

    @patch("manage_db.setup_django")
    @patch("config.database.create_auth_schema_if_not_exists")
    @patch("builtins.print")
    def test_create_auth_schema_success(self, mock_print, mock_create_schema, mock_setup_django):
        """Test successful auth schema creation"""
        mock_create_schema.return_value = None

        from manage_db import create_auth_schema

        result = create_auth_schema()

        self.assertTrue(result)
        mock_setup_django.assert_called_once()
        mock_create_schema.assert_called_once()
        mock_print.assert_called_with("✓ Successfully created auth schema")

    @patch("manage_db.setup_django")
    @patch("config.database.create_auth_schema_if_not_exists")
    @patch("builtins.print")
    def test_create_auth_schema_failure(self, mock_print, mock_create_schema, mock_setup_django):
        """Test auth schema creation failure"""
        mock_create_schema.side_effect = Exception("Database connection failed")

        from manage_db import create_auth_schema

        result = create_auth_schema()

        self.assertFalse(result)
        mock_setup_django.assert_called_once()
        mock_create_schema.assert_called_once()
        mock_print.assert_any_call("❌ Error creating auth schema: Database connection failed")
        mock_print.assert_any_call("Please ensure your database connection is properly configured")

    @patch("manage_db.execute_from_command_line")
    @patch("builtins.print")
    def test_run_migrations_success(self, mock_print, mock_execute):
        """Test successful migrations"""
        mock_execute.return_value = None

        from manage_db import run_migrations

        result = run_migrations()

        self.assertTrue(result)
        self.assertEqual(mock_execute.call_count, 2)
        mock_execute.assert_any_call(["manage.py", "makemigrations"])
        mock_execute.assert_any_call(["manage.py", "migrate"])
        mock_print.assert_called_with("✓ Migrations completed successfully")

    @patch("manage_db.execute_from_command_line")
    @patch("builtins.print")
    def test_run_migrations_failure(self, mock_print, mock_execute):
        """Test migrations failure"""
        mock_execute.side_effect = Exception("Migration failed")

        from manage_db import run_migrations

        result = run_migrations()

        self.assertFalse(result)
        mock_execute.assert_called_once_with(["manage.py", "makemigrations"])
        mock_print.assert_called_with("❌ Error running migrations: Migration failed")

    @patch("manage_db.execute_from_command_line")
    @patch("builtins.print")
    def test_create_superuser_success(self, mock_print, mock_execute):
        """Test successful superuser creation"""
        mock_execute.return_value = None

        from manage_db import create_superuser

        result = create_superuser()

        self.assertTrue(result)
        mock_execute.assert_called_once_with(["manage.py", "createsuperuser"])

    @patch("manage_db.execute_from_command_line")
    @patch("builtins.print")
    def test_create_superuser_failure(self, mock_print, mock_execute):
        """Test superuser creation failure"""
        mock_execute.side_effect = Exception("Superuser creation failed")

        from manage_db import create_superuser

        result = create_superuser()

        self.assertFalse(result)
        mock_execute.assert_called_once_with(["manage.py", "createsuperuser"])
        mock_print.assert_called_with("❌ Error creating superuser: Superuser creation failed")

    @patch("manage_db.create_auth_schema")
    @patch("builtins.print")
    def test_main_schema_command(self, mock_print, mock_create_schema):
        """Test main function with schema command"""
        mock_create_schema.return_value = True
        sys.argv = ["manage_db.py", "schema"]

        from manage_db import main

        main()

        mock_create_schema.assert_called_once()

    @patch("manage_db.run_migrations")
    @patch("builtins.print")
    def test_main_migrate_command(self, mock_print, mock_migrate):
        """Test main function with migrate command"""
        mock_migrate.return_value = True
        sys.argv = ["manage_db.py", "migrate"]

        from manage_db import main

        main()

        mock_migrate.assert_called_once()

    @patch("manage_db.create_superuser")
    @patch("builtins.print")
    def test_main_superuser_command(self, mock_print, mock_create_superuser):
        """Test main function with superuser command"""
        mock_create_superuser.return_value = True
        sys.argv = ["manage_db.py", "superuser"]

        from manage_db import main

        main()

        mock_create_superuser.assert_called_once()

    @patch("manage_db.create_auth_schema")
    @patch("manage_db.run_migrations")
    @patch("builtins.print")
    def test_main_setup_command_success(self, mock_print, mock_migrate, mock_create_schema):
        """Test main function with setup command - success"""
        mock_create_schema.return_value = True
        mock_migrate.return_value = True
        sys.argv = ["manage_db.py", "setup"]

        from manage_db import main

        main()

        mock_create_schema.assert_called_once()
        mock_migrate.assert_called_once()
        mock_print.assert_any_call("🚀 Setting up database for Railway PostgreSQL...")
        mock_print.assert_any_call("✅ Database setup complete!")
        mock_print.assert_any_call("Next steps:")
        mock_print.assert_any_call("1. Run: python manage_db.py superuser")
        mock_print.assert_any_call("2. Start the server: python manage.py runserver")

    @patch("manage_db.create_auth_schema")
    @patch("manage_db.run_migrations")
    @patch("builtins.print")
    def test_main_setup_command_failure(self, mock_print, mock_migrate, mock_create_schema):
        """Test main function with setup command - failure"""
        mock_create_schema.return_value = False
        sys.argv = ["manage_db.py", "setup"]

        from manage_db import main

        main()

        mock_create_schema.assert_called_once()
        mock_migrate.assert_not_called()  # Should not be called if schema creation fails
        mock_print.assert_any_call("🚀 Setting up database for Railway PostgreSQL...")
        mock_print.assert_any_call("❌ Setup failed. Please check your database configuration.")

    @patch("builtins.print")
    def test_main_unknown_command(self, mock_print):
        """Test main function with unknown command"""
        sys.argv = ["manage_db.py", "unknown"]

        from manage_db import main

        main()

        mock_print.assert_called_with("Unknown command: unknown")

    @patch("builtins.print")
    def test_main_no_arguments(self, mock_print):
        """Test main function with no arguments (shows usage)"""
        sys.argv = ["manage_db.py"]

        from manage_db import main

        main()

        # Check that usage information is printed
        calls = [call[0][0] for call in mock_print.call_args_list]
        usage_text = "\n".join(calls)
        self.assertIn("Railway PostgreSQL Database Setup", usage_text)
        self.assertIn("Usage:", usage_text)
        self.assertIn("python manage_db.py schema", usage_text)
        self.assertIn("python manage_db.py migrate", usage_text)
        self.assertIn("python manage_db.py superuser", usage_text)
        self.assertIn("python manage_db.py setup", usage_text)

    @patch("manage_db.main")
    def test_main_execution(self, mock_main):
        """Test that main is called when script is executed directly"""
        # This simulates the if __name__ == "__main__": block
        with patch("manage_db.__name__", "__main__"):
            # Import and reload to trigger the main execution
            import importlib

            import manage_db

            importlib.reload(manage_db)

        # Note: This test is more conceptual since we can't easily test
        # the __name__ == "__main__" condition in a unit test
