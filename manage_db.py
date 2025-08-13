#!/usr/bin/env python
"""
Database management script for Railway PostgreSQL setup
"""
import os
import sys
import django
from django.core.management import execute_from_command_line


def setup_django():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    django.setup()


def create_auth_schema():
    """Create auth schema in PostgreSQL"""
    setup_django()

    try:
        from config.database import create_auth_schema_if_not_exists

        create_auth_schema_if_not_exists()
        print("✓ Successfully created auth schema")
    except Exception as e:
        print(f"❌ Error creating auth schema: {e}")
        print("Please ensure your database connection is properly configured")
        return False
    return True


def run_migrations():
    """Run Django migrations"""
    try:
        execute_from_command_line(["manage.py", "makemigrations"])
        execute_from_command_line(["manage.py", "migrate"])
        print("✓ Migrations completed successfully")
    except Exception as e:
        print(f"❌ Error running migrations: {e}")
        return False
    return True


def create_superuser():
    """Create Django superuser"""
    try:
        execute_from_command_line(["manage.py", "createsuperuser"])
    except Exception as e:
        print(f"❌ Error creating superuser: {e}")
        return False
    return True


def main():
    if len(sys.argv) < 2:
        print(
            """
Railway PostgreSQL Database Setup

Usage:
    python manage_db.py schema    - Create auth schema
    python manage_db.py migrate   - Run migrations
    python manage_db.py superuser - Create superuser
    python manage_db.py setup     - Run complete setup (schema + migrations)
        """
        )
        return

    command = sys.argv[1]

    if command == "schema":
        create_auth_schema()
    elif command == "migrate":
        run_migrations()
    elif command == "superuser":
        create_superuser()
    elif command == "setup":
        print("🚀 Setting up database for Railway PostgreSQL...")
        if create_auth_schema():
            run_migrations()
            print("✅ Database setup complete!")
            print("Next steps:")
            print("1. Run: python manage_db.py superuser")
            print("2. Start the server: python manage.py runserver")
        else:
            print("❌ Setup failed. Please check your database configuration.")
    else:
        print(f"Unknown command: {command}")


if __name__ == "__main__":
    main()
