"""
Comprehensive tests for OAuth functionality to improve coverage
"""

import json
from unittest.mock import MagicMock, patch

import requests
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.authentication.models import Company, User
from apps.authentication.oauth import create_or_update_user_from_github, exchange_code_for_token, get_github_user_data


class TestExchangeCodeForToken(TestCase):
    """Test exchange_code_for_token function"""

    @patch("apps.authentication.oauth.requests.post")
    @patch("apps.authentication.oauth.settings")
    def test_exchange_code_for_token_success(self, mock_settings, mock_post):
        """Test successful code exchange"""
        mock_settings.GITHUB_CLIENT_ID = "test_client_id"
        mock_settings.GITHUB_CLIENT_SECRET = "test_client_secret"

        mock_response = MagicMock()
        mock_response.json.return_value = {"access_token": "test_access_token"}
        mock_post.return_value = mock_response

        result = exchange_code_for_token("test_code")

        self.assertEqual(result, "test_access_token")
        mock_post.assert_called_once_with(
            "https://github.com/login/oauth/access_token",
            data={"client_id": "test_client_id", "client_secret": "test_client_secret", "code": "test_code"},
            headers={"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"},
        )

    @patch("apps.authentication.oauth.requests.post")
    @patch("apps.authentication.oauth.settings")
    def test_exchange_code_for_token_request_exception(self, mock_settings, mock_post):
        """Test request exception during code exchange"""
        mock_settings.GITHUB_CLIENT_ID = "test_client_id"
        mock_settings.GITHUB_CLIENT_SECRET = "test_client_secret"

        mock_post.side_effect = requests.RequestException("Network error")

        with self.assertRaises(requests.RequestException):
            exchange_code_for_token("test_code")

    @patch("apps.authentication.oauth.requests.post")
    @patch("apps.authentication.oauth.settings")
    def test_exchange_code_for_token_no_access_token(self, mock_settings, mock_post):
        """Test response without access token"""
        mock_settings.GITHUB_CLIENT_ID = "test_client_id"
        mock_settings.GITHUB_CLIENT_SECRET = "test_client_secret"

        mock_response = MagicMock()
        mock_response.json.return_value = {"error": "invalid_grant"}
        mock_post.return_value = mock_response

        result = exchange_code_for_token("test_code")

        self.assertIsNone(result)


class TestGetGitHubUserData(TestCase):
    """Test get_github_user_data function"""

    @patch("apps.authentication.oauth.requests.get")
    def test_get_github_user_data_success(self, mock_get):
        """Test successful user data retrieval"""
        # Mock user API response
        user_response = MagicMock()
        user_response.json.return_value = {
            "id": 12345,
            "login": "testuser",
            "email": "test@example.com",
            "name": "Test User",
            "company": "Test Company",
        }

        # Mock emails API response
        emails_response = MagicMock()
        emails_response.json.return_value = [{"email": "test@example.com", "primary": True}]

        mock_get.side_effect = [user_response, emails_response]

        result = get_github_user_data("test_token")

        expected = {
            "id": 12345,
            "login": "testuser",
            "email": "test@example.com",
            "name": "Test User",
            "company": "Test Company",
        }

        self.assertEqual(result, expected)

    @patch("apps.authentication.oauth.requests.get")
    def test_get_github_user_data_emails_api_fails(self, mock_get):
        """Test user data retrieval when emails API fails"""
        # Mock user API response
        user_response = MagicMock()
        user_response.json.return_value = {
            "id": 12345,
            "login": "testuser",
            "email": "fallback@example.com",
            "name": "Test User",
            "company": "Test Company",
        }

        # Mock emails API failure
        emails_response = MagicMock()
        emails_response.raise_for_status.side_effect = requests.RequestException("API Error")

        mock_get.side_effect = [user_response, emails_response]

        result = get_github_user_data("test_token")

        self.assertEqual(result["email"], "fallback@example.com")

    @patch("apps.authentication.oauth.requests.get")
    def test_get_github_user_data_no_primary_email(self, mock_get):
        """Test user data retrieval with no primary email"""
        # Mock user API response
        user_response = MagicMock()
        user_response.json.return_value = {"id": 12345, "login": "testuser", "email": None, "name": "Test User"}

        # Mock emails API response with no primary email
        emails_response = MagicMock()
        emails_response.json.return_value = [{"email": "secondary@example.com", "primary": False}]

        mock_get.side_effect = [user_response, emails_response]

        result = get_github_user_data("test_token")

        self.assertEqual(result["email"], "secondary@example.com")

    @patch("apps.authentication.oauth.requests.get")
    def test_get_github_user_data_no_emails(self, mock_get):
        """Test user data retrieval with no emails"""
        # Mock user API response
        user_response = MagicMock()
        user_response.json.return_value = {"id": 12345, "login": "testuser", "email": None, "name": "Test User"}

        # Mock emails API response with empty list
        emails_response = MagicMock()
        emails_response.json.return_value = []

        mock_get.side_effect = [user_response, emails_response]

        result = get_github_user_data("test_token")

        self.assertIsNone(result["email"])


class TestCreateOrUpdateUserFromGitHub(TestCase):
    """Test create_or_update_user_from_github function"""

    def setUp(self):
        """Set up test data"""
        self.github_data = {
            "id": 12345,
            "login": "testuser",
            "email": "test@example.com",
            "name": "Test User",
            "company": "Test Company",
        }

    def test_create_or_update_user_no_email(self):
        """Test user creation with no email"""
        github_data = self.github_data.copy()
        github_data["email"] = None

        with self.assertRaises(ValueError) as cm:
            create_or_update_user_from_github(github_data)

        self.assertIn("GitHub account must have a verified email address", str(cm.exception))

    def test_create_or_update_user_existing_github_id(self):
        """Test creating new user when no existing user with same email"""
        # Create existing user with different email
        existing_user = User.objects.create_user(email="old@example.com", first_name="Old", last_name="User")

        # This should create a new user since email doesn't match
        user, is_new_user = create_or_update_user_from_github(self.github_data)

        self.assertEqual(user.email, "test@example.com")
        self.assertEqual(user.first_name, "Test")
        self.assertEqual(user.last_name, "User")
        self.assertEqual(user.role, "developer")
        self.assertTrue(is_new_user)

    def test_create_or_update_user_existing_email(self):
        """Test updating existing user by email"""
        # Create existing user
        existing_user = User.objects.create_user(email="test@example.com", first_name="Old", last_name="User")

        # This should update the existing user
        user, is_new_user = create_or_update_user_from_github(self.github_data)

        self.assertEqual(user.id, existing_user.id)  # Same user
        self.assertEqual(user.email, "test@example.com")
        self.assertEqual(user.first_name, "Old")  # Preserved existing name
        self.assertEqual(user.last_name, "User")  # Preserved existing name
        self.assertFalse(is_new_user)

    def test_create_or_update_user_existing_email_with_company(self):
        """Test updating existing user with company"""
        # Create existing user
        existing_user = User.objects.create_user(email="test@example.com", first_name="Old", last_name="User")

        # This should update the existing user
        user, is_new_user = create_or_update_user_from_github(self.github_data)

        self.assertEqual(user.id, existing_user.id)  # Same user
        self.assertEqual(user.email, "test@example.com")
        self.assertEqual(user.first_name, "Old")  # Preserved existing name
        self.assertEqual(user.last_name, "User")  # Preserved existing name
        self.assertFalse(is_new_user)

    def test_create_new_user(self):
        """Test creating new user"""
        user, is_new_user = create_or_update_user_from_github(self.github_data)

        self.assertEqual(user.email, "test@example.com")
        self.assertEqual(user.first_name, "Test")
        self.assertEqual(user.last_name, "User")
        self.assertEqual(user.role, "developer")
        self.assertIsNotNone(user.company)
        self.assertEqual(user.company.name, "Test Company")
        self.assertTrue(is_new_user)

    def test_create_new_user_no_company(self):
        """Test creating new user without company"""
        github_data = self.github_data.copy()
        github_data["company"] = None

        user, is_new_user = create_or_update_user_from_github(github_data)

        self.assertEqual(user.email, "test@example.com")
        self.assertEqual(user.first_name, "Test")
        self.assertEqual(user.last_name, "User")
        self.assertEqual(user.role, "developer")
        self.assertIsNone(user.company)
        self.assertTrue(is_new_user)

    def test_create_new_user_no_name(self):
        """Test creating new user without name"""
        github_data = self.github_data.copy()
        github_data["name"] = None

        user, is_new_user = create_or_update_user_from_github(github_data)

        self.assertEqual(user.email, "test@example.com")
        self.assertEqual(user.first_name, "")  # Empty since no name provided
        self.assertEqual(user.last_name, "")  # Empty since no name provided
        self.assertEqual(user.role, "developer")
        self.assertTrue(is_new_user)

    def test_create_new_user_empty_name(self):
        """Test creating new user with empty name"""
        github_data = self.github_data.copy()
        github_data["name"] = ""

        user, is_new_user = create_or_update_user_from_github(github_data)

        self.assertEqual(user.email, "test@example.com")
        self.assertEqual(user.first_name, "")  # Empty since name is empty
        self.assertEqual(user.last_name, "")  # Empty since name is empty
        self.assertEqual(user.role, "developer")
        self.assertTrue(is_new_user)

    def test_create_new_user_single_name(self):
        """Test creating new user with single name"""
        github_data = self.github_data.copy()
        github_data["name"] = "SingleName"

        user, is_new_user = create_or_update_user_from_github(github_data)

        self.assertEqual(user.email, "test@example.com")
        self.assertEqual(user.first_name, "SingleName")  # First name gets the single name
        self.assertEqual(user.last_name, "")  # Last name is empty
        self.assertEqual(user.role, "developer")
        self.assertTrue(is_new_user)


class TestGitHubOAuthViews(APITestCase):
    """Test GitHub OAuth API views"""

    def setUp(self):
        """Set up test client"""
        self.callback_url = reverse("github_oauth_callback")
        self.oauth_url_endpoint = reverse("github_oauth_url")

    @patch("apps.authentication.oauth.settings")
    def test_github_oauth_url_success(self, mock_settings):
        """Test successful OAuth URL generation"""
        mock_settings.GITHUB_CLIENT_ID = "test_client_id"

        response = self.client.get(self.oauth_url_endpoint)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("oauth_url", response.data)
        self.assertIn("github.com/login/oauth/authorize", response.data["oauth_url"])

    @patch("apps.authentication.oauth.settings")
    def test_github_oauth_url_no_client_id(self, mock_settings):
        """Test OAuth URL generation without client ID"""
        mock_settings.GITHUB_CLIENT_ID = None

        response = self.client.get(self.oauth_url_endpoint)

        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertIn("error", response.data)

    @patch("apps.authentication.oauth.settings")
    def test_github_oauth_url_https_forwarded(self, mock_settings):
        """Test OAuth URL generation with HTTPS forwarded"""
        mock_settings.GITHUB_CLIENT_ID = "test_client_id"

        response = self.client.get(self.oauth_url_endpoint, HTTP_X_FORWARDED_PROTO="https")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("https://", response.data["oauth_url"])

    @patch("apps.authentication.oauth.settings")
    def test_github_oauth_url_railway_domain(self, mock_settings):
        """Test OAuth URL generation with Railway domain"""
        mock_settings.GITHUB_CLIENT_ID = "test_client_id"

        with self.settings(ALLOWED_HOSTS=["test.railway.app"]):
            response = self.client.get(self.oauth_url_endpoint, HTTP_HOST="test.railway.app")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_github_oauth_callback_no_code(self):
        """Test OAuth callback without code"""
        response = self.client.get(self.callback_url)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.data)

    @patch("apps.authentication.oauth.settings")
    def test_github_oauth_callback_no_config(self, mock_settings):
        """Test OAuth callback without GitHub configuration"""
        mock_settings.GITHUB_CLIENT_ID = None
        mock_settings.GITHUB_CLIENT_SECRET = None

        response = self.client.get(self.callback_url + "?code=test_code")

        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertIn("error", response.data)

    @patch("apps.authentication.oauth.create_user_session")
    @patch("apps.authentication.oauth.get_tokens_for_user")
    @patch("apps.authentication.oauth.create_or_update_user_from_github")
    @patch("apps.authentication.oauth.get_github_user_data")
    @patch("apps.authentication.oauth.exchange_code_for_token")
    @patch("apps.authentication.oauth.settings")
    def test_github_oauth_callback_success(
        self, mock_settings, mock_exchange, mock_get_user_data, mock_create_user, mock_get_tokens, mock_create_session
    ):
        """Test successful OAuth callback"""
        mock_settings.GITHUB_CLIENT_ID = "test_client_id"
        mock_settings.GITHUB_CLIENT_SECRET = "test_client_secret"

        mock_exchange.return_value = "access_token"
        mock_get_user_data.return_value = {"id": 12345, "login": "testuser", "email": "test@example.com", "name": "Test User"}

        mock_user = User.objects.create_user(email="test@example.com", first_name="Test", last_name="User")
        mock_create_user.return_value = (mock_user, True)  # Return tuple (user, is_new_user)
        mock_get_tokens.return_value = {"access": "token", "refresh": "token"}
        mock_create_session.return_value = (MagicMock(), "session_token")

        response = self.client.get(self.callback_url + "?code=test_code")

        # Web OAuth flow should redirect to frontend (302) instead of returning JSON
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        # Check that it redirects to frontend callback with token_key
        self.assertTrue(response.url.startswith("https://syncscope-frontend-dev.up.railway.app/auth/github/callback"))
        self.assertIn("token_key=", response.url)

    @patch("apps.authentication.oauth.exchange_code_for_token")
    @patch("apps.authentication.oauth.settings")
    def test_github_oauth_callback_request_exception(self, mock_settings, mock_exchange):
        """Test OAuth callback with request exception"""
        mock_settings.GITHUB_CLIENT_ID = "test_client_id"
        mock_settings.GITHUB_CLIENT_SECRET = "test_client_secret"

        mock_exchange.side_effect = requests.RequestException("GitHub API error")

        response = self.client.get(self.callback_url + "?code=test_code")

        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        self.assertIn("error", response.data)

    @patch("apps.authentication.oauth.create_or_update_user_from_github")
    @patch("apps.authentication.oauth.get_github_user_data")
    @patch("apps.authentication.oauth.exchange_code_for_token")
    @patch("apps.authentication.oauth.settings")
    def test_github_oauth_callback_value_error(self, mock_settings, mock_exchange, mock_get_user_data, mock_create_user):
        """Test OAuth callback with value error"""
        mock_settings.GITHUB_CLIENT_ID = "test_client_id"
        mock_settings.GITHUB_CLIENT_SECRET = "test_client_secret"

        mock_exchange.return_value = "access_token"
        mock_get_user_data.return_value = {}
        mock_create_user.side_effect = ValueError("Invalid user data")

        response = self.client.get(self.callback_url + "?code=test_code")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.data)

    @patch("apps.authentication.oauth.exchange_code_for_token")
    @patch("apps.authentication.oauth.settings")
    def test_github_oauth_callback_general_exception(self, mock_settings, mock_exchange):
        """Test OAuth callback with general exception"""
        mock_settings.GITHUB_CLIENT_ID = "test_client_id"
        mock_settings.GITHUB_CLIENT_SECRET = "test_client_secret"

        mock_exchange.side_effect = Exception("Unexpected error")

        response = self.client.get(self.callback_url + "?code=test_code")

        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertIn("error", response.data)
