# Generated migration to fix CompanyInvitation constraint

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('authentication', '0012_companyinvitation_and_more'),
    ]

    operations = [
        # Remove the old constraint with the frozen datetime
        migrations.RemoveConstraint(
            model_name='companyinvitation',
            name='unique_active_invitation_per_email_company',
        ),
        # Add the new constraint that only checks is_accepted=False
        # This is simpler and doesn't rely on dynamic time conditions
        migrations.AddConstraint(
            model_name='companyinvitation',
            constraint=models.UniqueConstraint(
                condition=models.Q(('is_accepted', False)),
                fields=('company', 'invitee_email'),
                name='unique_pending_invitation_per_email_company',
            ),
        ),
    ]
