from datetime import timedelta
from unittest.mock import Mock, patch

import pytest
from django.contrib.auth import get_user_model
from django.test import RequestFactory
from django.utils import timezone

from apps.authentication.models import UserSession
from apps.authentication.utils import (
    cleanup_expired_sessions,
    create_user_session,
    extract_domain_from_email,
    generate_session_token,
    get_client_ip,
    get_tokens_for_user,
    hash_token,
    invalidate_user_sessions,
    validate_session_token,
)

User = get_user_model()


@pytest.mark.django_db
class TestUtilityFunctions:

    def test_hash_token(self):
        """Test token hashing function."""
        token = "test_token_123"
        hashed = hash_token(token)

        assert hashed != token
        assert len(hashed) == 64  # SHA-256 hex digest length
        assert isinstance(hashed, str)

        # Same token should produce same hash
        assert hash_token(token) == hashed

    def test_get_tokens_for_user(self, user):
        """Test JWT token generation for user."""
        tokens = get_tokens_for_user(user)

        assert "access" in tokens
        assert "refresh" in tokens
        assert isinstance(tokens["access"], str)
        assert isinstance(tokens["refresh"], str)
        assert len(tokens["access"]) > 0
        assert len(tokens["refresh"]) > 0

    def test_create_user_session(self, user):
        """Test user session creation."""
        request = Mock()
        request.META = {"HTTP_USER_AGENT": "Test Browser", "REMOTE_ADDR": "127.0.0.1"}

        session, token = create_user_session(user, request)

        assert isinstance(session, UserSession)
        assert session.user == user
        assert session.is_active is True
        assert session.user_agent == "Test Browser"
        assert session.ip_address == "127.0.0.1"
        assert isinstance(token, str)
        assert len(token) > 0

    def test_validate_session_token_valid(self, user):
        """Test session token validation with valid token."""
        request = Mock()
        request.META = {"HTTP_USER_AGENT": "Test Browser", "REMOTE_ADDR": "127.0.0.1"}

        session, token = create_user_session(user, request)

        validated_session = validate_session_token(token)
        assert validated_session == session

    def test_validate_session_token_invalid(self):
        """Test session token validation with invalid token."""
        invalid_token = "invalid_token_123"
        validated_session = validate_session_token(invalid_token)
        assert validated_session is None

    def test_get_client_ip_x_forwarded_for(self):
        """Test getting client IP from X-Forwarded-For header."""
        request = Mock()
        request.META = {"HTTP_X_FORWARDED_FOR": "203.0.113.195, 70.41.3.18, 150.172.238.178", "REMOTE_ADDR": "127.0.0.1"}

        ip = get_client_ip(request)
        assert ip == "203.0.113.195"  # Should return first IP

    def test_get_client_ip_x_real_ip(self):
        """Test getting client IP from X-Real-IP header."""
        request = Mock()
        request.META = {"HTTP_X_REAL_IP": "203.0.113.195", "REMOTE_ADDR": "127.0.0.1"}

        ip = get_client_ip(request)
        assert ip == "203.0.113.195"

    def test_get_client_ip_remote_addr(self):
        """Test getting client IP from REMOTE_ADDR."""
        request = Mock()
        request.META = {"REMOTE_ADDR": "203.0.113.195"}

        ip = get_client_ip(request)
        assert ip == "203.0.113.195"

    def test_get_client_ip_fallback(self):
        """Test client IP fallback when no headers present."""
        request = Mock()
        request.META = {}

        ip = get_client_ip(request)
        assert ip == "127.0.0.1"  # Should fallback to localhost

    def test_invalidate_user_sessions(self, user):
        """Test invalidating all user sessions."""
        request = Mock()
        request.META = {"HTTP_USER_AGENT": "Test Browser", "REMOTE_ADDR": "127.0.0.1"}

        # Create multiple sessions
        session1, _ = create_user_session(user, request)
        session2, _ = create_user_session(user, request)

        assert UserSession.objects.filter(user=user, is_active=True).count() == 2

        invalidate_user_sessions(user)

        # All sessions should be deactivated
        assert UserSession.objects.filter(user=user, is_active=True).count() == 0
        assert UserSession.objects.filter(user=user, is_active=False).count() == 2

    def test_invalidate_user_sessions_with_exclusion(self, user):
        """Test invalidating user sessions excluding a specific session."""
        request = Mock()
        request.META = {"HTTP_USER_AGENT": "Test Browser", "REMOTE_ADDR": "127.0.0.1"}

        # Create multiple sessions
        session1, _ = create_user_session(user, request)
        session2, _ = create_user_session(user, request)
        session3, _ = create_user_session(user, request)

        # Invalidate all except session2
        invalidate_user_sessions(user, exclude_session_id=session2.id)

        # Session2 should still be active
        session1.refresh_from_db()
        session2.refresh_from_db()
        session3.refresh_from_db()

        assert session1.is_active is False
        assert session2.is_active is True
        assert session3.is_active is False

    def test_generate_session_token(self):
        """Test session token generation."""
        token1 = generate_session_token()
        token2 = generate_session_token()

        # Should be strings
        assert isinstance(token1, str)
        assert isinstance(token2, str)

        # Should be different
        assert token1 != token2

        # Should be URL-safe base64 encoded (43 characters for 32 bytes)
        assert len(token1) == 43
        assert len(token2) == 43

    def test_create_user_session_without_request(self, user):
        """Test creating session without request object."""
        session, token = create_user_session(user)

        assert isinstance(session, UserSession)
        assert session.user == user
        assert session.is_active is True
        assert session.user_agent == ""
        assert session.ip_address is None
        assert isinstance(token, str)

    def test_create_user_session_with_x_forwarded_for(self, user):
        """Test creating session with X-Forwarded-For header."""
        request = Mock()
        request.META = {
            "HTTP_X_FORWARDED_FOR": "203.0.113.1, 198.51.100.1",
            "REMOTE_ADDR": "127.0.0.1",
            "HTTP_USER_AGENT": "Test Browser",
        }

        session, token = create_user_session(user, request)

        # Should use first IP from X-Forwarded-For
        assert session.ip_address == "203.0.113.1"

    def test_create_user_session_expiry_time(self, user):
        """Test that session has correct expiry time."""
        before_creation = timezone.now()
        session, token = create_user_session(user)
        after_creation = timezone.now()

        # Should expire in 7 days
        expected_min = before_creation + timedelta(days=7)
        expected_max = after_creation + timedelta(days=7)

        assert expected_min <= session.expires_at <= expected_max

    def test_validate_session_token_empty(self):
        """Test session token validation with empty/None token."""
        assert validate_session_token(None) is None
        assert validate_session_token("") is None

    def test_cleanup_expired_sessions(self):
        """Test cleanup of expired sessions."""
        with patch.object(UserSession, "cleanup_expired_sessions") as mock_cleanup:
            cleanup_expired_sessions()
            mock_cleanup.assert_called_once()

    def test_extract_domain_from_email_valid(self):
        """Test extracting domain from valid email."""
        assert extract_domain_from_email("user@example.com") == "@example.com"
        assert extract_domain_from_email("test@subdomain.example.org") == "@subdomain.example.org"

    def test_extract_domain_from_email_invalid(self):
        """Test extracting domain from invalid email."""
        assert extract_domain_from_email("invalid_email") is None
        assert extract_domain_from_email("") is None

    def test_extract_domain_from_email_multiple_at(self):
        """Test extracting domain from email with multiple @ symbols."""
        result = extract_domain_from_email("user@domain@example.com")
        # Function splits on @ and takes second part, so gets "domain" from ["user", "domain", "example.com"]
        assert result == "@domain"

    def test_get_client_ip_whitespace_handling(self):
        """Test client IP handling with whitespace in headers."""
        request = Mock()
        request.META = {"HTTP_X_FORWARDED_FOR": " 203.0.113.1 , 198.51.100.1 "}

        ip = get_client_ip(request)
        assert ip == "203.0.113.1"
