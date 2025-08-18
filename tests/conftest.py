import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.authentication.models import Company, UserSession

User = get_user_model()


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def company():
    return Company.objects.create(name="Test Company", domain="@testcompany.com")


@pytest.fixture
def user(company):
    return User.objects.create_user(
        email="testuser@testcompany.com",
        password="testpassword123",
        first_name="Test",
        last_name="User",
        role="developer",
        company=company,
        timezone="UTC",
        is_active=True,
        is_staff=False,
        is_superuser=False,
    )


@pytest.fixture
def admin_user(company):
    return User.objects.create_user(
        email="admin@testcompany.com",
        password="adminpassword123",
        first_name="Admin",
        last_name="User",
        role="admin",
        company=company,
        timezone="UTC",
        is_active=True,
        is_staff=True,
        is_superuser=False,
    )


@pytest.fixture
def github_user():
    return User.objects.create_user(
        email="githubuser@example.com",
        first_name="GitHub",
        last_name="User",
        password=None,
        role="developer",
        timezone="UTC",
        is_active=True,
        is_staff=False,
        is_superuser=False,
        github_id="123456",
    )


@pytest.fixture
def authenticated_client(api_client, user):
    refresh = RefreshToken.for_user(user)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
    return api_client


@pytest.fixture
def admin_authenticated_client(api_client, admin_user):
    refresh = RefreshToken.for_user(admin_user)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
    return api_client


@pytest.fixture
def user_session(user):
    from apps.authentication.utils import create_user_session

    session, token = create_user_session(user)
    return session, token
