"""
Management command to properly reset admin migrations for UUID User model.
This fixes the django_admin_log user_id type mismatch issue definitively.
"""

import logging

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import connection

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Reset admin migrations to fix UUID User model admin log issue"

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Force reset without confirmation prompt",
        )

    def handle(self, *args, **options):
        """Execute the admin log reset."""
        if connection.vendor != "postgresql":
            self.stdout.write(self.style.WARNING("This fix is only needed for PostgreSQL"))
            return

        if not options["force"]:
            confirm = input(
                "This will DROP the django_admin_log table and reset admin migrations. "
                "All admin log history will be lost. Continue? (y/N): "
            )
            if confirm.lower() != "y":
                self.stdout.write(self.style.WARNING("Operation cancelled"))
                return

        try:
            with connection.cursor() as cursor:
                self.stdout.write("Checking current admin log configuration...")

                # Check if table exists
                cursor.execute(
                    """
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_name = 'django_admin_log'
                    );
                """
                )
                table_exists = cursor.fetchone()[0]

                if table_exists:
                    # Check current user_id type
                    cursor.execute(
                        """
                        SELECT data_type
                        FROM information_schema.columns
                        WHERE table_name = 'django_admin_log'
                        AND column_name = 'user_id'
                    """
                    )
                    current_type = cursor.fetchone()
                    self.stdout.write(f'Current user_id type: {current_type[0] if current_type else "unknown"}')

                    if current_type and current_type[0] == "uuid":
                        self.stdout.write(self.style.SUCCESS("Admin log is already configured correctly for UUID User model"))
                        return

                    self.stdout.write("Dropping django_admin_log table...")
                    cursor.execute("DROP TABLE IF EXISTS django_admin_log CASCADE;")
                else:
                    self.stdout.write("django_admin_log table does not exist")

            # Reset admin migrations
            self.stdout.write("Resetting admin migrations...")
            call_command("migrate", "admin", "zero", "--fake", verbosity=0)

            self.stdout.write("Re-applying admin migrations...")
            call_command("migrate", "admin", verbosity=1)

            # Verify the fix
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT data_type
                    FROM information_schema.columns
                    WHERE table_name = 'django_admin_log'
                    AND column_name = 'user_id'
                """
                )
                new_type = cursor.fetchone()

                if new_type and new_type[0] == "uuid":
                    self.stdout.write(self.style.SUCCESS(f"Successfully reset admin log! user_id is now {new_type[0]} type"))
                else:
                    self.stdout.write(
                        self.style.ERROR(
                            f'Something went wrong - user_id type is still {new_type[0] if new_type else "unknown"}'
                        )
                    )

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error resetting admin log: {str(e)}"))
            logger.error(f"Admin log reset failed: {str(e)}", exc_info=True)
            raise
