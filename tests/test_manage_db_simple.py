"""
Simple tests for manage_db.py to improve coverage
"""

import sys
from unittest.mock import MagicMock, patch

from django.test import TestCase


class TestManageDbSimple(TestCase):
    """Simple tests for manage_db.py functions"""

    @patch("manage_db.django.setup")
    @patch("manage_db.os.environ.setdefault")
    def test_setup_django(self, mock_setdefault, mock_django_setup):
        """Test setup_django function"""
        from manage_db import setup_django

        setup_django()

        mock_setdefault.assert_called_once_with("DJANGO_SETTINGS_MODULE", "config.settings")
        mock_django_setup.assert_called_once()

    @patch("builtins.print")
    @patch("config.database.create_auth_schema_if_not_exists")
    @patch("manage_db.setup_django")
    def test_create_auth_schema_success(self, mock_setup, mock_create, mock_print):
        """Test create_auth_schema success"""
        from manage_db import create_auth_schema

        result = create_auth_schema()

        mock_setup.assert_called_once()
        mock_create.assert_called_once()
        self.assertTrue(result)
        mock_print.assert_called_with("✓ Successfully created auth schema")

    @patch("builtins.print")
    @patch("config.database.create_auth_schema_if_not_exists")
    @patch("manage_db.setup_django")
    def test_create_auth_schema_failure(self, mock_setup, mock_create, mock_print):
        """Test create_auth_schema failure"""
        mock_create.side_effect = Exception("Connection failed")

        from manage_db import create_auth_schema

        result = create_auth_schema()

        self.assertFalse(result)
        mock_print.assert_any_call("❌ Error creating auth schema: Connection failed")
        mock_print.assert_any_call("Please ensure your database connection is properly configured")

    @patch("builtins.print")
    @patch("manage_db.execute_from_command_line")
    def test_run_migrations_success(self, mock_execute, mock_print):
        """Test run_migrations success"""
        from manage_db import run_migrations

        result = run_migrations()

        self.assertTrue(result)
        self.assertEqual(mock_execute.call_count, 2)
        mock_print.assert_called_with("✓ Migrations completed successfully")

    @patch("builtins.print")
    @patch("manage_db.execute_from_command_line")
    def test_run_migrations_failure(self, mock_execute, mock_print):
        """Test run_migrations failure"""
        mock_execute.side_effect = Exception("Migration failed")

        from manage_db import run_migrations

        result = run_migrations()

        self.assertFalse(result)
        mock_print.assert_called_with("❌ Error running migrations: Migration failed")

    @patch("builtins.print")
    @patch("manage_db.execute_from_command_line")
    def test_create_superuser_success(self, mock_execute, mock_print):
        """Test create_superuser success"""
        from manage_db import create_superuser

        result = create_superuser()

        self.assertTrue(result)
        mock_execute.assert_called_once()

    @patch("builtins.print")
    @patch("manage_db.execute_from_command_line")
    def test_create_superuser_failure(self, mock_execute, mock_print):
        """Test create_superuser failure"""
        mock_execute.side_effect = Exception("Superuser creation failed")

        from manage_db import create_superuser

        result = create_superuser()

        self.assertFalse(result)
        mock_print.assert_called_with("❌ Error creating superuser: Superuser creation failed")

    def test_main_no_args(self):
        """Test main with no arguments"""
        original_argv = sys.argv[:]
        sys.argv = ["manage_db.py"]

        try:
            with patch("builtins.print") as mock_print:
                from manage_db import main

                main()

                # Should print usage
                usage_calls = [call for call in mock_print.call_args_list if "Usage:" in str(call)]
                self.assertTrue(len(usage_calls) > 0)
        finally:
            sys.argv = original_argv

    @patch("manage_db.create_auth_schema")
    def test_main_schema_command(self, mock_create_schema):
        """Test main with schema command"""
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
        """Test main with migrate command"""
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
        """Test main with superuser command"""
        original_argv = sys.argv[:]
        sys.argv = ["manage_db.py", "superuser"]

        try:
            from manage_db import main

            main()

            mock_superuser.assert_called_once()
        finally:
            sys.argv = original_argv

    @patch("builtins.print")
    @patch("manage_db.run_migrations")
    @patch("manage_db.create_auth_schema")
    def test_main_setup_command_success(self, mock_create_schema, mock_migrate, mock_print):
        """Test main with setup command - success"""
        mock_create_schema.return_value = True

        original_argv = sys.argv[:]
        sys.argv = ["manage_db.py", "setup"]

        try:
            from manage_db import main

            main()

            mock_create_schema.assert_called_once()
            mock_migrate.assert_called_once()
            mock_print.assert_any_call("🚀 Setting up database for Railway PostgreSQL...")
            mock_print.assert_any_call("✅ Database setup complete!")
        finally:
            sys.argv = original_argv

    @patch("builtins.print")
    @patch("manage_db.run_migrations")
    @patch("manage_db.create_auth_schema")
    def test_main_setup_command_failure(self, mock_create_schema, mock_migrate, mock_print):
        """Test main with setup command - failure"""
        mock_create_schema.return_value = False

        original_argv = sys.argv[:]
        sys.argv = ["manage_db.py", "setup"]

        try:
            from manage_db import main

            main()

            mock_create_schema.assert_called_once()
            mock_migrate.assert_not_called()  # Should not run migrations if schema creation fails
            mock_print.assert_any_call("❌ Setup failed. Please check your database configuration.")
        finally:
            sys.argv = original_argv

    def test_main_unknown_command(self):
        """Test main with unknown command"""
        original_argv = sys.argv[:]
        sys.argv = ["manage_db.py", "unknown"]

        try:
            with patch("builtins.print") as mock_print:
                from manage_db import main

                main()

                mock_print.assert_called_with("Unknown command: unknown")
        finally:
            sys.argv = original_argv
