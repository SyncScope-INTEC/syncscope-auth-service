import os

import django
import pytest
from django.conf import settings

# Configure Django settings before importing anything else
if not settings.configured:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    django.setup()

from unittest.mock import Mock, patch

from django.contrib import admin
from django.contrib.admin.sites import AdminSite
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory, TestCase

from apps.authentication.admin import CompanyAdmin, UserAdmin, UserSessionAdmin
from apps.authentication.models import Company, User, UserSession


class TestCompanyAdmin:
    """Test CompanyAdmin configuration."""

    def test_admin_registration(self):
        """Test that CompanyAdmin is registered."""
        assert Company in admin.site._registry
        assert isinstance(admin.site._registry[Company], CompanyAdmin)

    def test_list_display(self):
        """Test list_display configuration."""
        company_admin = CompanyAdmin(Company, admin.site)
        expected_fields = ["name", "domain", "created_at"]
        assert company_admin.list_display == expected_fields

    def test_list_filter(self):
        """Test list_filter configuration."""
        company_admin = CompanyAdmin(Company, admin.site)
        expected_filters = ["created_at"]
        assert company_admin.list_filter == expected_filters

    def test_search_fields(self):
        """Test search_fields configuration."""
        company_admin = CompanyAdmin(Company, admin.site)
        expected_fields = ["name", "domain"]
        assert company_admin.search_fields == expected_fields

    def test_readonly_fields(self):
        """Test readonly_fields configuration."""
        company_admin = CompanyAdmin(Company, admin.site)
        expected_fields = ["id", "created_at", "updated_at"]
        assert company_admin.readonly_fields == expected_fields

    def test_ordering(self):
        """Test ordering configuration."""
        company_admin = CompanyAdmin(Company, admin.site)
        expected_ordering = ["-created_at"]
        assert company_admin.ordering == expected_ordering

    def test_inherits_from_model_admin(self):
        """Test that CompanyAdmin inherits from ModelAdmin."""
        assert issubclass(CompanyAdmin, admin.ModelAdmin)


class TestUserAdmin:
    """Test UserAdmin configuration."""

    def test_admin_registration(self):
        """Test that UserAdmin is registered."""
        assert User in admin.site._registry
        assert isinstance(admin.site._registry[User], UserAdmin)

    def test_list_display(self):
        """Test list_display configuration."""
        user_admin = UserAdmin(User, admin.site)
        expected_fields = ["email", "first_name", "last_name", "role", "plan", "company", "is_active"]
        assert user_admin.list_display == expected_fields

    def test_list_filter(self):
        """Test list_filter configuration."""
        user_admin = UserAdmin(User, admin.site)
        expected_filters = ["role", "plan", "is_active", "is_staff", "company", "date_joined"]
        assert user_admin.list_filter == expected_filters

    def test_search_fields(self):
        """Test search_fields configuration."""
        user_admin = UserAdmin(User, admin.site)
        expected_fields = ["email", "first_name", "last_name"]
        assert user_admin.search_fields == expected_fields

    def test_readonly_fields(self):
        """Test readonly_fields configuration."""
        user_admin = UserAdmin(User, admin.site)
        expected_fields = ["id", "date_joined", "updated_at", "last_login"]
        assert user_admin.readonly_fields == expected_fields

    def test_ordering(self):
        """Test ordering configuration."""
        user_admin = UserAdmin(User, admin.site)
        expected_ordering = ["-date_joined"]
        assert user_admin.ordering == expected_ordering

    def test_fieldsets(self):
        """Test fieldsets configuration."""
        user_admin = UserAdmin(User, admin.site)
        expected_fieldsets = (
            (None, {"fields": ("id", "email", "password")}),
            ("Personal info", {"fields": ("first_name", "last_name", "phone_number", "timezone")}),
            ("Company info", {"fields": ("company", "role", "plan")}),
            ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
            ("Important dates", {"fields": ("last_login", "date_joined", "updated_at")}),
        )
        assert user_admin.fieldsets == expected_fieldsets

    def test_add_fieldsets(self):
        """Test add_fieldsets configuration."""
        user_admin = UserAdmin(User, admin.site)
        expected_add_fieldsets = (
            (
                None,
                {
                    "classes": ("wide",),
                    "fields": (
                        "email",
                        "password1",
                        "password2",
                        "first_name",
                        "last_name",
                        "phone_number",
                        "role",
                        "plan",
                        "company",
                    ),
                },
            ),
        )
        assert user_admin.add_fieldsets == expected_add_fieldsets

    def test_inherits_from_base_user_admin(self):
        """Test that UserAdmin inherits from BaseUserAdmin."""
        assert issubclass(UserAdmin, BaseUserAdmin)


class TestUserSessionAdmin:
    """Test UserSessionAdmin configuration."""

    def test_admin_registration(self):
        """Test that UserSessionAdmin is registered."""
        assert UserSession in admin.site._registry
        assert isinstance(admin.site._registry[UserSession], UserSessionAdmin)

    def test_list_display(self):
        """Test list_display configuration."""
        session_admin = UserSessionAdmin(UserSession, admin.site)
        expected_fields = ["user", "is_active", "created_at", "expires_at", "last_used", "ip_address"]
        assert session_admin.list_display == expected_fields

    def test_list_filter(self):
        """Test list_filter configuration."""
        session_admin = UserSessionAdmin(UserSession, admin.site)
        expected_filters = ["created_at", "expires_at"]
        assert session_admin.list_filter == expected_filters

    def test_search_fields(self):
        """Test search_fields configuration."""
        session_admin = UserSessionAdmin(UserSession, admin.site)
        expected_fields = ["user__email", "user__first_name", "user__last_name", "ip_address"]
        assert session_admin.search_fields == expected_fields

    def test_readonly_fields(self):
        """Test readonly_fields configuration."""
        session_admin = UserSessionAdmin(UserSession, admin.site)
        expected_fields = ["id", "token_hash", "created_at", "last_used"]
        assert session_admin.readonly_fields == expected_fields

    def test_ordering(self):
        """Test ordering configuration."""
        session_admin = UserSessionAdmin(UserSession, admin.site)
        expected_ordering = ["-created_at"]
        assert session_admin.ordering == expected_ordering

    def test_fieldsets(self):
        """Test fieldsets configuration."""
        session_admin = UserSessionAdmin(UserSession, admin.site)
        expected_fieldsets = (
            (None, {"fields": ("id", "user", "is_active")}),
            ("Session info", {"fields": ("token_hash", "user_agent", "ip_address")}),
            ("Timestamps", {"fields": ("created_at", "expires_at", "last_used")}),
        )
        assert session_admin.fieldsets == expected_fieldsets

    def test_actions_configured(self):
        """Test that custom actions are configured."""
        session_admin = UserSessionAdmin(UserSession, admin.site)
        expected_actions = ["deactivate_sessions"]
        assert session_admin.actions == expected_actions

    def test_deactivate_sessions_method_exists(self):
        """Test that deactivate_sessions method exists."""
        session_admin = UserSessionAdmin(UserSession, admin.site)
        assert hasattr(session_admin, "deactivate_sessions")
        assert callable(getattr(session_admin, "deactivate_sessions"))

    def test_deactivate_sessions_short_description(self):
        """Test that deactivate_sessions has the correct short description."""
        session_admin = UserSessionAdmin(UserSession, admin.site)
        assert session_admin.deactivate_sessions.short_description == "Deactivate selected sessions"

    def test_inherits_from_model_admin(self):
        """Test that UserSessionAdmin inherits from ModelAdmin."""
        assert issubclass(UserSessionAdmin, admin.ModelAdmin)


@pytest.mark.django_db
class TestUserSessionAdminActions:
    """Test UserSessionAdmin custom actions functionality."""

    def setup_method(self):
        """Set up test data."""
        self.factory = RequestFactory()
        self.site = AdminSite()
        self.session_admin = UserSessionAdmin(UserSession, self.site)

    def test_deactivate_sessions_action(self):
        """Test the deactivate_sessions action functionality."""
        # Create a mock request
        request = self.factory.post("/admin/")

        # Add session and messages manually since we don't need full middleware
        request.session = {}
        setattr(request, "_messages", FallbackStorage(request))

        # Create a mock queryset
        mock_queryset = Mock()
        mock_queryset.delete.return_value = None
        mock_queryset.count.return_value = 3

        # Test the action
        self.session_admin.deactivate_sessions(request, mock_queryset)

        # Verify the queryset was deleted
        mock_queryset.delete.assert_called_once()
        mock_queryset.count.assert_called_once()

    @patch.object(UserSessionAdmin, "message_user")
    def test_deactivate_sessions_message(self, mock_message_user):
        """Test that deactivate_sessions sends the correct message."""
        # Create a mock request
        request = self.factory.post("/admin/")

        # Create a mock queryset
        mock_queryset = Mock()
        mock_queryset.delete.return_value = None
        mock_queryset.count.return_value = 5

        # Test the action
        self.session_admin.deactivate_sessions(request, mock_queryset)

        # Verify the message was sent
        mock_message_user.assert_called_once_with(request, "Successfully deactivated 5 sessions.")

    @patch.object(UserSessionAdmin, "message_user")
    def test_deactivate_sessions_single_session_message(self, mock_message_user):
        """Test message for single session deactivation."""
        request = self.factory.post("/admin/")

        mock_queryset = Mock()
        mock_queryset.delete.return_value = None
        mock_queryset.count.return_value = 1

        self.session_admin.deactivate_sessions(request, mock_queryset)

        mock_message_user.assert_called_once_with(request, "Successfully deactivated 1 session.")

    @patch.object(UserSessionAdmin, "message_user")
    def test_deactivate_sessions_zero_sessions_message(self, mock_message_user):
        """Test message for zero session deactivation."""
        request = self.factory.post("/admin/")

        mock_queryset = Mock()
        mock_queryset.delete.return_value = None
        mock_queryset.count.return_value = 0

        self.session_admin.deactivate_sessions(request, mock_queryset)

        mock_message_user.assert_called_once_with(request, "Successfully deactivated 0 sessions.")


class TestAdminImports:
    """Test admin module imports and structure."""

    def test_required_imports_exist(self):
        """Test that all required imports are available."""
        from apps.authentication import admin as auth_admin

        # Test Django imports
        assert hasattr(auth_admin, "admin")
        assert hasattr(auth_admin, "BaseUserAdmin")

        # Test model imports
        assert hasattr(auth_admin, "Company")
        assert hasattr(auth_admin, "User")
        assert hasattr(auth_admin, "UserSession")

        # Test admin class definitions
        assert hasattr(auth_admin, "CompanyAdmin")
        assert hasattr(auth_admin, "UserAdmin")
        assert hasattr(auth_admin, "UserSessionAdmin")

    def test_admin_classes_are_properly_defined(self):
        """Test that admin classes are properly defined classes."""
        assert isinstance(CompanyAdmin, type)
        assert isinstance(UserAdmin, type)
        assert isinstance(UserSessionAdmin, type)

    def test_admin_decorators_applied(self):
        """Test that @admin.register decorators are properly applied."""
        # Check that models are registered in the admin site
        registered_models = [model._meta.model for model in admin.site._registry.keys()]

        assert Company in registered_models
        assert User in registered_models
        assert UserSession in registered_models


class TestAdminConfiguration:
    """Test overall admin configuration."""

    def test_all_admin_classes_have_required_attributes(self):
        """Test that all admin classes have the expected attributes."""
        # CompanyAdmin attributes
        company_admin = CompanyAdmin(Company, admin.site)
        required_company_attrs = ["list_display", "list_filter", "search_fields", "readonly_fields", "ordering"]
        for attr in required_company_attrs:
            assert hasattr(company_admin, attr)
            assert getattr(company_admin, attr) is not None

        # UserAdmin attributes
        user_admin = UserAdmin(User, admin.site)
        required_user_attrs = [
            "list_display",
            "list_filter",
            "search_fields",
            "readonly_fields",
            "ordering",
            "fieldsets",
            "add_fieldsets",
        ]
        for attr in required_user_attrs:
            assert hasattr(user_admin, attr)
            assert getattr(user_admin, attr) is not None

        # UserSessionAdmin attributes
        session_admin = UserSessionAdmin(UserSession, admin.site)
        required_session_attrs = [
            "list_display",
            "list_filter",
            "search_fields",
            "readonly_fields",
            "ordering",
            "fieldsets",
            "actions",
        ]
        for attr in required_session_attrs:
            assert hasattr(session_admin, attr)
            assert getattr(session_admin, attr) is not None

    def test_admin_classes_inheritance(self):
        """Test that admin classes inherit from correct base classes."""
        assert issubclass(CompanyAdmin, admin.ModelAdmin)
        assert issubclass(UserAdmin, BaseUserAdmin)
        assert issubclass(UserSessionAdmin, admin.ModelAdmin)

    def test_readonly_fields_are_lists(self):
        """Test that readonly_fields are properly configured as lists."""
        company_admin = CompanyAdmin(Company, admin.site)
        user_admin = UserAdmin(User, admin.site)
        session_admin = UserSessionAdmin(UserSession, admin.site)

        assert isinstance(company_admin.readonly_fields, (list, tuple))
        assert isinstance(user_admin.readonly_fields, (list, tuple))
        assert isinstance(session_admin.readonly_fields, (list, tuple))

    def test_list_display_fields_are_valid(self):
        """Test that list_display fields are non-empty."""
        company_admin = CompanyAdmin(Company, admin.site)
        user_admin = UserAdmin(User, admin.site)
        session_admin = UserSessionAdmin(UserSession, admin.site)

        assert len(company_admin.list_display) > 0
        assert len(user_admin.list_display) > 0
        assert len(session_admin.list_display) > 0

        # Check that all list_display items are strings
        assert all(isinstance(field, str) for field in company_admin.list_display)
        assert all(isinstance(field, str) for field in user_admin.list_display)
        assert all(isinstance(field, str) for field in session_admin.list_display)
