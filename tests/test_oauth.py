from unittest.mock import Mock, patch

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status

from apps.authentication.models import Company

User = get_user_model()


@pytest.mark.django_db
class TestGitHubOAuth:

    def test_github_oauth_url(self, api_client):
        url = reverse("github_oauth_url")

        with patch("django.conf.settings.GITHUB_CLIENT_ID", "test_client_id"):
            response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert "oauth_url" in response.data
        assert "github.com/login/oauth/authorize" in response.data["oauth_url"]
        assert "test_client_id" in response.data["oauth_url"]

    def test_github_oauth_url_not_configured(self, api_client):
        url = reverse("github_oauth_url")

        with patch("django.conf.settings.GITHUB_CLIENT_ID", None):
            response = api_client.get(url)

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "GitHub OAuth not configured" in response.data["error"]

    @patch("apps.authentication.oauth.exchange_code_for_token")
    @patch("apps.authentication.oauth.get_github_user_data")
    def test_github_oauth_callback_new_user(self, mock_get_user_data, mock_exchange_token, api_client):
        # Mock GitHub API responses
        mock_exchange_token.return_value = "test_access_token"
        mock_get_user_data.return_value = {
            "id": 123456,
            "login": "testuser",
            "email": "test@example.com",
            "name": "Test User",
            "avatar_url": "https://avatar.url",
            "company": "Test Company",
        }

        url = reverse("github_oauth_callback")
        data = {"code": "test_authorization_code"}

        with (
            patch("django.conf.settings.GITHUB_CLIENT_ID", "test_client_id"),
            patch("django.conf.settings.GITHUB_CLIENT_SECRET", "test_client_secret"),
        ):
            response = api_client.post(url, data)

        assert response.status_code == status.HTTP_200_OK
        assert "user" in response.data
        assert "tokens" in response.data
        assert "session_token" in response.data
        assert response.data["user"]["email"] == "test@example.com"

        # Check user was created
        user = User.objects.get(email="test@example.com")
        assert user.github_id == "123456"
        assert user.first_name == "Test"
        assert user.last_name == "User"
        assert user.avatar_url == "https://avatar.url"
        assert user.is_verified is True
        assert user.company.name == "Test Company"

    @patch("apps.authentication.oauth.exchange_code_for_token")
    @patch("apps.authentication.oauth.get_github_user_data")
    def test_github_oauth_callback_existing_user_by_email(self, mock_get_user_data, mock_exchange_token, api_client, user):
        # Mock GitHub API responses
        mock_exchange_token.return_value = "test_access_token"
        mock_get_user_data.return_value = {
            "id": 123456,
            "login": "testuser",
            "email": user.email,
            "name": "Updated User",
            "avatar_url": "https://avatar.url",
            "company": None,
        }

        url = reverse("github_oauth_callback")
        data = {"code": "test_authorization_code"}

        with (
            patch("django.conf.settings.GITHUB_CLIENT_ID", "test_client_id"),
            patch("django.conf.settings.GITHUB_CLIENT_SECRET", "test_client_secret"),
        ):
            response = api_client.post(url, data)

        assert response.status_code == status.HTTP_200_OK

        # Check user was updated
        user.refresh_from_db()
        assert user.github_id == "123456"
        assert user.first_name == "Updated"
        assert user.last_name == "User"
        assert user.avatar_url == "https://avatar.url"
        assert user.is_verified is True

    @patch("apps.authentication.oauth.exchange_code_for_token")
    @patch("apps.authentication.oauth.get_github_user_data")
    def test_github_oauth_callback_existing_user_by_github_id(
        self, mock_get_user_data, mock_exchange_token, api_client, github_user
    ):
        # Mock GitHub API responses
        mock_exchange_token.return_value = "test_access_token"
        mock_get_user_data.return_value = {
            "id": int(github_user.github_id),
            "login": "testuser",
            "email": "updated@example.com",
            "name": "Updated GitHub User",
            "avatar_url": "https://new-avatar.url",
            "company": None,
        }

        url = reverse("github_oauth_callback")
        data = {"code": "test_authorization_code"}

        with (
            patch("django.conf.settings.GITHUB_CLIENT_ID", "test_client_id"),
            patch("django.conf.settings.GITHUB_CLIENT_SECRET", "test_client_secret"),
        ):
            response = api_client.post(url, data)

        assert response.status_code == status.HTTP_200_OK

        # Check user was updated
        github_user.refresh_from_db()
        assert github_user.email == "updated@example.com"
        assert github_user.first_name == "Updated"
        assert github_user.last_name == "GitHub User"
        assert github_user.avatar_url == "https://new-avatar.url"

    def test_github_oauth_callback_missing_code(self, api_client):
        url = reverse("github_oauth_callback")
        data = {}

        response = api_client.post(url, data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Authorization code is required" in response.data["error"]

    def test_github_oauth_callback_not_configured(self, api_client):
        url = reverse("github_oauth_callback")
        data = {"code": "test_authorization_code"}

        with patch("django.conf.settings.GITHUB_CLIENT_ID", None):
            response = api_client.post(url, data)

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "GitHub OAuth not configured" in response.data["error"]

    @patch("apps.authentication.oauth.exchange_code_for_token")
    def test_github_oauth_callback_api_error(self, mock_exchange_token, api_client):
        # Mock API error
        mock_exchange_token.side_effect = Exception("GitHub API Error")

        url = reverse("github_oauth_callback")
        data = {"code": "test_authorization_code"}

        with (
            patch("django.conf.settings.GITHUB_CLIENT_ID", "test_client_id"),
            patch("django.conf.settings.GITHUB_CLIENT_SECRET", "test_client_secret"),
        ):
            response = api_client.post(url, data)

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "OAuth authentication failed" in response.data["error"]

    @patch("apps.authentication.oauth.exchange_code_for_token")
    @patch("apps.authentication.oauth.get_github_user_data")
    def test_github_oauth_callback_no_email(self, mock_get_user_data, mock_exchange_token, api_client):
        # Mock GitHub API responses with no email
        mock_exchange_token.return_value = "test_access_token"
        mock_get_user_data.return_value = {
            "id": 123456,
            "login": "testuser",
            "email": None,
            "name": "Test User",
            "avatar_url": "https://avatar.url",
            "company": None,
        }

        url = reverse("github_oauth_callback")
        data = {"code": "test_authorization_code"}

        with (
            patch("django.conf.settings.GITHUB_CLIENT_ID", "test_client_id"),
            patch("django.conf.settings.GITHUB_CLIENT_SECRET", "test_client_secret"),
        ):
            response = api_client.post(url, data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "GitHub account must have a public email" in response.data["error"]


@pytest.mark.django_db
class TestOAuthUtils:

    @patch("requests.post")
    def test_exchange_code_for_token(self, mock_post):
        from apps.authentication.oauth import exchange_code_for_token

        # Mock successful token exchange
        mock_response = Mock()
        mock_response.json.return_value = {"access_token": "test_token"}
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        with (
            patch("django.conf.settings.GITHUB_CLIENT_ID", "test_client_id"),
            patch("django.conf.settings.GITHUB_CLIENT_SECRET", "test_client_secret"),
        ):
            token = exchange_code_for_token("test_code")

        assert token == "test_token"
        assert mock_post.called

    @patch("requests.get")
    def test_get_github_user_data(self, mock_get):
        from apps.authentication.oauth import get_github_user_data

        # Mock GitHub API responses
        user_response = Mock()
        user_response.json.return_value = {
            "id": 123456,
            "login": "testuser",
            "email": "test@example.com",
            "name": "Test User",
            "avatar_url": "https://avatar.url",
            "company": "Test Company",
        }
        user_response.raise_for_status.return_value = None

        emails_response = Mock()
        emails_response.json.return_value = [
            {"email": "test@example.com", "primary": True},
            {"email": "other@example.com", "primary": False},
        ]
        emails_response.raise_for_status.return_value = None

        mock_get.side_effect = [user_response, emails_response]

        user_data = get_github_user_data("test_token")

        assert user_data["id"] == 123456
        assert user_data["email"] == "test@example.com"
        assert user_data["name"] == "Test User"
        assert user_data["avatar_url"] == "https://avatar.url"
        assert user_data["company"] == "Test Company"

    @patch("requests.get")
    def test_get_github_user_data_email_fallback_exception(self, mock_get):
        """Test fallback when emails API fails."""
        from apps.authentication.oauth import get_github_user_data

        # Mock GitHub API responses
        user_response = Mock()
        user_response.json.return_value = {
            "id": 123456,
            "login": "testuser",
            "email": "fallback@example.com",
            "name": "Test User",
            "avatar_url": "https://avatar.url",
            "company": "Test Company",
        }
        user_response.raise_for_status.return_value = None

        # Mock emails API to raise an exception
        emails_response = Mock()
        emails_response.raise_for_status.side_effect = Exception("API Error")

        mock_get.side_effect = [user_response, emails_response]

        user_data = get_github_user_data("test_token")

        assert user_data["email"] == "fallback@example.com"  # Should use fallback

    @patch("requests.get")
    def test_get_github_user_data_no_primary_email_with_list(self, mock_get):
        """Test fallback when no primary email found but emails list exists."""
        from apps.authentication.oauth import get_github_user_data

        # Mock GitHub API responses
        user_response = Mock()
        user_response.json.return_value = {
            "id": 123456,
            "login": "testuser",
            "email": None,  # No email in user data
            "name": "Test User",
        }
        user_response.raise_for_status.return_value = None

        emails_response = Mock()
        emails_response.json.return_value = [
            {"email": "first@example.com", "primary": False},
            {"email": "second@example.com", "primary": False},
        ]
        emails_response.raise_for_status.return_value = None

        mock_get.side_effect = [user_response, emails_response]

        user_data = get_github_user_data("test_token")

        assert user_data["email"] == "first@example.com"  # Should use first email

    @patch("apps.authentication.oauth.exchange_code_for_token")
    @patch("apps.authentication.oauth.get_github_user_data")
    def test_github_oauth_callback_no_name_uses_login(self, mock_get_user_data, mock_exchange_token, api_client):
        """Test user creation when name is empty, should use login as first_name."""
        # Mock GitHub API responses
        mock_exchange_token.return_value = "test_access_token"
        mock_get_user_data.return_value = {
            "id": 123456,
            "login": "testuser",
            "email": "test@example.com",
            "name": "",  # Empty name
            "avatar_url": "https://avatar.url",
            "company": None,
        }

        url = reverse("github_oauth_callback")
        data = {"code": "test_authorization_code"}

        with (
            patch("django.conf.settings.GITHUB_CLIENT_ID", "test_client_id"),
            patch("django.conf.settings.GITHUB_CLIENT_SECRET", "test_client_secret"),
        ):
            response = api_client.post(url, data)

        assert response.status_code == status.HTTP_200_OK

        # Check user was created with login as first_name
        user = User.objects.get(email="test@example.com")
        assert user.first_name == "testuser"  # Should use login
        assert user.last_name == "."

    @patch("apps.authentication.oauth.exchange_code_for_token")
    @patch("apps.authentication.oauth.get_github_user_data")
    def test_github_oauth_callback_with_company_creation(self, mock_get_user_data, mock_exchange_token, api_client):
        """Test company creation when user has github company."""
        # Mock GitHub API responses
        mock_exchange_token.return_value = "test_access_token"
        mock_get_user_data.return_value = {
            "id": 123456,
            "login": "testuser",
            "email": "test@example.com",
            "name": "Test User",
            "avatar_url": "https://avatar.url",
            "company": "New Company",
        }

        # Create existing user by email to test the update path with company
        existing_user = User.objects.create_user(
            email="test@example.com", password="testpass", first_name="Old", last_name="Name"
        )

        url = reverse("github_oauth_callback")
        data = {"code": "test_authorization_code"}

        with (
            patch("django.conf.settings.GITHUB_CLIENT_ID", "test_client_id"),
            patch("django.conf.settings.GITHUB_CLIENT_SECRET", "test_client_secret"),
        ):
            response = api_client.post(url, data)

        assert response.status_code == status.HTTP_200_OK

        # Check user was updated with company
        existing_user.refresh_from_db()
        assert existing_user.company is not None
        assert existing_user.company.name == "New Company"

    @patch("apps.authentication.oauth.exchange_code_for_token")
    def test_github_oauth_callback_requests_exception(self, mock_exchange_token, api_client):
        """Test handling of requests.RequestException."""
        import requests

        # Mock requests.RequestException
        mock_exchange_token.side_effect = requests.RequestException("Network error")

        url = reverse("github_oauth_callback")
        data = {"code": "test_authorization_code"}

        with (
            patch("django.conf.settings.GITHUB_CLIENT_ID", "test_client_id"),
            patch("django.conf.settings.GITHUB_CLIENT_SECRET", "test_client_secret"),
        ):
            response = api_client.post(url, data)

        assert response.status_code == status.HTTP_502_BAD_GATEWAY
        assert "GitHub API error" in response.data["error"]

    def test_github_oauth_url_https_redirect_conditions(self, api_client):
        """Test HTTPS redirect logic for production deployments."""
        from django.test import RequestFactory

        from apps.authentication.oauth import github_oauth_url

        factory = RequestFactory()

        with patch("django.conf.settings.GITHUB_CLIENT_ID", "test_client_id"):
            # Test case 1: Railway.app domain should trigger HTTPS replacement
            request1 = factory.get("/")
            request1.META["HTTP_HOST"] = "myapp.railway.app"

            # Mock build_absolute_uri to return http:// URL that should be replaced
            def mock_build_absolute_uri(path):
                return f"http://{request1.META['HTTP_HOST']}{path}"

            request1.build_absolute_uri = mock_build_absolute_uri

            response1 = github_oauth_url(request1)
            assert response1.status_code == status.HTTP_200_OK
            # Should contain https even though build_absolute_uri returned http
            oauth_url1 = response1.data["oauth_url"]
            assert "https://myapp.railway.app" in oauth_url1

            # Test case 2: X-Forwarded-Proto header should trigger HTTPS replacement
            request2 = factory.get("/")
            request2.META["HTTP_X_FORWARDED_PROTO"] = "https"
            request2.META["HTTP_HOST"] = "example.com"

            def mock_build_absolute_uri2(path):
                return f"http://{request2.META['HTTP_HOST']}{path}"

            request2.build_absolute_uri = mock_build_absolute_uri2

            response2 = github_oauth_url(request2)
            assert response2.status_code == status.HTTP_200_OK
            oauth_url2 = response2.data["oauth_url"]
            assert "https://example.com" in oauth_url2
