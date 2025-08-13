import pytest
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from apps.authentication.models import Company, UserSession

User = get_user_model()


@pytest.mark.django_db
class TestCompanyModel:
    
    def test_create_company(self):
        company = Company.objects.create(
            name="Test Company",
            domain="@testcompany.com"
        )
        assert company.name == "Test Company"
        assert company.domain == "@testcompany.com"
        assert company.id is not None
        assert company.created_at is not None
        
    def test_company_str_representation(self):
        company = Company.objects.create(
            name="Test Company",
            domain="@testcompany.com"
        )
        assert str(company) == "Test Company"
    
    def test_domain_auto_format(self):
        company = Company(name="Test Company", domain="testcompany.com")
        company.clean()
        assert company.domain == "@testcompany.com"


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
        assert user.check_password("testpassword123")
    
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
            company=company
        )
        assert admin_user.role == "admin"
    
    def test_github_user_creation(self):
        user = User.objects.create_user(
            email="github@example.com",
            first_name="GitHub",
            last_name="User",
            github_id="123456",
            avatar_url="https://avatars.githubusercontent.com/u/123456",
            is_verified=True,
            password=None
        )
        assert user.github_id == "123456"
        assert user.avatar_url == "https://avatars.githubusercontent.com/u/123456"
        assert user.is_verified is True


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
    
    def test_session_expiry_auto_set(self, user):
        session = UserSession.objects.create(
            user=user,
            token_hash="test_hash"
        )
        expected_expiry = timezone.now() + timedelta(days=7)
        # Allow for a few seconds difference
        assert abs((session.expires_at - expected_expiry).total_seconds()) < 10
    
    def test_is_expired_method(self, user):
        # Create expired session
        session = UserSession.objects.create(
            user=user,
            token_hash="test_hash",
            expires_at=timezone.now() - timedelta(hours=1)
        )
        assert session.is_expired() is True
        
        # Create valid session
        session = UserSession.objects.create(
            user=user,
            token_hash="test_hash2",
            expires_at=timezone.now() + timedelta(hours=1)
        )
        assert session.is_expired() is False
    
    def test_deactivate_session(self, user):
        session = UserSession.objects.create(
            user=user,
            token_hash="test_hash"
        )
        assert session.is_active is True
        
        session.deactivate()
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
        
        retrieved_session = UserSession.get_active_session(token_hash)
        assert retrieved_session == session
        
        # Test with invalid token
        invalid_session = UserSession.get_active_session("invalid_hash")
        assert invalid_session is None
    
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