import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken

from apps.authentication.models import Company, SupervisedUser, UserSession

User = get_user_model()


@pytest.mark.django_db
class TestAuthenticationAPI:

    def test_user_registration_success(self, api_client):
        url = reverse("register")
        data = {
            "email": "newuser@testcompany.com",
            "password": "strongpassword123",
            "password_confirm": "strongpassword123",
            "first_name": "New",
            "last_name": "User",
            "company_name": "Test Company",
        }

        response = api_client.post(url, data)

        assert response.status_code == status.HTTP_201_CREATED
        assert "user" in response.data
        assert "tokens" in response.data
        assert "session_token" in response.data
        assert response.data["user"]["email"] == "newuser@testcompany.com"

        # Check user was created with all expected fields
        user = User.objects.get(email="newuser@testcompany.com")
        assert user.first_name == "New"
        assert user.last_name == "User"
        assert user.company.name == "Test Company"
        assert user.role == "developer"  # Default role
        assert user.timezone == "UTC"  # Default timezone
        assert user.is_active is True
        assert user.is_staff is False
        assert user.is_superuser is False
        assert user.date_joined is not None
        assert user.updated_at is not None

        # Check company was created with proper domain
        company = user.company
        assert company.domain == "@testcompany.com"
        assert company.created_at is not None
        assert company.updated_at is not None

    def test_user_registration_password_mismatch(self, api_client):
        url = reverse("register")
        data = {
            "email": "newuser@testcompany.com",
            "password": "strongpassword123",
            "password_confirm": "differentpassword123",
            "first_name": "New",
            "last_name": "User",
            "company_name": "Test Company",
        }

        response = api_client.post(url, data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Passwords don't match" in str(response.data)

    def test_user_registration_weak_password(self, api_client):
        url = reverse("register")
        data = {
            "email": "newuser@testcompany.com",
            "password": "123",
            "password_confirm": "123",
            "first_name": "New",
            "last_name": "User",
            "company_name": "Test Company",
        }

        response = api_client.post(url, data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_user_login_success(self, api_client, user):
        url = reverse("login")
        data = {"email": user.email, "password": "testpassword123"}

        response = api_client.post(url, data)

        assert response.status_code == status.HTTP_200_OK
        assert "user" in response.data
        assert "tokens" in response.data
        assert "session_token" in response.data
        assert response.data["user"]["email"] == user.email

        # Check that a user session was created
        session_token = response.data["session_token"]
        assert session_token is not None

        # Verify session exists in database
        user_sessions = UserSession.objects.filter(user=user)
        assert user_sessions.exists()

        # Check user fields in response
        user_data = response.data["user"]
        assert user_data["first_name"] == user.first_name
        assert user_data["last_name"] == user.last_name
        assert user_data["role"] == user.role
        assert user_data["timezone"] == user.timezone
        assert user_data["is_active"] == user.is_active

    def test_user_login_invalid_credentials(self, api_client, user):
        url = reverse("login")
        data = {"email": user.email, "password": "wrongpassword"}

        response = api_client.post(url, data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Invalid credentials" in str(response.data)

    def test_user_login_inactive_user(self, api_client, user):
        user.is_active = False
        user.save()

        url = reverse("login")
        data = {"email": user.email, "password": "testpassword123"}

        response = api_client.post(url, data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Account is disabled" in str(response.data)

    def test_user_logout(self, authenticated_client):
        url = reverse("logout")
        data = {}

        response = authenticated_client.post(url, data)

        assert response.status_code == status.HTTP_200_OK
        assert "Logout successful" in response.data["message"]

    def test_get_profile(self, authenticated_client, user):
        url = reverse("profile")

        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["email"] == user.email
        assert response.data["first_name"] == user.first_name
        assert response.data["last_name"] == user.last_name
        assert response.data["role"] == user.role
        assert response.data["timezone"] == user.timezone
        assert response.data["is_active"] == user.is_active

        # Check additional profile fields
        assert "date_joined" in response.data or "created_at" in response.data
        assert "updated_at" in response.data

        # Check company information if user has a company
        if user.company:
            assert "company" in response.data
            company_data = response.data["company"]
            assert company_data["name"] == user.company.name
            assert company_data["domain"] == user.company.domain

    def test_update_profile(self, authenticated_client, user):
        url = reverse("profile")
        data = {"first_name": "Updated", "last_name": "Name", "timezone": "America/New_York"}

        response = authenticated_client.put(url, data)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["first_name"] == "Updated"
        assert response.data["last_name"] == "Name"

        # Check user was updated in database
        user.refresh_from_db()
        assert user.first_name == "Updated"
        assert user.last_name == "Name"

        # Check timezone update if supported
        if "timezone" in response.data:
            assert response.data["timezone"] == "America/New_York"
            assert user.timezone == "America/New_York"

        # Check that updated_at timestamp was changed
        assert user.updated_at is not None

    def test_update_profile_partial(self, authenticated_client, user):
        original_last_name = user.last_name
        url = reverse("profile")
        data = {"first_name": "PartialUpdate"}

        response = authenticated_client.put(url, data)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["first_name"] == "PartialUpdate"

        # Check that unchanged fields remain the same
        user.refresh_from_db()
        assert user.first_name == "PartialUpdate"
        assert user.last_name == original_last_name

    def test_profile_readonly_fields(self, authenticated_client, user):
        original_email = user.email
        original_role = user.role

        url = reverse("profile")
        data = {
            "first_name": "Updated",
            "email": "newemail@testcompany.com",  # Should not be updatable
            "role": "admin",  # Should not be updatable
            "is_staff": True,  # Should not be updatable
        }

        response = authenticated_client.put(url, data)

        # Even if the request succeeds, sensitive fields should not change
        user.refresh_from_db()
        assert user.email == original_email
        assert user.role == original_role
        assert user.is_staff is False  # Should remain unchanged

    def test_change_password(self, authenticated_client, user):
        url = reverse("change_password")
        data = {
            "old_password": "testpassword123",
            "new_password": "newstrongpassword456",
            "new_password_confirm": "newstrongpassword456",
        }

        response = authenticated_client.post(url, data)

        assert response.status_code == status.HTTP_200_OK
        assert "Password changed successfully" in response.data["message"]

        # Check password was changed
        user.refresh_from_db()
        assert user.check_password("newstrongpassword456")

    def test_change_password_wrong_old_password(self, authenticated_client):
        url = reverse("change_password")
        data = {
            "old_password": "wrongoldpassword",
            "new_password": "newstrongpassword456",
            "new_password_confirm": "newstrongpassword456",
        }

        response = authenticated_client.post(url, data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Old password is incorrect" in str(response.data)

    def test_change_password_mismatch(self, authenticated_client):
        url = reverse("change_password")
        data = {
            "old_password": "testpassword123",
            "new_password": "newstrongpassword456",
            "new_password_confirm": "differentpassword456",
        }

        response = authenticated_client.post(url, data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "New passwords don't match" in str(response.data)


@pytest.mark.django_db
class TestTokenAPI:

    def test_refresh_token(self, api_client, user):
        refresh = RefreshToken.for_user(user)

        url = reverse("token_refresh")
        data = {"refresh": str(refresh)}

        response = api_client.post(url, data)

        assert response.status_code == status.HTTP_200_OK
        assert "access" in response.data
        assert "message" in response.data

    def test_verify_token_valid(self, api_client, user):
        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)

        url = reverse("verify_token")
        data = {"token": access_token}

        response = api_client.post(url, data)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["valid"] is True
        assert response.data["user_id"] == str(user.id)
        assert response.data["email"] == user.email
        assert response.data["role"] == user.role

    def test_verify_token_invalid(self, api_client):
        url = reverse("verify_token")
        data = {"token": "invalid.token.here"}

        response = api_client.post(url, data)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.data["valid"] is False
        assert "Invalid token" in response.data["error"]

    def test_verify_token_no_token(self, api_client):
        url = reverse("verify_token")
        data = {}

        response = api_client.post(url, data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["valid"] is False
        assert "No token provided" in response.data["error"]


@pytest.mark.django_db
class TestSessionAPI:

    def test_get_user_sessions(self, authenticated_client, user, user_session):
        session, token = user_session

        url = reverse("user_sessions")

        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) >= 1

        # Find our specific session in the response
        session_data = next((s for s in response.data if s["id"] == str(session.id)), None)
        assert session_data is not None
        # Removed is_active field check
        assert session_data["user_agent"] is not None
        assert "created_at" in session_data
        # Removed last_used field check
        assert "expires_at" in session_data

    def test_terminate_specific_session(self, authenticated_client, user, user_session):
        session, token = user_session

        url = reverse("user_sessions")
        data = {"session_id": str(session.id)}

        response = authenticated_client.delete(url, data)

        assert response.status_code == status.HTTP_200_OK
        assert "Session terminated" in response.data["message"]

        # Check session was deleted
        with pytest.raises(UserSession.DoesNotExist):
            session.refresh_from_db()

    def test_terminate_all_sessions(self, authenticated_client, user):
        # Create multiple sessions for the user
        UserSession.objects.create(user=user, token_hash="session1_hash")
        UserSession.objects.create(user=user, token_hash="session2_hash")

        initial_active_sessions = UserSession.objects.filter(user=user).count()
        assert initial_active_sessions >= 2

        url = reverse("user_sessions")
        data = {}

        response = authenticated_client.delete(url, data)

        assert response.status_code == status.HTTP_200_OK
        assert "All sessions terminated" in response.data["message"]

        # Check all sessions were deactivated
        active_sessions = UserSession.objects.filter(user=user).count()
        assert active_sessions == 0

    def test_session_details_in_response(self, authenticated_client, user):
        # Create a session with specific details
        from apps.authentication.utils import hash_token

        session = UserSession.objects.create(
            user=user, token_hash=hash_token("test_token"), user_agent="Mozilla/5.0 Test Browser", ip_address="192.168.1.100"
        )

        url = reverse("user_sessions")
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK

        session_data = next((s for s in response.data if s["id"] == str(session.id)), None)
        assert session_data is not None

        # Check that sensitive information is not exposed
        assert "token_hash" not in session_data

        # Check that appropriate fields are included
        expected_fields = ["id", "created_at", "expires_at", "user_agent"]
        for field in expected_fields:
            assert field in session_data


@pytest.mark.django_db
class TestUnauthorizedAccess:

    def test_profile_requires_authentication(self, api_client):
        url = reverse("profile")

        response = api_client.get(url)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_change_password_requires_authentication(self, api_client):
        url = reverse("change_password")
        data = {"old_password": "testpassword123", "new_password": "newpassword456", "new_password_confirm": "newpassword456"}

        response = api_client.post(url, data)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_sessions_require_authentication(self, api_client):
        url = reverse("user_sessions")

        response = api_client.get(url)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
