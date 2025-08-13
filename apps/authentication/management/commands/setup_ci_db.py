"""
Management command to set up database for CI/test environments
"""

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "Set up database for CI/test environments"

    def add_arguments(self, parser):
        parser.add_argument(
            "--create-schema",
            action="store_true",
            help="Create auth schema if it does not exist",
        )

    def handle(self, *args, **options):
        """Handle the command execution"""

        # Show current database configuration
        self.show_database_config()

        if options["create_schema"]:
            self.create_auth_schema()

        # Check if database connection works
        self.check_database_connection()

        self.stdout.write(self.style.SUCCESS("✓ Database setup completed for CI environment"))

    def show_database_config(self):
        """Show current database configuration"""
        self.stdout.write("Current database configuration:")

        db_config = settings.DATABASES["default"]
        self.stdout.write(f"  - Engine: {db_config.get('ENGINE', 'Not set')}")
        self.stdout.write(f"  - Name: {db_config.get('NAME', 'Not set')}")
        self.stdout.write(f"  - Host: {db_config.get('HOST', 'Not set')}")
        self.stdout.write(f"  - Port: {db_config.get('PORT', 'Not set')}")
        self.stdout.write(f"  - User: {db_config.get('USER', 'Not set')}")

        options = db_config.get("OPTIONS", {})
        if "options" in options:
            self.stdout.write(f"  - PostgreSQL options: {options['options']}")
            if "search_path=auth" in options["options"]:
                self.stdout.write(self.style.WARNING("  ⚠️  Using auth schema"))
            else:
                self.stdout.write(self.style.SUCCESS("  ✓ Using public schema (recommended for CI)"))
        else:
            self.stdout.write("  - No PostgreSQL options set")

        self.stdout.write(f"  - DEBUG mode: {settings.DEBUG}")
        self.stdout.write("")

    def create_auth_schema(self):
        """Create auth schema if it doesn't exist"""
        self.stdout.write("Creating auth schema if it does not exist...")

        try:
            with connection.cursor() as cursor:
                # Create auth schema if it doesn't exist
                cursor.execute("CREATE SCHEMA IF NOT EXISTS auth;")

            self.stdout.write(self.style.SUCCESS("✓ Auth schema created or already exists"))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Error creating auth schema: {e}"))
            # Don't raise in CI environments, just warn
            self.stdout.write(self.style.WARNING("⚠️  Continuing without auth schema (using public schema)"))

    def check_database_connection(self):
        """Check if database connection works"""
        self.stdout.write("Checking database connection...")

        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                result = cursor.fetchone()
                if result[0] == 1:
                    self.stdout.write(self.style.SUCCESS("✓ Database connection successful"))
                else:
                    raise Exception("Unexpected result from test query")

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Database connection failed: {e}"))
            raise
