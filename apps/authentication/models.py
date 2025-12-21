import uuid
from datetime import timedelta

from django.contrib.auth.models import AbstractUser
from django.core.validators import EmailValidator
from django.db import models
from django.utils import timezone

from config.database_retry import atomic_with_retry

from .db_mixins import RetryableManager, RetryableModelMixin, RetryableUserManager


class Company(RetryableModelMixin, models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    domain = models.CharField(max_length=255, null=True, blank=True)
    industry = models.CharField(max_length=100, null=True, blank=True)
    size = models.CharField(max_length=50, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = RetryableManager()

    class Meta:
        verbose_name_plural = "Companies"
        db_table = "companies"
        ordering = ["-created_at"]

    def __str__(self):
        return self.name

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.domain and not self.domain.startswith("@"):
            self.domain = f"@{self.domain}"


class User(RetryableModelMixin, AbstractUser):
    ROLE_CHOICES = [
        ("admin", "Admin"),
        ("supervisor", "Supervisor"),
        ("developer", "Developer"),
    ]

    PLAN_CHOICES = [
        ("starter", "Starter"),
        ("growth", "Growth"),
        ("enterprise", "Enterprise"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True, validators=[EmailValidator()])
    password = models.CharField(max_length=255, db_column="password_hash")
    first_name = models.CharField(max_length=100, null=True, blank=True)
    last_name = models.CharField(max_length=100, null=True, blank=True)
    phone_number = models.CharField(max_length=20, null=True, blank=True)
    role = models.CharField(max_length=50, choices=ROLE_CHOICES, default="developer")
    plan = models.CharField(max_length=20, choices=PLAN_CHOICES, default="starter")
    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="users", null=True, blank=True, db_column="company_id"
    )
    is_active = models.BooleanField(default=True)
    timezone = models.CharField(max_length=50, default="UTC")
    date_joined = models.DateTimeField(auto_now_add=True, db_column="created_at")
    updated_at = models.DateTimeField(auto_now=True)
    last_login = models.DateTimeField(null=True, blank=True)
    is_staff = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)
    profile_image_path = models.CharField(
        max_length=500, null=True, blank=True, help_text="Path to user profile image stored in Railway volume"
    )
    requires_password_change = models.BooleanField(
        default=False,
        help_text="Flag indicating user must change their password on next login (e.g., temporary password from Stripe setup)",
    )
    # Remove fields that aren't in the new schema
    # is_verified = models.BooleanField(default=False)
    # github_id = models.CharField(max_length=50, null=True, blank=True, unique=True)
    # avatar_url = models.URLField(max_length=500, null=True, blank=True)

    username = None
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    objects = RetryableUserManager()

    class Meta:
        db_table = "users"
        ordering = ["-date_joined"]

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.email})"

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.email:
            self.email = self.email.lower()

        # Only validate domain if user has a company
        if self.company and self.email:
            email_domain = f"@{self.email.split('@')[1]}"
            if self.company.domain != email_domain:
                raise ValidationError({"__all__": [f"Email domain must match company domain: {self.company.domain}"]})

    @atomic_with_retry()
    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def created_at(self):
        """Backward compatibility property for created_at"""
        return self.date_joined

    def get_plan_limits(self):
        """Get the limits and features for the user's current plan."""
        from .plan_limits import get_plan_limits

        return get_plan_limits(self.plan)

    def has_feature(self, feature_name):
        """Check if the user's plan has a specific feature."""
        from .plan_limits import has_feature

        return has_feature(self.plan, feature_name)

    def can_add_user_to_company(self):
        """Check if the user's company can add more users based on plan limits."""
        if not self.company:
            return True

        from .plan_limits import can_add_user

        current_user_count = self.company.users.filter(is_active=True).count()
        return can_add_user(self.plan, current_user_count)

    def can_add_integration(self, current_integration_count=0):
        """Check if the user can add more integrations based on plan limits."""
        from .plan_limits import can_add_integration

        return can_add_integration(self.plan, current_integration_count)


class UserSession(RetryableModelMixin, models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="sessions", db_column="user_id")
    token_hash = models.CharField(max_length=255)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, null=True)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    objects = RetryableManager()

    class Meta:
        db_table = "user_sessions"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user"]),
            models.Index(fields=["token_hash"]),
            models.Index(fields=["expires_at"]),
        ]

    def __str__(self):
        return f"Session for {self.user.email} - {self.created_at}"

    @atomic_with_retry()
    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(days=7)
        super().save(*args, **kwargs)

    def is_expired(self):
        return timezone.now() > self.expires_at

    # Removed deactivate() method - sessions are now deleted instead of deactivated

    @classmethod
    @atomic_with_retry()
    def cleanup_expired_sessions(cls):
        cls.objects.filter(expires_at__lt=timezone.now()).delete()

    @classmethod
    @atomic_with_retry()
    def get_active_session(cls, token_hash):
        try:
            session = cls.objects.get(token_hash=token_hash, expires_at__gt=timezone.now())
            return session
        except cls.DoesNotExist:
            return None


class SupervisedUser(RetryableModelMixin, models.Model):
    """
    Critical model for supervisor-supervised user relationships
    This was missing from the current implementation
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="supervised_relationships", db_column="user_id")
    supervisor = models.ForeignKey(User, on_delete=models.CASCADE, related_name="supervised_users", db_column="supervisor_id")
    agent_token = models.CharField(max_length=255, null=True, blank=True)
    agent_last_heartbeat = models.DateTimeField(null=True, blank=True)
    agent_config = models.JSONField(null=True, blank=True)
    monitoring_enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = RetryableManager()

    class Meta:
        db_table = "supervised_users"
        ordering = ["-created_at"]
        unique_together = ["user", "supervisor"]
        indexes = [
            models.Index(fields=["user"]),
            models.Index(fields=["supervisor"]),
        ]

    def __str__(self):
        return f"{self.user.full_name} supervised by {self.supervisor.full_name}"

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.user == self.supervisor:
            raise ValidationError("A user cannot supervise themselves")

        # Ensure supervisor has supervisor role
        if self.supervisor.role not in ["admin", "supervisor"]:
            raise ValidationError("Supervisor must have admin or supervisor role")

    @atomic_with_retry()
    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class PasswordResetToken(RetryableModelMixin, models.Model):
    """
    Model for tracking password reset requests
    Stores 6-digit codes with expiration and attempt tracking
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="password_reset_tokens", db_column="user_id")
    code_hash = models.CharField(max_length=255, help_text="SHA256 hash of the 6-digit reset code")
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(help_text="Token expires after 1 hour")
    attempts = models.IntegerField(default=0, help_text="Number of verification attempts")
    is_used = models.BooleanField(default=False, help_text="Whether the token has been used successfully")
    is_invalidated = models.BooleanField(default=False, help_text="Whether the token was invalidated (max attempts)")

    objects = RetryableManager()

    class Meta:
        db_table = "password_reset_tokens"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user"]),
            models.Index(fields=["code_hash"]),
            models.Index(fields=["expires_at"]),
        ]

    def __str__(self):
        return f"Password reset for {self.user.email} - {self.created_at}"

    @atomic_with_retry()
    def save(self, *args, **kwargs):
        if not self.expires_at:
            # 1 hour expiration as per requirements
            self.expires_at = timezone.now() + timedelta(hours=1)
        super().save(*args, **kwargs)

    def is_expired(self):
        """Check if the reset token has expired"""
        return timezone.now() > self.expires_at

    def is_valid(self):
        """Check if the token is valid (not expired, not used, not invalidated, attempts < 5)"""
        return not self.is_expired() and not self.is_used and not self.is_invalidated and self.attempts < 5

    @atomic_with_retry()
    def increment_attempts(self):
        """Increment attempt count and invalidate if max attempts reached"""
        self.attempts += 1
        if self.attempts >= 5:
            self.is_invalidated = True
        self.save()

    @atomic_with_retry()
    def mark_as_used(self):
        """Mark the token as successfully used"""
        self.is_used = True
        self.save()

    @classmethod
    @atomic_with_retry()
    def cleanup_expired_tokens(cls):
        """Delete expired or used reset tokens"""
        cutoff_time = timezone.now() - timedelta(days=1)
        cls.objects.filter(
            models.Q(expires_at__lt=timezone.now()) | models.Q(is_used=True, created_at__lt=cutoff_time)
        ).delete()

    @classmethod
    @atomic_with_retry()
    def invalidate_user_tokens(cls, user):
        """Invalidate all reset tokens for a user"""
        cls.objects.filter(user=user, is_used=False, is_invalidated=False).update(is_invalidated=True)


class CompanyInvitation(RetryableModelMixin, models.Model):
    """
    Model for tracking company invitations to new employees
    Allows company users to invite others via email to join their company
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="invitations", db_column="company_id"
    )
    inviter = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="sent_invitations", db_column="inviter_id"
    )
    invitee_email = models.EmailField(
        validators=[EmailValidator()], help_text="Email address of the person being invited"
    )
    role = models.CharField(
        max_length=50, choices=User.ROLE_CHOICES, default="developer", help_text="Role for the invited user"
    )
    token = models.CharField(max_length=255, unique=True, help_text="Unique invitation token")
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(help_text="Invitation expires after 7 days")
    is_accepted = models.BooleanField(default=False, help_text="Whether the invitation has been accepted")
    accepted_at = models.DateTimeField(null=True, blank=True, help_text="When the invitation was accepted")
    accepted_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="accepted_invitations",
        null=True,
        blank=True,
        db_column="accepted_by_id",
        help_text="User who accepted the invitation",
    )

    objects = RetryableManager()

    class Meta:
        db_table = "company_invitations"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["company"]),
            models.Index(fields=["invitee_email"]),
            models.Index(fields=["token"]),
            models.Index(fields=["expires_at"]),
        ]
        # Ensure we don't send duplicate active invitations to the same email for the same company
        constraints = [
            models.UniqueConstraint(
                fields=["company", "invitee_email"],
                condition=models.Q(is_accepted=False, expires_at__gt=timezone.now()),
                name="unique_active_invitation_per_email_company",
            )
        ]

    def __str__(self):
        return f"Invitation to {self.invitee_email} from {self.company.name}"

    @atomic_with_retry()
    def save(self, *args, **kwargs):
        if not self.token:
            # Generate a secure random token
            import secrets

            self.token = secrets.token_urlsafe(32)

        if not self.expires_at:
            # 7 days expiration
            self.expires_at = timezone.now() + timedelta(days=7)

        super().save(*args, **kwargs)

    def is_expired(self):
        """Check if the invitation has expired"""
        return timezone.now() > self.expires_at

    def is_valid(self):
        """Check if the invitation is valid (not expired, not accepted)"""
        return not self.is_expired() and not self.is_accepted

    @atomic_with_retry()
    def accept(self, user):
        """Mark the invitation as accepted by a user"""
        if not self.is_valid():
            raise ValueError("Cannot accept an expired or already accepted invitation")

        self.is_accepted = True
        self.accepted_at = timezone.now()
        self.accepted_by = user
        self.save()

        # Associate the user with the company
        user.company = self.company
        user.role = self.role
        user.save()

    @classmethod
    @atomic_with_retry()
    def cleanup_expired_invitations(cls):
        """Delete expired invitations"""
        cutoff_time = timezone.now() - timedelta(days=30)
        cls.objects.filter(expires_at__lt=timezone.now(), created_at__lt=cutoff_time).delete()

    @classmethod
    @atomic_with_retry()
    def get_active_invitation(cls, token):
        """Get an active (valid) invitation by token"""
        try:
            invitation = cls.objects.get(
                token=token, is_accepted=False, expires_at__gt=timezone.now()
            )
            return invitation
        except cls.DoesNotExist:
            return None
