import os

import django
import pytest
from django.conf import settings

# Configure Django settings before importing anything else
if not settings.configured:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.test_settings")
    django.setup()

from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.authentication.models import Company, SupervisedUser, UserSession

User = get_user_model()


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def company():
    return Company.objects.create(name="Test Company", domain="@testcompany.com", industry="Technology", size="Small")


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
def supervisor_user(company):
    return User.objects.create_user(
        email="supervisor@testcompany.com",
        password="supervisorpassword123",
        first_name="Supervisor",
        last_name="User",
        role="supervisor",
        company=company,
        timezone="UTC",
        is_active=True,
        is_staff=False,
        is_superuser=False,
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
def supervisor_authenticated_client(api_client, supervisor_user):
    refresh = RefreshToken.for_user(supervisor_user)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
    return api_client


@pytest.fixture
def supervised_user_relationship(user, supervisor_user):
    return SupervisedUser.objects.create(user=user, supervisor=supervisor_user, monitoring_enabled=True)


@pytest.fixture
def user_session(user):
    from apps.authentication.utils import create_user_session

    session, token = create_user_session(user)
    return session, token
