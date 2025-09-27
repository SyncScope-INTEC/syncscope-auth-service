"""
Management command to manually fix admin log user_id type mismatch.
This ensures the fix is applied even if migrations fail.
"""

from django.core.management.base import BaseCommand
from django.db import connection
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Fix django_admin_log user_id type to match UUID User model'

    def handle(self, *args, **options):
        """Execute the admin log fix."""
        if connection.vendor != 'postgresql':
            self.stdout.write(
                self.style.WARNING('Skipping - only needed for PostgreSQL')
            )
            return

        try:
            with connection.cursor() as cursor:
                # Check current schema
                cursor.execute("SELECT current_schema();")
                current_schema = cursor.fetchone()[0]

                # Determine table reference
                if current_schema == 'public':
                    users_table = 'users'
                else:
                    users_table = 'auth.users'

                self.stdout.write(f"Using schema: {current_schema}")
                self.stdout.write(f"User table reference: {users_table}")

                # Check if fix is needed
                cursor.execute("""
                    SELECT data_type
                    FROM information_schema.columns
                    WHERE table_name = 'django_admin_log'
                    AND column_name = 'user_id'
                """)
                current_type = cursor.fetchone()

                if current_type and current_type[0] == 'uuid':
                    self.stdout.write(
                        self.style.SUCCESS('Admin log user_id is already UUID - no fix needed')
                    )
                    return

                self.stdout.write(
                    self.style.WARNING(f'Current user_id type: {current_type[0] if current_type else "unknown"}')
                )

                # Apply the fix
                self.stdout.write('Clearing existing admin log data...')
                cursor.execute("DELETE FROM django_admin_log;")

                self.stdout.write('Dropping foreign key constraint...')
                cursor.execute("ALTER TABLE django_admin_log DROP CONSTRAINT IF EXISTS django_admin_log_user_id_fkey CASCADE;")

                self.stdout.write('Converting user_id column to UUID...')
                cursor.execute("ALTER TABLE django_admin_log ALTER COLUMN user_id TYPE UUID USING NULL;")

                self.stdout.write('Re-adding foreign key constraint...')
                cursor.execute(f"""
                    ALTER TABLE django_admin_log
                    ADD CONSTRAINT django_admin_log_user_id_fkey
                    FOREIGN KEY (user_id) REFERENCES {users_table}(id)
                    ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED;
                """)

                self.stdout.write(
                    self.style.SUCCESS('Successfully fixed admin log user_id type mismatch')
                )

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error fixing admin log: {str(e)}')
            )
            logger.error(f"Admin log fix failed: {str(e)}", exc_info=True)
            raise