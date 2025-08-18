from unittest.mock import Mock, patch

import pytest
import requests
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status

from apps.authentication.models import Company

User = get_user_model()


@pytest.mark.django_db
class TestGitHubOAuthEdgeCases:

    def test_github_oauth_url_missing_client_id_setting(self, api_client):
        """Test OAuth URL generation when GITHUB_CLIENT_ID is not set."""
        url = reverse("github_oauth_url")

        # Remove or set to None
        with patch("django.conf.settings.GITHUB_CLIENT_ID", None):
            response = api_client.get(url)

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "GitHub OAuth not configured" in response.data["error"]

    def test_github_oauth_url_empty_client_id(self, api_client):
        """Test OAuth URL generation when GITHUB_CLIENT_ID is empty."""
        url = reverse("github_oauth_url")

        with patch("django.conf.settings.GITHUB_CLIENT_ID", ""):
            response = api_client.get(url)

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "GitHub OAuth not configured" in response.data["error"]

    @patch("apps.authentication.oauth.exchange_code_for_token")
    def test_github_oauth_callback_missing_client_secret(self, mock_exchange_token, api_client):
        """Test OAuth callback when GITHUB_CLIENT_SECRET is not configured."""
        url = reverse("github_oauth_callback")
        data = {"code": "test_authorization_code"}

        with (
            patch("django.conf.settings.GITHUB_CLIENT_ID", "test_client_id"),
            patch("django.conf.settings.GITHUB_CLIENT_SECRET", None),
        ):

            response = api_client.post(url, data)

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "GitHub OAuth not configured" in response.data["error"]

    @patch("apps.authentication.oauth.exchange_code_for_token")
    @patch("apps.authentication.oauth.get_github_user_data")
    def test_github_oauth_callback_partial_name(self, mock_get_user_data, mock_exchange_token, api_client):
        """Test OAuth callback with partial name from GitHub."""
        mock_exchange_token.return_value = "test_access_token"
        mock_get_user_data.return_value = {
            "id": 123456,
            "login": "testuser",
            "email": "test@example.com",
            "name": "TestUser",  # Single name, no space
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

        # Check user was created with partial name
        user = User.objects.get(email="test@example.com")
        assert user.first_name == "TestUser"
        assert user.last_name == "."

    @patch("apps.authentication.oauth.exchange_code_for_token")
    @patch("apps.authentication.oauth.get_github_user_data")
    def test_github_oauth_callback_null_name(self, mock_get_user_data, mock_exchange_token, api_client):
        """Test OAuth callback with null name from GitHub."""
        mock_exchange_token.return_value = "test_access_token"
        mock_get_user_data.return_value = {
            "id": 123456,
            "login": "testuser",
            "email": "test@example.com",
            "name": None,
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

        # Check user was created with username as fallback
        user = User.objects.get(email="test@example.com")
        assert user.first_name == "testuser"
        assert user.last_name == "."

    @patch("apps.authentication.oauth.exchange_code_for_token")
    @patch("apps.authentication.oauth.get_github_user_data")
    def test_github_oauth_callback_existing_company_update(self, mock_get_user_data, mock_exchange_token, api_client):
        """Test OAuth callback updates existing user's company."""
        # Create existing user without company
        user = User.objects.create_user(email="test@example.com", password=None, first_name="Test", last_name="User")

        mock_exchange_token.return_value = "test_access_token"
        mock_get_user_data.return_value = {
            "id": 123456,
            "login": "testuser",
            "email": "test@example.com",
            "name": "Updated User",
            "avatar_url": "https://avatar.url",
            "company": "New Company",
        }

        url = reverse("github_oauth_callback")
        data = {"code": "test_authorization_code"}

        with (
            patch("django.conf.settings.GITHUB_CLIENT_ID", "test_client_id"),
            patch("django.conf.settings.GITHUB_CLIENT_SECRET", "test_client_secret"),
        ):

            response = api_client.post(url, data)

        assert response.status_code == status.HTTP_200_OK

        user.refresh_from_db()
        assert user.company is not None
        assert user.company.name == "New Company"


@pytest.mark.django_db
class TestOAuthUtilsEdgeCases:

    @patch("requests.post")
    def test_exchange_code_for_token_http_error(self, mock_post):
        """Test token exchange with HTTP error."""
        from apps.authentication.oauth import exchange_code_for_token

        mock_response = Mock()
        mock_response.raise_for_status.side_effect = requests.HTTPError("HTTP 400")
        mock_post.return_value = mock_response

        with (
            patch("django.conf.settings.GITHUB_CLIENT_ID", "test_client_id"),
            patch("django.conf.settings.GITHUB_CLIENT_SECRET", "test_client_secret"),
        ):

            with pytest.raises(requests.HTTPError):
                exchange_code_for_token("test_code")

    @patch("requests.post")
    def test_exchange_code_for_token_missing_access_token(self, mock_post):
        """Test token exchange when response doesn't contain access_token."""
        from apps.authentication.oauth import exchange_code_for_token

        mock_response = Mock()
        mock_response.json.return_value = {"error": "invalid_grant"}
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        with (
            patch("django.conf.settings.GITHUB_CLIENT_ID", "test_client_id"),
            patch("django.conf.settings.GITHUB_CLIENT_SECRET", "test_client_secret"),
        ):

            token = exchange_code_for_token("test_code")
            assert token is None

    @patch("requests.get")
    def test_get_github_user_data_http_error(self, mock_get):
        """Test GitHub user data retrieval with HTTP error."""
        from apps.authentication.oauth import get_github_user_data

        mock_response = Mock()
        mock_response.raise_for_status.side_effect = requests.HTTPError("HTTP 401")
        mock_get.return_value = mock_response

        with pytest.raises(requests.HTTPError):
            get_github_user_data("test_token")

    @patch("requests.get")
    def test_get_github_user_data_no_primary_email(self, mock_get):
        """Test GitHub user data when no primary email is found."""
        from apps.authentication.oauth import get_github_user_data

        user_response = Mock()
        user_response.json.return_value = {
            "id": 123456,
            "login": "testuser",
            "email": None,  # No public email
            "name": "Test User",
            "avatar_url": "https://avatar.url",
            "company": None,
        }
        user_response.raise_for_status.return_value = None

        emails_response = Mock()
        emails_response.json.return_value = [
            {"email": "private@example.com", "primary": False},
            {"email": "other@example.com", "primary": False},
        ]
        emails_response.raise_for_status.return_value = None

        mock_get.side_effect = [user_response, emails_response]

        user_data = get_github_user_data("test_token")

        # Should fallback to first email if no primary found
        assert user_data["email"] == "private@example.com"

    @patch("requests.get")
    def test_get_github_user_data_empty_emails(self, mock_get):
        """Test GitHub user data when emails list is empty."""
        from apps.authentication.oauth import get_github_user_data

        user_response = Mock()
        user_response.json.return_value = {
            "id": 123456,
            "login": "testuser",
            "email": None,
            "name": "Test User",
            "avatar_url": "https://avatar.url",
            "company": None,
        }
        user_response.raise_for_status.return_value = None

        emails_response = Mock()
        emails_response.json.return_value = []  # No emails
        emails_response.raise_for_status.return_value = None

        mock_get.side_effect = [user_response, emails_response]

        user_data = get_github_user_data("test_token")

        # Should keep email as None if no emails available
        assert user_data["email"] is None

    @patch("requests.get")
    def test_get_github_user_data_emails_api_error(self, mock_get):
        """Test GitHub user data when emails API fails."""
        from apps.authentication.oauth import get_github_user_data

        user_response = Mock()
        user_response.json.return_value = {
            "id": 123456,
            "login": "testuser",
            "email": "public@example.com",  # Has public email
            "name": "Test User",
            "avatar_url": "https://avatar.url",
            "company": None,
        }
        user_response.raise_for_status.return_value = None

        emails_response = Mock()
        emails_response.raise_for_status.side_effect = requests.HTTPError("HTTP 403")

        mock_get.side_effect = [user_response, emails_response]

        user_data = get_github_user_data("test_token")

        # Should use public email when emails API fails
        assert user_data["email"] == "public@example.com"


@pytest.mark.django_db
class TestGitHubOAuthCompanyHandling:

    @patch("apps.authentication.oauth.exchange_code_for_token")
    @patch("apps.authentication.oauth.get_github_user_data")
    def test_oauth_company_creation_with_email_domain(self, mock_get_user_data, mock_exchange_token, api_client):
        """Test that company is created with proper domain from email."""
        mock_exchange_token.return_value = "test_access_token"
        mock_get_user_data.return_value = {
            "id": 123456,
            "login": "testuser",
            "email": "test@mycompany.com",
            "name": "Test User",
            "avatar_url": "https://avatar.url",
            "company": "My Company",
        }

        url = reverse("github_oauth_callback")
        data = {"code": "test_authorization_code"}

        with (
            patch("django.conf.settings.GITHUB_CLIENT_ID", "test_client_id"),
            patch("django.conf.settings.GITHUB_CLIENT_SECRET", "test_client_secret"),
        ):

            response = api_client.post(url, data)

        assert response.status_code == status.HTTP_200_OK

        # Check company was created with correct domain
        user = User.objects.get(email="test@mycompany.com")
        assert user.company.name == "My Company"
        assert user.company.domain == "@mycompany.com"

    @patch("apps.authentication.oauth.exchange_code_for_token")
    @patch("apps.authentication.oauth.get_github_user_data")
    def test_oauth_existing_company_with_matching_domain(self, mock_get_user_data, mock_exchange_token, api_client):
        """Test OAuth with existing company that has matching domain."""
        # Create existing company
        existing_company = Company.objects.create(name="Existing Company", domain="@mycompany.com")

        mock_exchange_token.return_value = "test_access_token"
        mock_get_user_data.return_value = {
            "id": 123456,
            "login": "testuser",
            "email": "test@mycompany.com",
            "name": "Test User",
            "avatar_url": "https://avatar.url",
            "company": "Existing Company",
        }

        url = reverse("github_oauth_callback")
        data = {"code": "test_authorization_code"}

        with (
            patch("django.conf.settings.GITHUB_CLIENT_ID", "test_client_id"),
            patch("django.conf.settings.GITHUB_CLIENT_SECRET", "test_client_secret"),
        ):

            response = api_client.post(url, data)

        assert response.status_code == status.HTTP_200_OK

        # Should use existing company
        user = User.objects.get(email="test@mycompany.com")
        assert user.company.id == existing_company.id

        # Should not create duplicate company
        assert Company.objects.filter(name="Existing Company").count() == 1
