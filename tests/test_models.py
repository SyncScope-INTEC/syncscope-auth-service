from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.authentication.models import Company, UserSession

User = get_user_model()


@pytest.mark.django_db
class TestCompanyModel:

    def test_create_company(self):
        company = Company.objects.create(name="Test Company", domain="@testcompany.com")
        assert company.name == "Test Company"
        assert company.domain == "@testcompany.com"
        assert company.id is not None
        assert company.created_at is not None
        assert company.updated_at is not None

    def test_company_str_representation(self):
        company = Company.objects.create(name="Test Company", domain="@testcompany.com")
        assert str(company) == "Test Company"

    def test_domain_auto_format(self):
        company = Company(name="Test Company", domain="testcompany.com")
        company.clean()
        assert company.domain == "@testcompany.com"

    def test_company_name_uniqueness(self):
        Company.objects.create(name="Test Company", domain="@testcompany.com")
        with pytest.raises(Exception):
            Company.objects.create(name="Test Company", domain="@anotherdomain.com")

    def test_company_domain_uniqueness(self):
        Company.objects.create(name="Test Company", domain="@testcompany.com")
        with pytest.raises(Exception):
            Company.objects.create(name="Another Company", domain="@testcompany.com")

    def test_company_timestamps_auto_update(self):
        import time
        company = Company.objects.create(name="Test Company", domain="@testcompany.com")
        original_updated_at = company.updated_at
        
        time.sleep(0.01)
        company.name = "Updated Company"
        company.save()
        
        assert company.updated_at > original_updated_at


@pytest.mark.django_db
class TestUserModel:

    def test_create_user(self, company):
        user = User.objects.create_user(
            email="test@testcompany.com", 
            password="testpassword123", 
            first_name="Test", 
            last_name="User", 
            company=company
        )
        assert user.email == "test@testcompany.com"
        assert user.first_name == "Test"
        assert user.last_name == "User"
        assert user.company == company
        assert user.role == "developer"
        assert user.timezone == "UTC"
        assert user.is_active is True
        assert user.is_staff is False
        assert user.is_superuser is False
        assert user.check_password("testpassword123")
        assert user.date_joined is not None
        assert user.updated_at is not None

    def test_user_str_representation(self, company):
        user = User.objects.create_user(
            email="test@testcompany.com", 
            password="testpassword123", 
            first_name="Test", 
            last_name="User", 
            company=company
        )
        assert str(user) == "Test User (test@testcompany.com)"

    def test_full_name_property(self, company):
        user = User.objects.create_user(
            email="test@testcompany.com", 
            password="testpassword123", 
            first_name="Test", 
            last_name="User", 
            company=company
        )
        assert user.full_name == "Test User"

    def test_created_at_property(self, company):
        user = User.objects.create_user(
            email="test@testcompany.com", 
            password="testpassword123", 
            first_name="Test", 
            last_name="User", 
            company=company
        )
        assert user.created_at == user.date_joined

    def test_email_domain_validation(self, company):
        with pytest.raises(ValidationError):
            user = User(
                email="test@wrongdomain.com", 
                first_name="Test", 
                last_name="User", 
                company=company
            )
            user.clean()

    def test_email_case_normalization(self, company):
        user = User.objects.create_user(
            email="TEST@TESTCOMPANY.COM", 
            password="testpassword123", 
            first_name="Test", 
            last_name="User", 
            company=company
        )
        assert user.email == "test@testcompany.com"

    def test_user_roles(self, company):
        admin_user = User.objects.create_user(
            email="admin@testcompany.com",
            password="testpassword123",
            first_name="Admin",
            last_name="User",
            role="admin",
            company=company,
        )
        assert admin_user.role == "admin"
        
        developer_user = User.objects.create_user(
            email="dev@testcompany.com",
            password="testpassword123",
            first_name="Dev",
            last_name="User",
            role="developer",
            company=company,
        )
        assert developer_user.role == "developer"
        
        manager_user = User.objects.create_user(
            email="manager@testcompany.com",
            password="testpassword123",
            first_name="Manager",
            last_name="User",
            role="manager",
            company=company,
        )
        assert manager_user.role == "manager"

    def test_user_email_uniqueness(self, company):
        User.objects.create_user(
            email="test@testcompany.com",
            password="testpassword123",
            first_name="Test",
            last_name="User",
            company=company,
        )
        with pytest.raises(Exception):
            User.objects.create_user(
                email="test@testcompany.com",
                password="testpassword123",
                first_name="Another",
                last_name="User",
                company=company,
            )

    def test_user_timestamps_auto_update(self, company):
        import time
        user = User.objects.create_user(
            email="test@testcompany.com",
            password="testpassword123",
            first_name="Test",
            last_name="User",
            company=company,
        )
        original_updated_at = user.updated_at
        
        time.sleep(0.01)
        user.first_name = "Updated"
        user.save()
        
        assert user.updated_at > original_updated_at

    def test_github_user_creation(self):
        user = User.objects.create_user(
            email="github@example.com", 
            first_name="GitHub", 
            last_name="User", 
            password=None
        )
        assert user.email == "github@example.com"
        assert user.first_name == "GitHub"
        assert user.last_name == "User"
        assert user.role == "developer"
        assert user.timezone == "UTC"
        assert user.is_active is True

    def test_user_without_company(self):
        user = User.objects.create_user(
            email="nocompany@example.com",
            password="testpassword123",
            first_name="No",
            last_name="Company",
        )
        assert user.company is None
        assert user.email == "nocompany@example.com"

    def test_user_timezone_field(self, company):
        user = User.objects.create_user(
            email="test@testcompany.com",
            password="testpassword123",
            first_name="Test",
            last_name="User",
            company=company,
            timezone="America/New_York",
        )
        assert user.timezone == "America/New_York"

    def test_user_staff_and_superuser_flags(self, company):
        staff_user = User.objects.create_user(
            email="staff@testcompany.com",
            password="testpassword123",
            first_name="Staff",
            last_name="User",
            company=company,
            is_staff=True,
        )
        assert staff_user.is_staff is True
        assert staff_user.is_superuser is False
        
        super_user = User.objects.create_user(
            email="super@testcompany.com",
            password="testpassword123",
            first_name="Super",
            last_name="User",
            company=company,
            is_staff=True,
            is_superuser=True,
        )
        assert super_user.is_staff is True
        assert super_user.is_superuser is True


@pytest.mark.django_db
class TestUserSessionModel:

    def test_create_user_session(self, user):
        from apps.authentication.utils import hash_token

        token = "test_token"
        token_hash = hash_token(token)

        session = UserSession.objects.create(
            user=user, 
            token_hash=token_hash, 
            user_agent="Test User Agent", 
            ip_address="127.0.0.1"
        )

        assert session.user == user
        assert session.token_hash == token_hash
        assert session.is_active is True
        assert session.user_agent == "Test User Agent"
        assert session.ip_address == "127.0.0.1"
        assert session.expires_at is not None
        assert session.created_at is not None
        assert session.last_used is not None

    def test_session_expiry_auto_set(self, user):
        session = UserSession.objects.create(user=user, token_hash="test_hash")
        expected_expiry = timezone.now() + timedelta(days=7)
        # Allow for a few seconds difference
        assert abs((session.expires_at - expected_expiry).total_seconds()) < 10

    def test_session_str_representation(self, user):
        session = UserSession.objects.create(user=user, token_hash="test_hash")
        expected_str = f"Session for {user.email} - {session.created_at}"
        assert str(session) == expected_str

    def test_is_expired_method(self, user):
        # Create expired session
        expired_session = UserSession.objects.create(
            user=user, 
            token_hash="expired_hash", 
            expires_at=timezone.now() - timedelta(hours=1)
        )
        assert expired_session.is_expired() is True

        # Create valid session
        valid_session = UserSession.objects.create(
            user=user, 
            token_hash="valid_hash", 
            expires_at=timezone.now() + timedelta(hours=1)
        )
        assert valid_session.is_expired() is False

    def test_deactivate_session(self, user):
        session = UserSession.objects.create(user=user, token_hash="test_hash")
        assert session.is_active is True

        session.deactivate()
        session.refresh_from_db()
        assert session.is_active is False

    def test_get_active_session(self, user):
        from apps.authentication.utils import hash_token

        token = "test_token"
        token_hash = hash_token(token)

        # Create active session
        session = UserSession.objects.create(
            user=user, 
            token_hash=token_hash, 
            expires_at=timezone.now() + timedelta(hours=1)
        )
        original_last_used = session.last_used

        # Small delay to ensure last_used gets updated
        import time
        time.sleep(0.01)

        retrieved_session = UserSession.get_active_session(token_hash)
        assert retrieved_session == session
        assert retrieved_session.last_used > original_last_used

        # Test with invalid token
        invalid_session = UserSession.get_active_session("invalid_hash")
        assert invalid_session is None

        # Test with inactive session
        session.deactivate()
        inactive_session = UserSession.get_active_session(token_hash)
        assert inactive_session is None

    def test_cleanup_expired_sessions(self, user):
        # Create expired session
        UserSession.objects.create(
            user=user, 
            token_hash="expired_hash", 
            expires_at=timezone.now() - timedelta(hours=1)
        )

        # Create valid session
        valid_session = UserSession.objects.create(
            user=user, 
            token_hash="valid_hash", 
            expires_at=timezone.now() + timedelta(hours=1)
        )

        assert UserSession.objects.count() == 2

        UserSession.cleanup_expired_sessions()

        assert UserSession.objects.count() == 1
        assert UserSession.objects.first() == valid_session

    def test_session_token_hash_uniqueness(self, user):
        UserSession.objects.create(user=user, token_hash="unique_hash")
        with pytest.raises(Exception):
            UserSession.objects.create(user=user, token_hash="unique_hash")

    def test_session_ip_address_types(self, user):
        # Test IPv4
        ipv4_session = UserSession.objects.create(
            user=user, 
            token_hash="ipv4_hash", 
            ip_address="192.168.1.1"
        )
        assert str(ipv4_session.ip_address) == "192.168.1.1"

        # Test IPv6
        ipv6_session = UserSession.objects.create(
            user=user, 
            token_hash="ipv6_hash", 
            ip_address="2001:db8::1"
        )
        assert str(ipv6_session.ip_address) == "2001:db8::1"

        # Test null IP address
        null_ip_session = UserSession.objects.create(
            user=user, 
            token_hash="null_ip_hash", 
            ip_address=None
        )
        assert null_ip_session.ip_address is None

    def test_session_user_agent_field(self, user):
        long_user_agent = "A" * 1000  # Test long user agent string
        session = UserSession.objects.create(
            user=user,
            token_hash="ua_test_hash",
            user_agent=long_user_agent
        )
        assert session.user_agent == long_user_agent

        # Test empty user agent
        empty_ua_session = UserSession.objects.create(
            user=user,
            token_hash="empty_ua_hash",
            user_agent=""
        )
        assert empty_ua_session.user_agent == ""

    def test_session_last_used_auto_update(self, user):
        session = UserSession.objects.create(user=user, token_hash="test_hash")
        original_last_used = session.last_used
        
        import time
        time.sleep(0.01)
        
        session.save()
        assert session.last_used > original_last_used

    def test_multiple_sessions_per_user(self, user):
        session1 = UserSession.objects.create(user=user, token_hash="hash1")
        session2 = UserSession.objects.create(user=user, token_hash="hash2")
        
        user_sessions = UserSession.objects.filter(user=user)
        assert user_sessions.count() == 2
        assert session1 in user_sessions
        assert session2 in user_sessions
