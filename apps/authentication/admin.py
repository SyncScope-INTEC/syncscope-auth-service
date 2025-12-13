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
        ("Personal info", {"fields": ("first_name", "last_name", "phone_number", "timezone")}),
        ("Company info", {"fields": ("company", "role")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Important dates", {"fields": ("last_login", "date_joined", "updated_at")}),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "password1", "password2", "first_name", "last_name", "phone_number", "role", "company"),
            },
        ),
    )


@admin.register(UserSession)
class UserSessionAdmin(admin.ModelAdmin):
    list_display = ["user", "is_active", "created_at", "expires_at", "last_used", "ip_address"]
    list_filter = ["created_at", "expires_at"]
    search_fields = ["user__email", "user__first_name", "user__last_name", "ip_address"]
    readonly_fields = ["id", "token_hash", "created_at", "last_used"]
    ordering = ["-created_at"]
    actions = ["deactivate_sessions"]

    fieldsets = (
        (None, {"fields": ("id", "user", "is_active")}),
        ("Session info", {"fields": ("token_hash", "user_agent", "ip_address")}),
        ("Timestamps", {"fields": ("created_at", "expires_at", "last_used")}),
    )

    def is_active(self, obj):
        """Check if session is active (not expired)"""
        from django.utils import timezone

        return obj.expires_at > timezone.now()

    is_active.boolean = True
    is_active.short_description = "Active"

    def last_used(self, obj):
        """Show created_at as last_used for compatibility"""
        return obj.created_at

    last_used.short_description = "Last Used"

    def deactivate_sessions(self, request, queryset):
        """Deactivate selected sessions by deleting them"""
        count = queryset.count()
        queryset.delete()
        self.message_user(request, f"Successfully deactivated {count} session{'s' if count != 1 else ''}.")

    deactivate_sessions.short_description = "Deactivate selected sessions"


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
