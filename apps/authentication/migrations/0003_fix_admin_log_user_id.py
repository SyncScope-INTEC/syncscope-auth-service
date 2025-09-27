# Generated manually to fix django_admin_log.user_id type mismatch with UUID User model

import uuid
from django.db import migrations, models, connection
import django.db.models.deletion


def fix_admin_log_user_id_auth_service(apps, schema_editor):
    """
    Fix django_admin_log.user_id type to match auth service UUID User model
    """
    # Only run on PostgreSQL - SQLite tests don't need this
    if connection.vendor != 'postgresql':
        return

    with connection.cursor() as cursor:
        # Determine the correct table reference based on environment
        # Check if we're in CI/test environment (using public schema)
        cursor.execute("SELECT current_schema();")
        current_schema = cursor.fetchone()[0]

        # In CI/test, users table is in public schema as users (no schema prefix)
        # In production, users table is in auth schema as auth.users
        if current_schema == 'public':
            users_table = 'users'
        else:
            users_table = 'auth.users'

        # Clear existing data to avoid conversion issues
        cursor.execute("DELETE FROM django_admin_log;")

        # Drop foreign key constraint
        cursor.execute("ALTER TABLE django_admin_log DROP CONSTRAINT IF EXISTS django_admin_log_user_id_fkey CASCADE;")

        # Change column type from integer to UUID
        cursor.execute("ALTER TABLE django_admin_log ALTER COLUMN user_id TYPE UUID USING NULL;")

        # Re-add foreign key constraint with correct table reference
        cursor.execute(f"""
            ALTER TABLE django_admin_log
            ADD CONSTRAINT django_admin_log_user_id_fkey
            FOREIGN KEY (user_id) REFERENCES {users_table}(id)
            ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED;
        """)


def reverse_fix_admin_log_user_id_auth_service(apps, schema_editor):
    """Reverse operation - not implemented"""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('authentication', '0002_auto_20250908_1433'),
    ]

    operations = [
        migrations.RunPython(
            fix_admin_log_user_id_auth_service,
            reverse_fix_admin_log_user_id_auth_service,
        ),
    ]