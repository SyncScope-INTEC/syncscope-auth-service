"""
Tests for account setup functionality (Stripe integration flow)
Tests the setup-account endpoint, change-initial-password endpoint,
and login behavior with requires_password_change flag.
"""

import pytest
from unittest.mock import patch, MagicMock
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.authentication.models import User
from apps.authentication.utils import generate_temp_password

User = get_user_model()


@pytest.fixture
def api_client():
    """Create an API client for testing"""
    return APIClient()


@pytest.mark.django_db
class TestSetupAccountEndpoint:
    """Tests for POST /auth/setup-account/ endpoint"""

    @patch("apps.authentication.views.send_welcome_email")
    def test_setup_account_creates_new_user(self, mock_send_email, api_client):
        """Test that setup-account creates a new user with temporary password"""
        mock_send_email.return_value = True

        url = reverse("setup_account")
        data = {"email": "newuser@example.com", "first_name": "John", "last_name": "Doe", "plan": "growth"}

        response = api_client.post(url, data)

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["message"] == "Account created successfully. Welcome email sent with temporary password."
        assert response.data["email"] == "newuser@example.com"
        assert response.data["user_created"] is True
        assert "user_id" in response.data

        # Verify user was created in database
        user = User.objects.get(email="newuser@example.com")
        assert user.first_name == "John"
        assert user.last_name == "Doe"
        assert user.plan == "growth"
        assert user.requires_password_change is True

        # Verify welcome email was sent with correct parameters
        mock_send_email.assert_called_once()
        call_args = mock_send_email.call_args[0]
        assert call_args[0] == "newuser@example.com"  # email
        assert call_args[1] == "John Doe"  # user_name
        assert len(call_args[2]) == 12  # temp_password (12 chars)
        assert call_args[3] == "growth"  # plan

    @patch("apps.authentication.views.send_welcome_email")
    def test_setup_account_updates_existing_user(self, mock_send_email, api_client):
        """Test that setup-account updates existing user's password"""
        mock_send_email.return_value = True

        # Create existing user
        existing_user = User.objects.create_user(
            email="existing@example.com", password="oldpassword123", first_name="Jane", last_name="Smith", plan="starter"
        )
        old_password_hash = existing_user.password

        url = reverse("setup_account")
        data = {"email": "existing@example.com", "first_name": "Jane", "last_name": "Updated", "plan": "enterprise"}

        response = api_client.post(url, data)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["message"] == "Account updated successfully. Welcome email sent with temporary password."
        assert response.data["user_created"] is False
        assert response.data["email"] == "existing@example.com"

        # Verify user was updated
        existing_user.refresh_from_db()
        assert existing_user.last_name == "Updated"
        assert existing_user.plan == "enterprise"
        assert existing_user.requires_password_change is True
        assert existing_user.password != old_password_hash  # Password was changed

        # Verify welcome email was sent
        mock_send_email.assert_called_once()

    @patch("apps.authentication.views.send_welcome_email")
    def test_setup_account_email_only_required(self, mock_send_email, api_client):
        """Test that only email is required for setup-account"""
        mock_send_email.return_value = True

        url = reverse("setup_account")
        data = {"email": "minimal@example.com"}

        response = api_client.post(url, data)

        assert response.status_code == status.HTTP_201_CREATED

        # Verify user was created with defaults
        user = User.objects.get(email="minimal@example.com")
        assert user.first_name == "User"  # Default
        assert user.last_name == ""
        assert user.plan == "starter"  # Default
        assert user.requires_password_change is True

    def test_setup_account_missing_email(self, api_client):
        """Test that setup-account returns error when email is missing"""
        url = reverse("setup_account")
        data = {"first_name": "John"}

        response = api_client.post(url, data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "email" in response.data

    @patch("apps.authentication.views.send_welcome_email")
    def test_setup_account_email_send_failure(self, mock_send_email, api_client):
        """Test that setup-account returns error when email fails to send"""
        mock_send_email.return_value = False

        url = reverse("setup_account")
        data = {"email": "test@example.com"}

        response = api_client.post(url, data)

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "failed to send welcome email" in response.data["error"].lower()

    @patch("apps.authentication.views.send_welcome_email")
    def test_setup_account_normalizes_email_to_lowercase(self, mock_send_email, api_client):
        """Test that email is normalized to lowercase"""
        mock_send_email.return_value = True

        url = reverse("setup_account")
        data = {"email": "TestUser@EXAMPLE.COM"}

        response = api_client.post(url, data)

        assert response.status_code == status.HTTP_201_CREATED

        # Verify email was normalized
        user = User.objects.get(email="testuser@example.com")
        assert user.email == "testuser@example.com"


@pytest.mark.django_db
class TestLoginWithPasswordChangeRequired:
    """Tests for login behavior when requires_password_change is True"""

    def test_login_with_requires_password_change_flag(self, api_client):
        """Test that login returns requires_password_change flag"""
        # Create user with requires_password_change=True
        user = User.objects.create_user(
            email="temppass@example.com",
            password="TempPass123!",
            first_name="Temp",
            last_name="User",
            requires_password_change=True,
        )

        url = reverse("login")
        data = {"email": "temppass@example.com", "password": "TempPass123!"}

        response = api_client.post(url, data)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["requires_password_change"] is True
        assert "must change your temporary password" in response.data["message"].lower()
        assert "tokens" in response.data
        assert "session_token" in response.data

    def test_login_without_requires_password_change_flag(self, api_client):
        """Test that login works normally when requires_password_change is False"""
        # Create normal user
        user = User.objects.create_user(
            email="normal@example.com",
            password="NormalPass123!",
            first_name="Normal",
            last_name="User",
            requires_password_change=False,
        )

        url = reverse("login")
        data = {"email": "normal@example.com", "password": "NormalPass123!"}

        response = api_client.post(url, data)

        assert response.status_code == status.HTTP_200_OK
        assert "requires_password_change" not in response.data or response.data.get("requires_password_change") is False
        assert response.data["message"] == "Login successful"


@pytest.mark.django_db
class TestChangeInitialPasswordEndpoint:
    """Tests for POST /auth/change-initial-password/ endpoint"""

    def test_change_initial_password_success(self, api_client):
        """Test successful password change from temporary to permanent"""
        # Create user with temporary password
        user = User.objects.create_user(
            email="temp@example.com",
            password="TempPass123!",
            first_name="Temp",
            last_name="User",
            requires_password_change=True,
        )

        # Login to get auth token
        login_url = reverse("login")
        login_data = {"email": "temp@example.com", "password": "TempPass123!"}
        login_response = api_client.post(login_url, login_data)
        access_token = login_response.data["tokens"]["access"]

        # Change password
        url = reverse("change_initial_password")
        data = {
            "temp_password": "TempPass123!",
            "new_password": "NewSecurePass123!",
            "new_password_confirm": "NewSecurePass123!",
        }

        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
        response = api_client.post(url, data)

        assert response.status_code == status.HTTP_200_OK
        assert "Password changed successfully" in response.data["message"]
        assert "tokens" in response.data

        # Verify password was changed and flag cleared
        user.refresh_from_db()
        assert user.requires_password_change is False
        assert user.check_password("NewSecurePass123!") is True
        assert user.check_password("TempPass123!") is False

    def test_change_initial_password_wrong_temp_password(self, api_client):
        """Test that wrong temporary password is rejected"""
        user = User.objects.create_user(email="temp@example.com", password="TempPass123!", requires_password_change=True)

        # Login
        login_url = reverse("login")
        login_response = api_client.post(login_url, {"email": "temp@example.com", "password": "TempPass123!"})
        access_token = login_response.data["tokens"]["access"]

        # Try to change with wrong temp password
        url = reverse("change_initial_password")
        data = {
            "temp_password": "WrongPassword!",
            "new_password": "NewSecurePass123!",
            "new_password_confirm": "NewSecurePass123!",
        }

        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
        response = api_client.post(url, data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "temp_password" in response.data or "Temporary password is incorrect" in str(response.data)

    def test_change_initial_password_mismatch(self, api_client):
        """Test that password confirmation mismatch is rejected"""
        user = User.objects.create_user(email="temp@example.com", password="TempPass123!", requires_password_change=True)

        # Login
        login_url = reverse("login")
        login_response = api_client.post(login_url, {"email": "temp@example.com", "password": "TempPass123!"})
        access_token = login_response.data["tokens"]["access"]

        # Try to change with mismatched passwords
        url = reverse("change_initial_password")
        data = {
            "temp_password": "TempPass123!",
            "new_password": "NewSecurePass123!",
            "new_password_confirm": "DifferentPass123!",
        }

        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
        response = api_client.post(url, data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "don't match" in str(response.data).lower()

    def test_change_initial_password_weak_password(self, api_client):
        """Test that weak new password is rejected"""
        user = User.objects.create_user(email="temp@example.com", password="TempPass123!", requires_password_change=True)

        # Login
        login_url = reverse("login")
        login_response = api_client.post(login_url, {"email": "temp@example.com", "password": "TempPass123!"})
        access_token = login_response.data["tokens"]["access"]

        # Try to change to weak password
        url = reverse("change_initial_password")
        data = {"temp_password": "TempPass123!", "new_password": "123", "new_password_confirm": "123"}

        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
        response = api_client.post(url, data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_change_initial_password_requires_authentication(self, api_client):
        """Test that endpoint requires authentication"""
        url = reverse("change_initial_password")
        data = {
            "temp_password": "TempPass123!",
            "new_password": "NewSecurePass123!",
            "new_password_confirm": "NewSecurePass123!",
        }

        response = api_client.post(url, data)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestTempPasswordGeneration:
    """Tests for temporary password generation utility"""

    def test_generate_temp_password_length(self):
        """Test that generated password is 12 characters"""
        password = generate_temp_password()
        assert len(password) == 12

    def test_generate_temp_password_has_required_chars(self):
        """Test that generated password has all required character types"""
        password = generate_temp_password()

        has_uppercase = any(c.isupper() for c in password)
        has_lowercase = any(c.islower() for c in password)
        has_digit = any(c.isdigit() for c in password)
        has_special = any(c in "!@#$%" for c in password)

        assert has_uppercase, "Password should contain at least one uppercase letter"
        assert has_lowercase, "Password should contain at least one lowercase letter"
        assert has_digit, "Password should contain at least one digit"
        assert has_special, "Password should contain at least one special character"

    def test_generate_temp_password_uniqueness(self):
        """Test that generated passwords are unique (random)"""
        passwords = [generate_temp_password() for _ in range(10)]
        # All passwords should be different
        assert len(set(passwords)) == 10


@pytest.mark.django_db
class TestEndToEndAccountSetupFlow:
    """Integration tests for the complete account setup flow"""

    @patch("apps.authentication.views.send_welcome_email")
    def test_complete_stripe_account_setup_flow(self, mock_send_email, api_client):
        """
        Test complete flow:
        1. Setup account (creates user with temp password)
        2. Login (returns requires_password_change=True)
        3. Change password (clears flag)
        4. Login again (normal login)
        """
        mock_send_email.return_value = True

        # Step 1: Setup account
        setup_url = reverse("setup_account")
        setup_data = {"email": "customer@example.com", "first_name": "Stripe", "last_name": "Customer", "plan": "growth"}
        setup_response = api_client.post(setup_url, setup_data)

        assert setup_response.status_code == status.HTTP_201_CREATED

        # Extract temp password from mock call
        temp_password = mock_send_email.call_args[0][2]

        # Step 2: Login with temp password
        login_url = reverse("login")
        login_data = {"email": "customer@example.com", "password": temp_password}
        login_response = api_client.post(login_url, login_data)

        assert login_response.status_code == status.HTTP_200_OK
        assert login_response.data["requires_password_change"] is True

        access_token = login_response.data["tokens"]["access"]

        # Step 3: Change password
        change_pwd_url = reverse("change_initial_password")
        change_pwd_data = {
            "temp_password": temp_password,
            "new_password": "MyNewSecurePass123!",
            "new_password_confirm": "MyNewSecurePass123!",
        }
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
        change_response = api_client.post(change_pwd_url, change_pwd_data)

        assert change_response.status_code == status.HTTP_200_OK

        # Step 4: Login again with new password (should be normal login)
        api_client.credentials()  # Clear auth
        login2_data = {"email": "customer@example.com", "password": "MyNewSecurePass123!"}
        login2_response = api_client.post(login_url, login2_data)

        assert login2_response.status_code == status.HTTP_200_OK
        assert login2_response.data.get("requires_password_change", False) is False
        assert login2_response.data["message"] == "Login successful"
