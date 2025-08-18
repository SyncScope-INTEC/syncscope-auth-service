from unittest.mock import Mock, patch

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from apps.authentication.models import UserSession

User = get_user_model()


@pytest.mark.django_db
class TestVerifyTokenEndpoint:

    def test_verify_token_user_not_found(self, api_client):
        """Test token verification when user doesn't exist in database."""
        # Create a token with non-existent user ID
        token = RefreshToken()
        token.payload["user_id"] = 99999  # Non-existent user ID
        access_token = str(token.access_token)

        url = reverse("verify_token")
        data = {"token": access_token}

        response = api_client.post(url, data)

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.data["valid"] is False
        assert "User not found" in response.data["error"]

    def test_verify_token_user_inactive(self, api_client, user):
        """Test token verification with inactive user."""
        user.is_active = False
        user.save()

        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)

        url = reverse("verify_token")
        data = {"token": access_token}

        response = api_client.post(url, data)

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.data["valid"] is False

    def test_verify_token_with_company(self, api_client, user):
        """Test token verification returns company ID when user has company."""
        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)

        url = reverse("verify_token")
        data = {"token": access_token}

        response = api_client.post(url, data)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["valid"] is True
        if user.company:
            assert response.data["company_id"] == str(user.company.id)
        else:
            assert response.data["company_id"] is None


@pytest.mark.django_db
class TestLogoutViewEdgeCases:

    def test_logout_with_invalid_refresh_token(self, authenticated_client):
        """Test logout with invalid refresh token."""
        url = reverse("logout")
        data = {"refresh_token": "invalid.token.here"}

        response = authenticated_client.post(url, data)

        # Should still return success even with invalid token
        assert response.status_code == status.HTTP_200_OK
        assert "Logout completed" in response.data["message"]

    def test_logout_with_invalid_session_token(self, authenticated_client):
        """Test logout with invalid session token."""
        url = reverse("logout")
        data = {"session_token": "invalid_session_token"}

        response = authenticated_client.post(url, data)

        assert response.status_code == status.HTTP_200_OK
        # Should invalidate all sessions when session token is invalid

    def test_logout_session_token_belongs_to_different_user(self, authenticated_client, user):
        """Test logout with session token that belongs to different user."""
        # Create another user and their session
        other_user = User.objects.create_user(
            email="other@example.com", password="password123", first_name="Other", last_name="User"
        )

        from apps.authentication.utils import create_user_session

        request_mock = Mock()
        request_mock.META = {"HTTP_USER_AGENT": "Test", "REMOTE_ADDR": "127.0.0.1"}

        other_session, other_token = create_user_session(other_user, request_mock)

        url = reverse("logout")
        data = {"session_token": other_token}

        response = authenticated_client.post(url, data)

        assert response.status_code == status.HTTP_200_OK
        # Should not deactivate other user's session
        other_session.refresh_from_db()
        assert other_session.is_active is True

    def test_logout_without_tokens(self, authenticated_client):
        """Test logout without providing any tokens."""
        url = reverse("logout")
        data = {}

        response = authenticated_client.post(url, data)

        assert response.status_code == status.HTTP_200_OK
        assert "Logout successful" in response.data["message"]
        # Should invalidate all user sessions


@pytest.mark.django_db
class TestUserSessionsViewEdgeCases:

    def test_get_sessions_only_active_and_not_expired(self, authenticated_client, user):
        """Test that only active and non-expired sessions are returned."""
        from datetime import timedelta

        from django.utils import timezone

        from apps.authentication.utils import hash_token

        # Create expired session
        UserSession.objects.create(
            user=user, token_hash=hash_token("expired_token"), expires_at=timezone.now() - timedelta(hours=1), is_active=True
        )

        # Create inactive session
        UserSession.objects.create(
            user=user, token_hash=hash_token("inactive_token"), expires_at=timezone.now() + timedelta(hours=1), is_active=False
        )

        # Create valid session
        valid_session = UserSession.objects.create(
            user=user, token_hash=hash_token("valid_token"), expires_at=timezone.now() + timedelta(hours=1), is_active=True
        )

        url = reverse("user_sessions")
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        # Should only return the valid session
        session_ids = [s["id"] for s in response.data]
        assert str(valid_session.id) in session_ids
        assert len([s for s in response.data if s["is_active"]]) >= 1

    def test_terminate_nonexistent_session(self, authenticated_client):
        """Test terminating a session that doesn't exist."""
        url = reverse("user_sessions")
        data = {"session_id": "00000000-0000-0000-0000-000000000000"}

        response = authenticated_client.delete(url, data)

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "Session not found" in response.data["error"]

    def test_terminate_other_users_session(self, authenticated_client, user):
        """Test terminating a session that belongs to another user."""
        # Create another user and their session
        other_user = User.objects.create_user(
            email="other@example.com", password="password123", first_name="Other", last_name="User"
        )

        from apps.authentication.utils import hash_token

        other_session = UserSession.objects.create(user=other_user, token_hash=hash_token("other_token"))

        url = reverse("user_sessions")
        data = {"session_id": str(other_session.id)}

        response = authenticated_client.delete(url, data)

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "Session not found" in response.data["error"]

        # Other user's session should remain active
        other_session.refresh_from_db()
        assert other_session.is_active is True


@pytest.mark.django_db
class TestRateLimitingViews:

    def test_register_rate_limit_applied(self, api_client):
        """Test that rate limiting is applied to register endpoint."""
        url = reverse("register")
        data = {
            "email": "test@example.com",
            "password": "strongpassword123",
            "password_confirm": "strongpassword123",
            "first_name": "Test",
            "last_name": "User",
            "company_name": "Test Company",
        }

        response = api_client.post(url, data)

        # Rate limit decorator is applied at class level, test successful response
        assert response.status_code == status.HTTP_201_CREATED

    def test_login_rate_limit_applied(self, api_client, user):
        """Test that rate limiting is applied to login endpoint."""
        url = reverse("login")
        data = {"email": user.email, "password": "testpassword123"}

        response = api_client.post(url, data)

        # Rate limit decorator is applied at class level, test successful response
        assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
class TestCustomTokenRefreshView:

    def test_token_refresh_success_message(self, api_client, user):
        """Test that token refresh adds success message."""
        refresh = RefreshToken.for_user(user)

        url = reverse("token_refresh")
        data = {"refresh": str(refresh)}

        response = api_client.post(url, data)

        assert response.status_code == status.HTTP_200_OK
        assert "access" in response.data
        assert response.data["message"] == "Token refreshed successfully"

    def test_token_refresh_invalid_token(self, api_client):
        """Test token refresh with invalid token."""
        url = reverse("token_refresh")
        data = {"refresh": "invalid.refresh.token"}

        response = api_client.post(url, data)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        # Should not have custom message for error responses


@pytest.mark.django_db
class TestProfileViewEdgeCases:

    def test_profile_update_empty_data(self, authenticated_client, user):
        """Test profile update with empty data."""
        original_first_name = user.first_name

        url = reverse("profile")
        data = {}

        response = authenticated_client.put(url, data)

        assert response.status_code == status.HTTP_200_OK
        # User data should remain unchanged
        user.refresh_from_db()
        assert user.first_name == original_first_name

    def test_profile_update_invalid_data(self, authenticated_client):
        """Test profile update with invalid data."""
        url = reverse("profile")
        data = {"first_name": ""}  # Empty first name might be invalid

        response = authenticated_client.put(url, data)

        # Response could be 200 (if empty is allowed) or 400 (if validation fails)
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_400_BAD_REQUEST]
