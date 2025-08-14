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
    name = models.CharField(max_length=255, unique=True)
    domain = models.CharField(max_length=255, unique=True)
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
        ("developer", "Developer"),
        ("manager", "Manager"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True, validators=[EmailValidator()])
    password = models.CharField(max_length=255, db_column="password_hash")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="developer")
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="users", null=True, blank=True)
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    date_joined = models.DateTimeField(auto_now_add=True, db_column="created_at")
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)
    last_login = models.DateTimeField(null=True, blank=True)
    timezone = models.CharField(max_length=50, default="UTC")

    username = None
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    objects = RetryableUserManager()

    class Meta:
        db_table = "authentication_user"
        ordering = ["-date_joined"]

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.email})"

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.email:
            self.email = self.email.lower()

        if self.company:
            email_domain = f"@{self.email.split('@')[1]}"
            if self.company.domain != email_domain:
                raise ValidationError(f"Email domain must match company domain: {self.company.domain}")

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
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="sessions")
    token_hash = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    user_agent = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    last_used = models.DateTimeField(auto_now=True)

    objects = RetryableManager()

    class Meta:
        db_table = "user_sessions"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "is_active"]),
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

    @atomic_with_retry()
    def deactivate(self):
        self.is_active = False
        self.save()

    @classmethod
    @atomic_with_retry()
    def cleanup_expired_sessions(cls):
        cls.objects.filter(expires_at__lt=timezone.now()).delete()

    @classmethod
    @atomic_with_retry()
    def get_active_session(cls, token_hash):
        try:
            session = cls.objects.get(token_hash=token_hash, is_active=True, expires_at__gt=timezone.now())
            session.last_used = timezone.now()
            session.save()
            return session
        except cls.DoesNotExist:
            return None
