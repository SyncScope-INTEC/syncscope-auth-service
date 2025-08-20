"""
Comprehensive tests for views.py to improve coverage
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from apps.authentication.models import Company, User, UserSession


class TestRegisterView(APITestCase):
    """Test RegisterView"""

    def setUp(self):
        self.url = reverse("register")

    def test_register_success(self):
        """Test successful user registration"""
        data = {"email": "test@example.com", "password": "testpass123", "first_name": "Test", "last_name": "User"}

        response = self.client.post(self.url, data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("message", response.data)
        self.assertIn("user", response.data)
        self.assertIn("tokens", response.data)
        self.assertIn("session_token", response.data)

        # Verify user was created
        user = User.objects.get(email="test@example.com")
        self.assertEqual(user.first_name, "Test")
        self.assertEqual(user.last_name, "User")

    def test_register_invalid_data(self):
        """Test registration with invalid data"""
        data = {
            "email": "invalid-email",
            "password": "123",  # Too short
        }

        response = self.client.post(self.url, data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.data)

    def test_register_duplicate_email(self):
        """Test registration with duplicate email"""
        User.objects.create_user(email="test@example.com", password="testpass123", first_name="Existing", last_name="User")

        data = {"email": "test@example.com", "password": "testpass123", "first_name": "Test", "last_name": "User"}

        response = self.client.post(self.url, data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class TestLoginView(APITestCase):
    """Test LoginView"""

    def setUp(self):
        self.url = reverse("login")
        self.user = User.objects.create_user(
            email="test@example.com", password="testpass123", first_name="Test", last_name="User"
        )

    def test_login_success(self):
        """Test successful login"""
        data = {"email": "test@example.com", "password": "testpass123"}

        response = self.client.post(self.url, data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("message", response.data)
        self.assertIn("user", response.data)
        self.assertIn("tokens", response.data)
        self.assertIn("session_token", response.data)

        # Verify last_login was updated
        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.last_login)

    def test_login_invalid_credentials(self):
        """Test login with invalid credentials"""
        data = {"email": "test@example.com", "password": "wrongpassword"}

        response = self.client.post(self.url, data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_login_nonexistent_user(self):
        """Test login with nonexistent user"""
        data = {"email": "nonexistent@example.com", "password": "testpass123"}

        response = self.client.post(self.url, data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class TestLogoutView(APITestCase):
    """Test LogoutView"""

    def setUp(self):
        self.url = reverse("logout")
        self.user = User.objects.create_user(
            email="test@example.com", password="testpass123", first_name="Test", last_name="User"
        )
        self.client.force_authenticate(user=self.user)

    def test_logout_with_refresh_token(self):
        """Test logout with refresh token"""
        refresh = RefreshToken.for_user(self.user)

        data = {"refresh_token": str(refresh)}

        response = self.client.post(self.url, data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("message", response.data)

    def test_logout_with_session_token(self):
        """Test logout with session token"""
        # Create a session
        session = UserSession.objects.create(
            user=self.user,
            token_hash="test_hash",
            ip_address="127.0.0.1",
            user_agent="test",
            expires_at=timezone.now() + timedelta(days=1),
        )

        data = {"session_token": "test_token"}

        with patch("apps.authentication.views.validate_session_token") as mock_validate:
            mock_validate.return_value = session
            response = self.client.post(self.url, data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_logout_without_tokens(self):
        """Test logout without any tokens"""
        response = self.client.post(self.url, {})

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_logout_with_invalid_refresh_token(self):
        """Test logout with invalid refresh token"""
        data = {"refresh_token": "invalid_token"}

        response = self.client.post(self.url, data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_logout_with_wrong_user_session(self):
        """Test logout with session from different user"""
        other_user = User.objects.create_user(
            email="other@example.com", password="testpass123", first_name="Other", last_name="User"
        )

        session = UserSession.objects.create(
            user=other_user,
            token_hash="test_hash",
            ip_address="127.0.0.1",
            user_agent="test",
            expires_at=timezone.now() + timedelta(days=1),
        )

        data = {"session_token": "test_token"}

        with patch("apps.authentication.views.validate_session_token") as mock_validate:
            mock_validate.return_value = session
            response = self.client.post(self.url, data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)


class TestProfileView(APITestCase):
    """Test ProfileView"""

    def setUp(self):
        self.url = reverse("profile")
        self.user = User.objects.create_user(
            email="test@example.com", password="testpass123", first_name="Test", last_name="User"
        )
        self.client.force_authenticate(user=self.user)

    def test_get_profile(self):
        """Test getting user profile"""
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["email"], "test@example.com")
        self.assertEqual(response.data["first_name"], "Test")

    def test_update_profile_success(self):
        """Test successful profile update"""
        data = {"first_name": "Updated", "last_name": "Name"}

        response = self.client.put(self.url, data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["first_name"], "Updated")
        self.assertEqual(response.data["last_name"], "Name")

        # Verify database was updated
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Updated")

    def test_update_profile_invalid_data(self):
        """Test profile update with invalid data"""
        data = {"email": "invalid-email"}

        response = self.client.put(self.url, data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class TestChangePasswordView(APITestCase):
    """Test ChangePasswordView"""

    def setUp(self):
        self.url = reverse("change_password")
        self.user = User.objects.create_user(
            email="test@example.com", password="oldpass123", first_name="Test", last_name="User"
        )
        self.client.force_authenticate(user=self.user)

    def test_change_password_success(self):
        """Test successful password change"""
        data = {"old_password": "oldpass123", "new_password": "newpass123"}

        response = self.client.post(self.url, data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("message", response.data)

    def test_change_password_wrong_old_password(self):
        """Test password change with wrong old password"""
        data = {"old_password": "wrongpass123", "new_password": "newpass123"}

        response = self.client.post(self.url, data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_change_password_invalid_new_password(self):
        """Test password change with invalid new password"""
        data = {"old_password": "oldpass123", "new_password": "123"}  # Too short

        response = self.client.post(self.url, data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class TestCustomTokenRefreshView(APITestCase):
    """Test CustomTokenRefreshView"""

    def setUp(self):
        self.url = reverse("token_refresh")
        self.user = User.objects.create_user(
            email="test@example.com", password="testpass123", first_name="Test", last_name="User"
        )

    def test_token_refresh_success(self):
        """Test successful token refresh"""
        refresh = RefreshToken.for_user(self.user)

        data = {"refresh": str(refresh)}

        response = self.client.post(self.url, data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("message", response.data)

    def test_token_refresh_invalid_token(self):
        """Test token refresh with invalid token"""
        data = {"refresh": "invalid_token"}

        response = self.client.post(self.url, data)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class TestVerifyTokenView(APITestCase):
    """Test verify_token view"""

    def setUp(self):
        self.url = reverse("verify_token")
        self.user = User.objects.create_user(
            email="test@example.com", password="testpass123", first_name="Test", last_name="User"
        )
        self.company = Company.objects.create(name="Test Company")
        self.user.company = self.company
        self.user.save()

    def test_verify_token_success(self):
        """Test successful token verification"""
        access_token = AccessToken.for_user(self.user)

        data = {"token": str(access_token)}

        response = self.client.post(self.url, data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["valid"])
        self.assertEqual(response.data["email"], "test@example.com")
        self.assertIsNotNone(response.data["company_id"])

    def test_verify_token_no_company(self):
        """Test token verification for user without company"""
        self.user.company = None
        self.user.save()

        access_token = AccessToken.for_user(self.user)

        data = {"token": str(access_token)}

        response = self.client.post(self.url, data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["valid"])
        self.assertIsNone(response.data["company_id"])

    def test_verify_token_no_token(self):
        """Test token verification without token"""
        response = self.client.post(self.url, {})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data["valid"])

    def test_verify_token_invalid_token(self):
        """Test token verification with invalid token"""
        data = {"token": "invalid_token"}

        response = self.client.post(self.url, data)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertFalse(response.data["valid"])

    def test_verify_token_user_not_found(self):
        """Test token verification for deleted user"""
        access_token = AccessToken.for_user(self.user)
        self.user.delete()

        data = {"token": str(access_token)}

        response = self.client.post(self.url, data)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(response.data["valid"])

    def test_verify_token_inactive_user(self):
        """Test token verification for inactive user"""
        self.user.is_active = False
        self.user.save()

        access_token = AccessToken.for_user(self.user)

        data = {"token": str(access_token)}

        response = self.client.post(self.url, data)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(response.data["valid"])


class TestUserSessionsView(APITestCase):
    """Test UserSessionsView"""

    def setUp(self):
        self.url = reverse("user_sessions")
        self.user = User.objects.create_user(
            email="test@example.com", password="testpass123", first_name="Test", last_name="User"
        )
        self.client.force_authenticate(user=self.user)

    def test_get_user_sessions(self):
        """Test getting user sessions"""
        # Create active session
        UserSession.objects.create(
            user=self.user,
            token_hash="hash1",
            ip_address="127.0.0.1",
            user_agent="test",
            expires_at=timezone.now() + timedelta(days=1),
        )

        # Create expired session (should not be returned)
        UserSession.objects.create(
            user=self.user,
            token_hash="hash2",
            ip_address="127.0.0.1",
            user_agent="test",
            expires_at=timezone.now() - timedelta(days=1),
        )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_delete_specific_session(self):
        """Test deleting specific session"""
        session = UserSession.objects.create(
            user=self.user,
            token_hash="hash1",
            ip_address="127.0.0.1",
            user_agent="test",
            expires_at=timezone.now() + timedelta(days=1),
        )

        data = {"session_id": str(session.id)}

        response = self.client.delete(self.url, data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("message", response.data)

        # Verify session was deactivated
        session.refresh_from_db()
        self.assertFalse(session.is_active)

    def test_delete_nonexistent_session(self):
        """Test deleting nonexistent session"""
        data = {"session_id": "nonexistent-id"}

        response = self.client.delete(self.url, data)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_delete_all_sessions(self):
        """Test deleting all sessions"""
        UserSession.objects.create(
            user=self.user,
            token_hash="hash1",
            ip_address="127.0.0.1",
            user_agent="test",
            expires_at=timezone.now() + timedelta(days=1),
        )

        response = self.client.delete(self.url, {})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("message", response.data)


class TestApiHomeView(APITestCase):
    """Test api_home view"""

    def setUp(self):
        self.url = reverse("api_home")

    def test_api_home_json_response(self):
        """Test API home with JSON response"""
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("main_routes", response.data)
        self.assertIn("service_info", response.data)
        self.assertIn("api_title", response.data)

    @patch("apps.authentication.views.loader.get_template")
    def test_api_home_html_response(self, mock_get_template):
        """Test API home with HTML response"""
        mock_template = MagicMock()
        mock_template.render.return_value = "<html>Test</html>"
        mock_get_template.return_value = mock_template

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.content.decode(), "<html>Test</html>")

    @patch("apps.authentication.views.loader.get_template")
    def test_api_home_template_not_found(self, mock_get_template):
        """Test API home when template not found"""
        mock_get_template.side_effect = Exception("Template not found")

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("main_routes", response.data)
