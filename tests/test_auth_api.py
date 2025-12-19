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
        assert "profile_image_path" in response.data

        # Check company information if user has a company
        if user.company:
            assert "company" in response.data
            company_data = response.data["company"]
            assert company_data["name"] == user.company.name
            assert company_data["domain"] == user.company.domain

    def test_get_user_by_id(self, authenticated_client, user):
        """Test getting user details by user ID"""
        # Create another user to fetch
        other_user = User.objects.create_user(
            email="otheruser@test.com",
            password="testpass123",
            first_name="Other",
            last_name="User",
            role="developer",
        )

        url = reverse("user_by_id", kwargs={"user_id": other_user.id})
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["id"] == str(other_user.id)
        assert response.data["email"] == other_user.email
        assert response.data["first_name"] == other_user.first_name
        assert response.data["last_name"] == other_user.last_name
        assert response.data["role"] == other_user.role

    def test_get_user_by_id_not_found(self, authenticated_client):
        """Test getting user by non-existent ID"""
        import uuid

        fake_id = uuid.uuid4()
        url = reverse("user_by_id", kwargs={"user_id": fake_id})
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "User not found" in response.data["error"]

    def test_get_user_by_id_requires_authentication(self, api_client):
        """Test that getting user by ID requires authentication"""
        import uuid

        fake_id = uuid.uuid4()
        url = reverse("user_by_id", kwargs={"user_id": fake_id})
        response = api_client.get(url)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

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


@pytest.mark.django_db
class TestUserModelMethods:
    """Test User model methods for plan features and limits"""

    def test_has_feature(self, user):
        """Test User.has_feature() method"""
        # Test starter plan features
        user.plan = "starter"
        assert user.has_feature("automatic_time_monitoring") is True
        assert user.has_feature("weekly_reports") is True
        assert user.has_feature("automated_code_audit") is False  # Growth+ only

        # Test growth plan features
        user.plan = "growth"
        assert user.has_feature("automated_code_audit") is True

    def test_can_add_user_to_company_no_company(self, user):
        """Test can_add_user_to_company when user has no company"""
        user.company = None
        user.save()
        assert user.can_add_user_to_company() is True

    def test_can_add_user_to_company_with_company(self, user, company):
        """Test can_add_user_to_company with company"""
        user.company = company
        user.plan = "starter"  # Starter plan has max 5 users
        user.save()

        # Should be able to add users since we only have 1 user
        assert user.can_add_user_to_company() is True

    def test_can_add_integration(self, user):
        """Test can_add_integration method"""
        user.plan = "starter"  # Starter plan has max 1 integration
        assert user.can_add_integration(0) is True
        assert user.can_add_integration(1) is False

        # Test growth plan (max 3 integrations)
        user.plan = "growth"
        assert user.can_add_integration(2) is True
        assert user.can_add_integration(3) is False


@pytest.mark.django_db
class TestPasswordResetAPI:
    """Test password reset functionality including forgot password, verify code, and reset password"""

    @pytest.fixture(autouse=True)
    def disable_rate_limiting(self, settings):
        """Disable rate limiting for all password reset tests"""
        settings.RATELIMIT_ENABLE = False

    def test_forgot_password_success(self, api_client, user, monkeypatch):
        """Test successful forgot password request"""
        from apps.authentication import utils

        # Mock send_reset_email to avoid calling alerts-service
        mock_send_called = []

        def mock_send_reset_email(email, name, code):
            mock_send_called.append({"email": email, "name": name, "code": code})
            return True

        monkeypatch.setattr(utils, "send_reset_email", mock_send_reset_email)

        url = reverse("forgot_password")
        data = {"email": user.email}

        response = api_client.post(url, data)

        assert response.status_code == status.HTTP_200_OK
        assert "reset code has been sent" in response.data["message"].lower()
        assert len(mock_send_called) == 1
        assert mock_send_called[0]["email"] == user.email
        assert mock_send_called[0]["name"] == user.full_name
        assert len(mock_send_called[0]["code"]) == 6
        assert mock_send_called[0]["code"].isdigit()

        # Check that a reset token was created
        from apps.authentication.models import PasswordResetToken

        reset_token = PasswordResetToken.objects.filter(user=user).first()
        assert reset_token is not None
        assert reset_token.is_valid()

    def test_forgot_password_nonexistent_email(self, api_client, monkeypatch):
        """Test forgot password with non-existent email (should return success to prevent user enumeration)"""
        from apps.authentication import utils

        mock_send_called = []

        def mock_send_reset_email(email, name, code):
            mock_send_called.append(True)
            return True

        monkeypatch.setattr(utils, "send_reset_email", mock_send_reset_email)

        url = reverse("forgot_password")
        data = {"email": "nonexistent@testcompany.com"}

        response = api_client.post(url, data)

        # Should return success to prevent user enumeration
        assert response.status_code == status.HTTP_200_OK
        assert "reset code has been sent" in response.data["message"].lower()
        # Email should not actually be sent
        assert len(mock_send_called) == 0

    def test_forgot_password_inactive_user(self, api_client, user, monkeypatch):
        """Test forgot password with inactive user (should return success to prevent user enumeration)"""
        from apps.authentication import utils

        user.is_active = False
        user.save()

        mock_send_called = []

        def mock_send_reset_email(email, name, code):
            mock_send_called.append(True)
            return True

        monkeypatch.setattr(utils, "send_reset_email", mock_send_reset_email)

        url = reverse("forgot_password")
        data = {"email": user.email}

        response = api_client.post(url, data)

        # Should return success to prevent user enumeration
        assert response.status_code == status.HTTP_200_OK
        # Email should not actually be sent to inactive users
        assert len(mock_send_called) == 0

    def test_forgot_password_invalidates_old_tokens(self, api_client, user, monkeypatch):
        """Test that new forgot password request invalidates old tokens"""
        from apps.authentication import utils
        from apps.authentication.models import PasswordResetToken

        # Create an old reset token
        old_code = "123456"
        old_code_hash = utils.hash_token(old_code)
        old_token = PasswordResetToken.objects.create(user=user, code_hash=old_code_hash)
        assert old_token.is_valid()

        # Mock send_reset_email
        def mock_send_reset_email(email, name, code):
            return True

        monkeypatch.setattr(utils, "send_reset_email", mock_send_reset_email)

        url = reverse("forgot_password")
        data = {"email": user.email}

        response = api_client.post(url, data)

        assert response.status_code == status.HTTP_200_OK

        # Old token should be invalidated
        old_token.refresh_from_db()
        assert old_token.is_invalidated is True

    def test_verify_reset_code_success(self, api_client, user):
        """Test successful reset code verification"""
        from apps.authentication.models import PasswordResetToken
        from apps.authentication.utils import hash_token

        # Create a reset token
        reset_code = "123456"
        code_hash = hash_token(reset_code)
        PasswordResetToken.objects.create(user=user, code_hash=code_hash)

        url = reverse("verify_reset_code")
        data = {"email": user.email, "code": reset_code}

        response = api_client.post(url, data)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["valid"] is True
        assert "code is valid" in response.data["message"].lower()

    def test_verify_reset_code_invalid_code(self, api_client, user):
        """Test verification with invalid reset code"""
        from apps.authentication.models import PasswordResetToken
        from apps.authentication.utils import hash_token

        # Create a reset token
        reset_code = "123456"
        code_hash = hash_token(reset_code)
        PasswordResetToken.objects.create(user=user, code_hash=code_hash)

        url = reverse("verify_reset_code")
        data = {"email": user.email, "code": "999999"}  # Wrong code

        response = api_client.post(url, data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "invalid or expired" in response.data["message"].lower()

    def test_verify_reset_code_expired(self, api_client, user):
        """Test verification with expired reset code"""
        from datetime import timedelta

        from django.utils import timezone

        from apps.authentication.models import PasswordResetToken
        from apps.authentication.utils import hash_token

        # Create an expired reset token
        reset_code = "123456"
        code_hash = hash_token(reset_code)
        expired_token = PasswordResetToken.objects.create(user=user, code_hash=code_hash)
        expired_token.expires_at = timezone.now() - timedelta(hours=2)
        expired_token.save()

        url = reverse("verify_reset_code")
        data = {"email": user.email, "code": reset_code}

        response = api_client.post(url, data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "expired" in response.data["message"].lower() or "invalid" in response.data["message"].lower()

    def test_verify_reset_code_max_attempts(self, api_client, user):
        """Test verification with max attempts exceeded"""
        from apps.authentication.models import PasswordResetToken
        from apps.authentication.utils import hash_token

        # Create a reset token with max attempts
        reset_code = "123456"
        code_hash = hash_token(reset_code)
        token = PasswordResetToken.objects.create(user=user, code_hash=code_hash)
        token.attempts = 5
        token.is_invalidated = True
        token.save()

        url = reverse("verify_reset_code")
        data = {"email": user.email, "code": reset_code}

        response = api_client.post(url, data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "maximum" in response.data["message"].lower() or "invalid" in response.data["message"].lower()

    def test_reset_password_success(self, api_client, user):
        """Test successful password reset"""
        from apps.authentication.models import PasswordResetToken, UserSession
        from apps.authentication.utils import hash_token

        # Create a reset token
        reset_code = "123456"
        code_hash = hash_token(reset_code)
        PasswordResetToken.objects.create(user=user, code_hash=code_hash)

        # Create some user sessions
        UserSession.objects.create(user=user, token_hash="session1")
        UserSession.objects.create(user=user, token_hash="session2")
        assert UserSession.objects.filter(user=user).count() == 2

        url = reverse("reset_password")
        data = {
            "email": user.email,
            "code": reset_code,
            "new_password": "newstrongpassword123",
            "new_password_confirm": "newstrongpassword123",
        }

        response = api_client.post(url, data)

        assert response.status_code == status.HTTP_200_OK
        assert "password has been reset" in response.data["message"].lower()

        # Check password was changed
        user.refresh_from_db()
        assert user.check_password("newstrongpassword123")

        # Check all sessions were invalidated
        assert UserSession.objects.filter(user=user).count() == 0

        # Check token was marked as used
        token = PasswordResetToken.objects.filter(user=user, code_hash=code_hash).first()
        assert token.is_used is True

    def test_reset_password_invalid_code(self, api_client, user):
        """Test password reset with invalid code"""
        from apps.authentication.models import PasswordResetToken
        from apps.authentication.utils import hash_token

        # Create a reset token
        reset_code = "123456"
        code_hash = hash_token(reset_code)
        PasswordResetToken.objects.create(user=user, code_hash=code_hash)

        url = reverse("reset_password")
        data = {
            "email": user.email,
            "code": "999999",
            "new_password": "newstrongpassword123",
            "new_password_confirm": "newstrongpassword123",
        }

        response = api_client.post(url, data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "invalid or expired" in response.data["error"].lower()

        # Password should not have changed
        user.refresh_from_db()
        assert user.check_password("testpassword123")

    def test_reset_password_weak_password(self, api_client, user):
        """Test password reset with weak password"""
        from apps.authentication.models import PasswordResetToken
        from apps.authentication.utils import hash_token

        # Create a reset token
        reset_code = "123456"
        code_hash = hash_token(reset_code)
        PasswordResetToken.objects.create(user=user, code_hash=code_hash)

        url = reverse("reset_password")
        data = {"email": user.email, "code": reset_code, "new_password": "123", "new_password_confirm": "123"}

        response = api_client.post(url, data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_reset_password_mismatch(self, api_client, user):
        """Test password reset with mismatched passwords"""
        from apps.authentication.models import PasswordResetToken
        from apps.authentication.utils import hash_token

        # Create a reset token
        reset_code = "123456"
        code_hash = hash_token(reset_code)
        PasswordResetToken.objects.create(user=user, code_hash=code_hash)

        url = reverse("reset_password")
        data = {
            "email": user.email,
            "code": reset_code,
            "new_password": "newstrongpassword123",
            "new_password_confirm": "differentpassword123",
        }

        response = api_client.post(url, data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "don't match" in str(response.data).lower()

    def test_reset_password_expired_token(self, api_client, user):
        """Test password reset with expired token"""
        from datetime import timedelta

        from django.utils import timezone

        from apps.authentication.models import PasswordResetToken
        from apps.authentication.utils import hash_token

        # Create an expired reset token
        reset_code = "123456"
        code_hash = hash_token(reset_code)
        expired_token = PasswordResetToken.objects.create(user=user, code_hash=code_hash)
        expired_token.expires_at = timezone.now() - timedelta(hours=2)
        expired_token.save()

        url = reverse("reset_password")
        data = {
            "email": user.email,
            "code": reset_code,
            "new_password": "newstrongpassword123",
            "new_password_confirm": "newstrongpassword123",
        }

        response = api_client.post(url, data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "expired" in response.data["error"].lower() or "invalid" in response.data["error"].lower()

    def test_reset_password_already_used_token(self, api_client, user):
        """Test password reset with already used token"""
        from apps.authentication.models import PasswordResetToken
        from apps.authentication.utils import hash_token

        # Create a used reset token
        reset_code = "123456"
        code_hash = hash_token(reset_code)
        used_token = PasswordResetToken.objects.create(user=user, code_hash=code_hash)
        used_token.is_used = True
        used_token.save()

        url = reverse("reset_password")
        data = {
            "email": user.email,
            "code": reset_code,
            "new_password": "newstrongpassword123",
            "new_password_confirm": "newstrongpassword123",
        }

        response = api_client.post(url, data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "invalid or expired" in response.data["error"].lower()

    def test_reset_password_invalidated_token(self, api_client, user):
        """Test password reset with invalidated token (max attempts exceeded)"""
        from apps.authentication.models import PasswordResetToken
        from apps.authentication.utils import hash_token

        # Create a token with max attempts
        reset_code = "123456"
        code_hash = hash_token(reset_code)
        token = PasswordResetToken.objects.create(user=user, code_hash=code_hash)
        token.attempts = 4  # Set to 4, so incrementing will make it 5 and invalidate
        token.save()

        url = reverse("reset_password")
        data = {
            "email": user.email,
            "code": reset_code,
            "new_password": "newstrongpassword123",
            "new_password_confirm": "newstrongpassword123",
        }

        response = api_client.post(url, data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "maximum" in response.data["error"].lower() or "attempts" in response.data["error"].lower()

        # Token should now be invalidated
        token.refresh_from_db()
        assert token.is_invalidated is True

    def test_reset_password_nonexistent_user(self, api_client):
        """Test password reset with non-existent user email"""
        url = reverse("reset_password")
        data = {
            "email": "nonexistent@test.com",
            "code": "123456",
            "new_password": "newstrongpassword123",
            "new_password_confirm": "newstrongpassword123",
        }

        response = api_client.post(url, data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "invalid or expired" in response.data["error"].lower()

    def test_reset_password_increments_attempts_on_success(self, api_client, user):
        """Test that successful reset password increments attempts once then marks as used"""
        from apps.authentication.models import PasswordResetToken
        from apps.authentication.utils import hash_token

        # Create a reset token
        reset_code = "123456"
        code_hash = hash_token(reset_code)
        token = PasswordResetToken.objects.create(user=user, code_hash=code_hash)
        assert token.attempts == 0

        url = reverse("reset_password")
        data = {
            "email": user.email,
            "code": reset_code,
            "new_password": "newstrongpassword123",
            "new_password_confirm": "newstrongpassword123",
        }

        # Make one successful reset attempt
        response = api_client.post(url, data)
        token.refresh_from_db()

        # Should have incremented attempts and marked as used
        assert response.status_code == status.HTTP_200_OK
        assert token.attempts == 1
        assert token.is_used is True

    def test_reset_password_max_attempts_with_model_method(self, user):
        """Test that token invalidation works after 5 increment_attempts() calls"""
        from apps.authentication.models import PasswordResetToken
        from apps.authentication.utils import hash_token

        # Create a reset token
        reset_code = "123456"
        code_hash = hash_token(reset_code)
        token = PasswordResetToken.objects.create(user=user, code_hash=code_hash)

        # Manually increment attempts 5 times (simulating failed verifications)
        for i in range(5):
            token.increment_attempts()

        # Token should now be invalidated
        assert token.attempts == 5
        assert token.is_invalidated is True
        assert token.is_valid() is False

    def test_forgot_password_email_failure(self, api_client, user, monkeypatch):
        """Test forgot password when email sending fails"""
        from apps.authentication import utils

        # Mock send_reset_email to return False (email failed)
        def mock_send_reset_email_failure(email, name, code):
            return False

        monkeypatch.setattr(utils, "send_reset_email", mock_send_reset_email_failure)

        url = reverse("forgot_password")
        data = {"email": user.email}

        response = api_client.post(url, data)

        # Should return error when email fails to send
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "failed to send" in response.data["error"].lower()

    def test_send_reset_email_exception_handling(self, monkeypatch):
        """Test that send_reset_email handles exceptions gracefully"""
        from apps.authentication.utils import send_reset_email

        # Mock requests.post to raise an exception
        def mock_post_exception(*args, **kwargs):
            raise Exception("Connection error")

        import requests

        monkeypatch.setattr(requests, "post", mock_post_exception)

        # Should return False and not raise exception
        result = send_reset_email("test@example.com", "Test User", "123456")
        assert result is False

    def test_generate_reset_code_format(self):
        """Test that generated reset codes are 6-digit numeric strings"""
        from apps.authentication.utils import generate_reset_code

        for _ in range(10):
            code = generate_reset_code()
            assert len(code) == 6
            assert code.isdigit()
            assert 0 <= int(code) <= 999999

    def test_password_reset_model_cleanup(self, user):
        """Test cleanup of expired password reset tokens"""
        from datetime import timedelta

        from django.utils import timezone

        from apps.authentication.models import PasswordResetToken
        from apps.authentication.utils import hash_token

        # Create expired tokens
        for i in range(3):
            code_hash = hash_token(f"code{i}")
            token = PasswordResetToken.objects.create(user=user, code_hash=code_hash)
            token.expires_at = timezone.now() - timedelta(days=2)
            token.save()

        # Create valid token
        valid_code_hash = hash_token("validcode")
        valid_token = PasswordResetToken.objects.create(user=user, code_hash=valid_code_hash)

        assert PasswordResetToken.objects.filter(user=user).count() == 4

        # Run cleanup
        PasswordResetToken.cleanup_expired_tokens()

        # Only valid token should remain
        assert PasswordResetToken.objects.filter(user=user).count() == 1
        assert PasswordResetToken.objects.filter(user=user).first().id == valid_token.id

    def test_password_reset_token_is_expired_method(self, user):
        """Test PasswordResetToken.is_expired() method"""
        from datetime import timedelta

        from django.utils import timezone

        from apps.authentication.models import PasswordResetToken
        from apps.authentication.utils import hash_token

        # Create valid token
        code_hash = hash_token("validcode")
        valid_token = PasswordResetToken.objects.create(user=user, code_hash=code_hash)
        assert valid_token.is_expired() is False

        # Create expired token
        expired_code_hash = hash_token("expiredcode")
        expired_token = PasswordResetToken.objects.create(user=user, code_hash=expired_code_hash)
        expired_token.expires_at = timezone.now() - timedelta(hours=2)
        expired_token.save()
        assert expired_token.is_expired() is True

    def test_password_reset_token_mark_as_used(self, user):
        """Test PasswordResetToken.mark_as_used() method"""
        from apps.authentication.models import PasswordResetToken
        from apps.authentication.utils import hash_token

        code_hash = hash_token("testcode")
        token = PasswordResetToken.objects.create(user=user, code_hash=code_hash)
        assert token.is_used is False
        assert token.is_valid() is True

        token.mark_as_used()
        assert token.is_used is True
        assert token.is_valid() is False

    def test_password_reset_token_increment_attempts(self, user):
        """Test PasswordResetToken.increment_attempts() method"""
        from apps.authentication.models import PasswordResetToken
        from apps.authentication.utils import hash_token

        code_hash = hash_token("testcode")
        token = PasswordResetToken.objects.create(user=user, code_hash=code_hash)
        assert token.attempts == 0

        # Increment attempts
        for i in range(1, 6):
            token.increment_attempts()
            assert token.attempts == i

        # After 5 attempts, should be invalidated
        assert token.is_invalidated is True
        assert token.is_valid() is False

    def test_password_reset_token_invalidate_user_tokens(self, user):
        """Test PasswordResetToken.invalidate_user_tokens() class method"""
        from apps.authentication.models import PasswordResetToken
        from apps.authentication.utils import hash_token

        # Create multiple tokens for the user
        for i in range(3):
            code_hash = hash_token(f"code{i}")
            PasswordResetToken.objects.create(user=user, code_hash=code_hash)

        assert PasswordResetToken.objects.filter(user=user, is_invalidated=False).count() == 3

        # Invalidate all tokens
        PasswordResetToken.invalidate_user_tokens(user)

        # All tokens should be invalidated
        assert PasswordResetToken.objects.filter(user=user, is_invalidated=False).count() == 0
        assert PasswordResetToken.objects.filter(user=user, is_invalidated=True).count() == 3
