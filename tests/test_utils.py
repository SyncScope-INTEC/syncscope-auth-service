import pytest
from unittest.mock import Mock, patch
from django.test import RequestFactory
from django.contrib.auth import get_user_model
from apps.authentication.utils import (
    create_user_session,
    get_tokens_for_user,
    hash_token,
    validate_session_token,
    get_client_ip,
    invalidate_user_sessions
)
from apps.authentication.models import UserSession

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
        
        assert 'access' in tokens
        assert 'refresh' in tokens
        assert isinstance(tokens['access'], str)
        assert isinstance(tokens['refresh'], str)
        assert len(tokens['access']) > 0
        assert len(tokens['refresh']) > 0
    
    def test_create_user_session(self, user):
        """Test user session creation."""
        request = Mock()
        request.META = {
            'HTTP_USER_AGENT': 'Test Browser',
            'REMOTE_ADDR': '127.0.0.1'
        }
        
        session, token = create_user_session(user, request)
        
        assert isinstance(session, UserSession)
        assert session.user == user
        assert session.is_active is True
        assert session.user_agent == 'Test Browser'
        assert session.ip_address == '127.0.0.1'
        assert isinstance(token, str)
        assert len(token) > 0
    
    def test_validate_session_token_valid(self, user):
        """Test session token validation with valid token."""
        request = Mock()
        request.META = {'HTTP_USER_AGENT': 'Test Browser', 'REMOTE_ADDR': '127.0.0.1'}
        
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
        request.META = {
            'HTTP_X_FORWARDED_FOR': '203.0.113.195, 70.41.3.18, 150.172.238.178',
            'REMOTE_ADDR': '127.0.0.1'
        }
        
        ip = get_client_ip(request)
        assert ip == '203.0.113.195'  # Should return first IP
    
    def test_get_client_ip_x_real_ip(self):
        """Test getting client IP from X-Real-IP header."""
        request = Mock()
        request.META = {
            'HTTP_X_REAL_IP': '203.0.113.195',
            'REMOTE_ADDR': '127.0.0.1'
        }
        
        ip = get_client_ip(request)
        assert ip == '203.0.113.195'
    
    def test_get_client_ip_remote_addr(self):
        """Test getting client IP from REMOTE_ADDR."""
        request = Mock()
        request.META = {'REMOTE_ADDR': '203.0.113.195'}
        
        ip = get_client_ip(request)
        assert ip == '203.0.113.195'
    
    def test_get_client_ip_fallback(self):
        """Test client IP fallback when no headers present."""
        request = Mock()
        request.META = {}
        
        ip = get_client_ip(request)
        assert ip == '127.0.0.1'  # Should fallback to localhost
    
    def test_invalidate_user_sessions(self, user):
        """Test invalidating all user sessions."""
        request = Mock()
        request.META = {'HTTP_USER_AGENT': 'Test Browser', 'REMOTE_ADDR': '127.0.0.1'}
        
        # Create multiple sessions
        session1, _ = create_user_session(user, request)
        session2, _ = create_user_session(user, request)
        
        assert UserSession.objects.filter(user=user, is_active=True).count() == 2
        
        invalidate_user_sessions(user)
        
        # All sessions should be deactivated
        assert UserSession.objects.filter(user=user, is_active=True).count() == 0
        assert UserSession.objects.filter(user=user, is_active=False).count() == 2