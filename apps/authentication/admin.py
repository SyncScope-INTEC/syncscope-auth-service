from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import Company, SupervisedUser, User, UserSession


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ["name", "domain", "created_at"]
    list_filter = ["created_at"]
    search_fields = ["name", "domain"]
    readonly_fields = ["id", "created_at", "updated_at"]
    ordering = ["-created_at"]


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ["email", "first_name", "last_name", "role", "company", "is_active"]
    list_filter = ["role", "is_active", "is_staff", "company", "date_joined"]
    search_fields = ["email", "first_name", "last_name"]
    readonly_fields = ["id", "date_joined", "updated_at", "last_login"]
    ordering = ["-date_joined"]

    fieldsets = (
        (None, {"fields": ("id", "email", "password")}),
        ("Personal info", {"fields": ("first_name", "last_name", "timezone")}),
        ("Company info", {"fields": ("company", "role")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Important dates", {"fields": ("last_login", "date_joined", "updated_at")}),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "password1", "password2", "first_name", "last_name", "role", "company"),
            },
        ),
    )


@admin.register(UserSession)
class UserSessionAdmin(admin.ModelAdmin):
    list_display = ["user", "created_at", "expires_at", "ip_address"]
    list_filter = ["created_at", "expires_at"]
    search_fields = ["user__email", "user__first_name", "user__last_name", "ip_address"]
    readonly_fields = ["id", "token_hash", "created_at"]
    ordering = ["-created_at"]

    fieldsets = (
        (None, {"fields": ("id", "user")}),
        ("Session info", {"fields": ("token_hash", "user_agent", "ip_address")}),
        ("Timestamps", {"fields": ("created_at", "expires_at")}),
    )


@admin.register(SupervisedUser)
class SupervisedUserAdmin(admin.ModelAdmin):
    list_display = ["user", "supervisor", "monitoring_enabled", "created_at"]
    list_filter = ["monitoring_enabled", "created_at"]
    search_fields = ["user__email", "user__first_name", "supervisor__email", "supervisor__first_name"]
    readonly_fields = ["id", "created_at", "updated_at", "agent_last_heartbeat"]
    ordering = ["-created_at"]

    fieldsets = (
        (None, {"fields": ("id", "user", "supervisor")}),
        ("Monitoring", {"fields": ("monitoring_enabled", "agent_token", "agent_config")}),
        ("Status", {"fields": ("agent_last_heartbeat",)}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )
