from unittest.mock import Mock, patch

import pytest
from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.test import RequestFactory

from apps.authentication.middleware import RateLimitMiddleware, RequestLoggingMiddleware, SecurityHeadersMiddleware

User = get_user_model()


class TestSecurityHeadersMiddleware:

    def test_adds_security_headers(self):
        """Test that security headers are added to response."""
        request = RequestFactory().get("/auth/")

        def get_response(request):
            return HttpResponse("OK")

        middleware = SecurityHeadersMiddleware(get_response)
        response = middleware(request)

        # Check security headers
        assert response["X-Content-Type-Options"] == "nosniff"
        assert response["X-Frame-Options"] == "DENY"
        assert response["X-XSS-Protection"] == "1; mode=block"
        assert "Referrer-Policy" in response
        assert "Content-Security-Policy" in response


class TestRequestLoggingMiddleware:

    @patch("apps.authentication.middleware.logger")
    def test_logs_request_info(self, mock_logger):
        """Test that request information is logged."""
        request = RequestFactory().get("/test-path/")
        request.META["REMOTE_ADDR"] = "127.0.0.1"
        request.META["HTTP_USER_AGENT"] = "Test Agent"

        def get_response(request):
            return HttpResponse("OK")

        middleware = RequestLoggingMiddleware(get_response)
        response = middleware(request)

        # Check that logger was called (should be called twice - request and response)
        assert mock_logger.info.call_count == 2
        
        # Check first call (request log)
        first_call_args = mock_logger.info.call_args_list[0][0][0]
        assert "GET" in first_call_args
        assert "/test-path/" in first_call_args
        assert "127.0.0.1" in first_call_args

    @patch("apps.authentication.middleware.logger")
    def test_logs_response_time(self, mock_logger):
        """Test that response time is logged."""
        request = RequestFactory().get("/test-path/")
        request.META["REMOTE_ADDR"] = "127.0.0.1"

        def get_response(request):
            return HttpResponse("OK")

        middleware = RequestLoggingMiddleware(get_response)
        middleware(request)

        # Should have logged both request and response
        assert mock_logger.info.call_count >= 1


class TestRateLimitMiddleware:

    def test_allows_normal_requests(self):
        """Test that normal requests are allowed."""
        request = RequestFactory().get("/")
        request.META["REMOTE_ADDR"] = "127.0.0.1"

        def get_response(request):
            return HttpResponse("OK")

        middleware = RateLimitMiddleware(get_response)
        response = middleware(request)

        assert response.status_code == 200
        assert response.content == b"OK"

    @patch("apps.authentication.middleware.cache")
    def test_rate_limit_headers_added(self, mock_cache):
        """Test that rate limit headers are added to response."""
        mock_cache.get.return_value = 2  # 2 requests made (under limit of 5)
        mock_cache.set.return_value = True

        request = RequestFactory().get("/auth/login")
        request.META["REMOTE_ADDR"] = "127.0.0.1"

        def get_response(request):
            return HttpResponse("OK")

        middleware = RateLimitMiddleware(get_response)
        response = middleware(request)

        # Should have rate limit headers
        assert "X-RateLimit-Limit" in response
        assert "X-RateLimit-Remaining" in response
        assert "X-RateLimit-Reset" in response
