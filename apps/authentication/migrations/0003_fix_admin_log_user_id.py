# Generated manually to fix django_admin_log.user_id type mismatch with UUID User model

import uuid
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('authentication', '0002_auto_20250908_1433'),
    ]

    operations = [
        # First, clear the admin log table to avoid conversion issues
        migrations.RunSQL(
            sql="DELETE FROM django_admin_log;",
            reverse_sql="-- Cannot reverse deletion"
        ),

        # Drop any existing foreign key constraint
        migrations.RunSQL(
            sql="ALTER TABLE django_admin_log DROP CONSTRAINT IF EXISTS django_admin_log_user_id_fkey CASCADE;",
            reverse_sql="-- Reverse not needed"
        ),

        # Change the user_id column type from integer to UUID
        migrations.RunSQL(
            sql="""
            ALTER TABLE django_admin_log
            ALTER COLUMN user_id TYPE UUID USING NULL;
            """,
            reverse_sql="""
            ALTER TABLE django_admin_log
            ALTER COLUMN user_id TYPE integer;
            """
        ),

        # Re-add the foreign key constraint
        migrations.RunSQL(
            sql="""
            ALTER TABLE django_admin_log
            ADD CONSTRAINT django_admin_log_user_id_fkey
            FOREIGN KEY (user_id) REFERENCES auth.users(id)
            ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED;
            """,
            reverse_sql="""
            ALTER TABLE django_admin_log
            DROP CONSTRAINT django_admin_log_user_id_fkey;
            """
        ),
    ]