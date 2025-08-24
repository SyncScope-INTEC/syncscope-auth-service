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

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True, validators=[EmailValidator()])
    password = models.CharField(max_length=255, db_column="password_hash")
    first_name = models.CharField(max_length=100, null=True, blank=True)
    last_name = models.CharField(max_length=100, null=True, blank=True)
    role = models.CharField(max_length=50, choices=ROLE_CHOICES, default="developer")
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
