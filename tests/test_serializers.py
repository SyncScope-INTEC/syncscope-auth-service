import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.authentication.models import Company
from apps.authentication.serializers import (
    CompanySerializer,
    PasswordChangeSerializer,
    UserLoginSerializer,
    UserProfileSerializer,
    UserRegistrationSerializer,
    UserSessionSerializer,
    UserUpdateSerializer,
)

User = get_user_model()


@pytest.mark.django_db
class TestCompanySerializer:

    def test_domain_validation_adds_at_symbol(self):
        """Test that domain validation adds @ symbol if missing."""
        data = {"name": "Test Company", "domain": "testcompany.com"}
        serializer = CompanySerializer(data=data)

        assert serializer.is_valid()
        assert serializer.validated_data["domain"] == "@testcompany.com"

    def test_domain_validation_keeps_at_symbol(self):
        """Test that domain validation keeps @ symbol if present."""
        data = {"name": "Test Company", "domain": "@testcompany.com"}
        serializer = CompanySerializer(data=data)

        assert serializer.is_valid()
        assert serializer.validated_data["domain"] == "@testcompany.com"


@pytest.mark.django_db
class TestUserRegistrationSerializer:

    def test_password_validation_weak_password(self):
        """Test that weak passwords are rejected."""
        data = {
            "email": "test@example.com",
            "first_name": "Test",
            "last_name": "User",
            "password": "123",
            "password_confirm": "123",
            "company_name": "Test Company",
        }
        serializer = UserRegistrationSerializer(data=data)

        assert not serializer.is_valid()
        assert "password" in serializer.errors

    def test_password_mismatch(self):
        """Test that password mismatch is detected."""
        data = {
            "email": "test@example.com",
            "first_name": "Test",
            "last_name": "User",
            "password": "strongpassword123",
            "password_confirm": "differentpassword123",
            "company_name": "Test Company",
        }
        serializer = UserRegistrationSerializer(data=data)

        assert not serializer.is_valid()
        assert "Passwords don't match" in str(serializer.errors)

    def test_company_domain_mismatch(self):
        """Test that email domain must match existing company domain."""
        # Create existing company with specific domain
        Company.objects.create(name="Existing Company", domain="@existing.com")

        data = {
            "email": "test@different.com",
            "first_name": "Test",
            "last_name": "User",
            "password": "strongpassword123",
            "password_confirm": "strongpassword123",
            "company_name": "Existing Company",
        }
        serializer = UserRegistrationSerializer(data=data)

        assert not serializer.is_valid()
        assert "Email domain must match company domain" in str(serializer.errors)

    def test_registration_without_company(self):
        """Test registration without company name."""
        data = {
            "email": "test@example.com",
            "first_name": "Test",
            "last_name": "User",
            "password": "strongpassword123",
            "password_confirm": "strongpassword123",
            "role": "developer",
        }
        serializer = UserRegistrationSerializer(data=data)

        assert serializer.is_valid()
        user = serializer.save()
        assert user.company is None

    def test_create_user_removes_confirm_fields(self):
        """Test that password_confirm and company_name are removed during creation."""
        data = {
            "email": "test@example.com",
            "first_name": "Test",
            "last_name": "User",
            "password": "strongpassword123",
            "password_confirm": "strongpassword123",
            "company_name": "Test Company",
        }
        serializer = UserRegistrationSerializer(data=data)

        assert serializer.is_valid()
        user = serializer.save()
        assert user.email == "test@example.com"
        assert user.company.name == "Test Company"


@pytest.mark.django_db
class TestUserLoginSerializer:

    def test_login_missing_email(self):
        """Test login validation with missing email."""
        data = {"password": "testpassword123"}
        serializer = UserLoginSerializer(data=data)

        assert not serializer.is_valid()
        assert "Must include email and password" in str(serializer.errors)

    def test_login_missing_password(self):
        """Test login validation with missing password."""
        data = {"email": "test@example.com"}
        serializer = UserLoginSerializer(data=data)

        assert not serializer.is_valid()
        assert "Must include email and password" in str(serializer.errors)

    def test_login_invalid_credentials(self):
        """Test login with invalid credentials."""
        data = {"email": "nonexistent@example.com", "password": "wrongpassword"}
        serializer = UserLoginSerializer(data=data)

        assert not serializer.is_valid()
        assert "Invalid credentials" in str(serializer.errors)

    def test_login_inactive_user(self, user):
        """Test login with inactive user."""
        user.is_active = False
        user.save()

        data = {"email": user.email, "password": "testpassword123"}
        serializer = UserLoginSerializer(data=data)

        assert not serializer.is_valid()
        assert "Account is disabled" in str(serializer.errors)

    def test_login_wrong_password_for_existing_user(self, user):
        """Test login with wrong password for existing user."""
        data = {"email": user.email, "password": "wrongpassword"}
        serializer = UserLoginSerializer(data=data)

        assert not serializer.is_valid()
        assert "Invalid credentials" in str(serializer.errors)

    def test_login_successful_authentication(self, user):
        """Test successful login authentication."""
        data = {"email": user.email, "password": "testpassword123"}

        from django.test import RequestFactory

        request = RequestFactory().post("/")

        serializer = UserLoginSerializer(data=data, context={"request": request})

        assert serializer.is_valid()
        assert serializer.validated_data["user"] == user

    def test_login_edge_case_empty_string_values(self):
        """Test login with empty string values to check field validation."""
        # This test checks field-level validation before custom validation
        data = {"email": "", "password": ""}
        serializer = UserLoginSerializer(data=data)

        assert not serializer.is_valid()
        assert "This field may not be blank" in str(serializer.errors)


@pytest.mark.django_db
class TestPasswordChangeSerializer:

    def test_incorrect_old_password(self, user):
        """Test validation with incorrect old password."""
        data = {
            "old_password": "wrongpassword",
            "new_password": "newstrongpassword123",
            "new_password_confirm": "newstrongpassword123",
        }

        from django.test import RequestFactory

        request = RequestFactory().post("/")
        request.user = user

        serializer = PasswordChangeSerializer(data=data, context={"request": request})

        assert not serializer.is_valid()
        assert "Old password is incorrect" in str(serializer.errors)

    def test_new_password_mismatch(self, user):
        """Test validation with new password mismatch."""
        data = {
            "old_password": "testpassword123",
            "new_password": "newstrongpassword123",
            "new_password_confirm": "differentpassword123",
        }

        from django.test import RequestFactory

        request = RequestFactory().post("/")
        request.user = user

        serializer = PasswordChangeSerializer(data=data, context={"request": request})

        assert not serializer.is_valid()
        assert "New passwords don't match" in str(serializer.errors)

    def test_weak_new_password(self, user):
        """Test validation with weak new password."""
        data = {"old_password": "testpassword123", "new_password": "123", "new_password_confirm": "123"}

        from django.test import RequestFactory

        request = RequestFactory().post("/")
        request.user = user

        serializer = PasswordChangeSerializer(data=data, context={"request": request})

        assert not serializer.is_valid()
        assert "new_password" in serializer.errors

    def test_password_change_save(self, user):
        """Test successful password change."""
        old_password_hash = user.password

        data = {
            "old_password": "testpassword123",
            "new_password": "newstrongpassword123",
            "new_password_confirm": "newstrongpassword123",
        }

        from django.test import RequestFactory

        request = RequestFactory().post("/")
        request.user = user

        serializer = PasswordChangeSerializer(data=data, context={"request": request})

        assert serializer.is_valid()
        updated_user = serializer.save()

        assert updated_user.password != old_password_hash
        assert updated_user.check_password("newstrongpassword123")


@pytest.mark.django_db
class TestUserUpdateSerializer:

    def test_update_partial_fields(self, user):
        """Test updating partial user fields."""
        data = {"first_name": "Updated"}
        serializer = UserUpdateSerializer(user, data=data, partial=True)

        assert serializer.is_valid()
        updated_user = serializer.save()

        assert updated_user.first_name == "Updated"
        assert updated_user.last_name == user.last_name  # Should remain unchanged

    def test_update_avatar_url(self, user):
        """Test updating avatar URL."""
        data = {"avatar_url": "https://example.com/avatar.jpg"}
        serializer = UserUpdateSerializer(user, data=data, partial=True)

        assert serializer.is_valid()
        updated_user = serializer.save()

        assert updated_user.avatar_url == "https://example.com/avatar.jpg"


@pytest.mark.django_db
class TestUserSessionSerializer:

    def test_session_serialization(self, user_session):
        """Test user session serialization."""
        session, token = user_session
        serializer = UserSessionSerializer(session)

        data = serializer.data
        assert data["id"] == str(session.id)
        assert data["is_active"] == session.is_active
        assert data["user_agent"] == session.user_agent
        assert "created_at" in data
        assert "expires_at" in data
        assert "last_used" in data

        # Check that sensitive data is not exposed
        assert "token_hash" not in data


@pytest.mark.django_db
class TestUserProfileSerializer:

    def test_profile_serialization_with_company(self, user):
        """Test user profile serialization with company."""
        serializer = UserProfileSerializer(user)
        data = serializer.data

        assert data["id"] == str(user.id)
        assert data["email"] == user.email
        assert data["first_name"] == user.first_name
        assert data["last_name"] == user.last_name
        assert data["full_name"] == user.full_name
        assert data["role"] == user.role

        if user.company:
            assert "company" in data
            assert data["company"]["name"] == user.company.name

    def test_profile_serialization_without_company(self):
        """Test user profile serialization without company."""
        user = User.objects.create_user(
            email="nocompany@example.com", password="testpassword123", first_name="No", last_name="Company", company=None
        )

        serializer = UserProfileSerializer(user)
        data = serializer.data

        assert data["company"] is None
        assert data["full_name"] == "No Company"
