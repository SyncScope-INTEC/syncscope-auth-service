from unittest.mock import Mock, patch

import pytest
from django.contrib.auth import get_user_model
from django.http import HttpResponse, JsonResponse
from django.test import RequestFactory, override_settings

from apps.authentication.middleware import (
    CorsMiddleware,
    RateLimitMiddleware,
    RequestLoggingMiddleware,
    SecurityHeadersMiddleware,
)

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

    def test_adds_hsts_header_for_https(self):
        """Test that HSTS header is added for HTTPS requests."""
        request = RequestFactory().get("/auth/", secure=True)

        def get_response(request):
            return HttpResponse("OK")

        middleware = SecurityHeadersMiddleware(get_response)
        response = middleware(request)

        # Check HSTS header is added for secure requests
        assert response["Strict-Transport-Security"] == "max-age=31536000; includeSubDomains"

    def test_no_hsts_header_for_http(self):
        """Test that HSTS header is not added for HTTP requests."""
        request = RequestFactory().get("/auth/")

        def get_response(request):
            return HttpResponse("OK")

        middleware = SecurityHeadersMiddleware(get_response)
        response = middleware(request)

        # Check HSTS header is not added for non-secure requests
        assert "Strict-Transport-Security" not in response

    def test_csp_header_for_auth_paths(self):
        """Test that CSP header is added for auth endpoints."""
        request = RequestFactory().get("/auth/login")

        def get_response(request):
            return HttpResponse("OK")

        middleware = SecurityHeadersMiddleware(get_response)
        response = middleware(request)

        # Check CSP header is added for auth paths
        assert response["Content-Security-Policy"] == "default-src 'none'; script-src 'none'; object-src 'none'"

    def test_no_csp_header_for_non_auth_paths(self):
        """Test that CSP header is not added for non-auth endpoints."""
        request = RequestFactory().get("/api/docs/")

        def get_response(request):
            return HttpResponse("OK")

        middleware = SecurityHeadersMiddleware(get_response)
        response = middleware(request)

        # Check CSP header is not added for non-auth paths
        assert "Content-Security-Policy" not in response


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

    @patch("apps.authentication.middleware.logger")
    def test_logs_request_with_user_agent(self, mock_logger):
        """Test that request with user agent is logged."""
        request = RequestFactory().get("/test-path/")
        request.META["REMOTE_ADDR"] = "192.168.1.1"
        request.META["HTTP_USER_AGENT"] = "Mozilla/5.0 Test Browser"

        def get_response(request):
            return HttpResponse("OK")

        middleware = RequestLoggingMiddleware(get_response)
        middleware(request)

        # Check that request was logged with IP
        first_call_args = mock_logger.info.call_args_list[0][0][0]
        assert "192.168.1.1" in first_call_args
        assert "GET" in first_call_args
        assert "/test-path/" in first_call_args

    @patch("apps.authentication.middleware.logger")
    def test_logs_response_status_and_duration(self, mock_logger):
        """Test that response status and duration are logged."""
        request = RequestFactory().get("/test-path/")
        request.META["REMOTE_ADDR"] = "127.0.0.1"

        def get_response(request):
            return HttpResponse("OK", status=201)

        middleware = RequestLoggingMiddleware(get_response)
        middleware(request)

        # Check that response was logged with status code and duration
        second_call_args = mock_logger.info.call_args_list[1][0][0]
        assert "201" in second_call_args
        assert "Response:" in second_call_args
        assert "s" in second_call_args  # Duration should be in seconds

    def test_get_client_ip_x_forwarded_for(self):
        """Test client IP extraction from X-Forwarded-For header."""
        request = RequestFactory().get("/")
        request.META["HTTP_X_FORWARDED_FOR"] = "203.0.113.1, 198.51.100.1"
        request.META["REMOTE_ADDR"] = "127.0.0.1"

        middleware = RequestLoggingMiddleware(None)
        ip = middleware.get_client_ip(request)

        # Should return first IP from X-Forwarded-For
        assert ip == "203.0.113.1"

    def test_get_client_ip_fallback(self):
        """Test client IP fallback to REMOTE_ADDR."""
        request = RequestFactory().get("/")
        request.META["REMOTE_ADDR"] = "10.0.0.50"

        middleware = RequestLoggingMiddleware(None)
        ip = middleware.get_client_ip(request)

        # Should return REMOTE_ADDR when no X-Forwarded-For
        assert ip == "10.0.0.50"


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

    @override_settings(RATELIMIT_ENABLE=False)
    def test_disabled_rate_limiting(self):
        """Test that rate limiting can be disabled."""
        request = RequestFactory().get("/auth/login")
        request.META["REMOTE_ADDR"] = "127.0.0.1"

        def get_response(request):
            return HttpResponse("OK")

        middleware = RateLimitMiddleware(get_response)
        response = middleware.process_request(request)

        # Should return None when disabled
        assert response is None

    def test_skips_admin_paths(self):
        """Test that admin paths are skipped from rate limiting."""
        request = RequestFactory().get("/admin/users/")
        request.META["REMOTE_ADDR"] = "127.0.0.1"

        def get_response(request):
            return HttpResponse("OK")

        middleware = RateLimitMiddleware(get_response)
        response = middleware.process_request(request)

        # Should return None for admin paths
        assert response is None

    def test_skips_static_paths(self):
        """Test that static paths are skipped from rate limiting."""
        request = RequestFactory().get("/static/css/style.css")
        request.META["REMOTE_ADDR"] = "127.0.0.1"

        def get_response(request):
            return HttpResponse("OK")

        middleware = RateLimitMiddleware(get_response)
        response = middleware.process_request(request)

        # Should return None for static paths
        assert response is None

    def test_skips_non_auth_paths(self):
        """Test that non-auth paths are skipped from rate limiting."""
        request = RequestFactory().get("/api/docs/")
        request.META["REMOTE_ADDR"] = "127.0.0.1"

        def get_response(request):
            return HttpResponse("OK")

        middleware = RateLimitMiddleware(get_response)
        response = middleware.process_request(request)

        # Should return None for non-auth paths
        assert response is None

    @patch("apps.authentication.middleware.cache")
    def test_rate_limit_exceeded(self, mock_cache):
        """Test that rate limit exceeded returns 429."""
        mock_cache.get.return_value = 5  # At limit

        request = RequestFactory().get("/auth/login")
        request.META["REMOTE_ADDR"] = "127.0.0.1"

        def get_response(request):
            return HttpResponse("OK")

        middleware = RateLimitMiddleware(get_response)
        response = middleware.process_request(request)

        # Should return 429 response
        assert isinstance(response, JsonResponse)
        assert response.status_code == 429
        assert "Rate limit exceeded" in response.content.decode()

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

    @patch("apps.authentication.middleware.cache")
    def test_different_limits_for_login_register(self, mock_cache):
        """Test different rate limits for login/register vs other auth endpoints."""
        mock_cache.get.return_value = 0
        mock_cache.set.return_value = True

        def get_response(request):
            return HttpResponse("OK")

        # Test login endpoint (5 requests limit)
        request_login = RequestFactory().get("/auth/login")
        request_login.META["REMOTE_ADDR"] = "127.0.0.1"

        middleware = RateLimitMiddleware(get_response)
        middleware.process_request(request_login)

        # Check rate limit info
        assert request_login._rate_limit_info["limit"] == 5

        # Test other auth endpoint (30 requests limit)
        request_profile = RequestFactory().get("/auth/profile")
        request_profile.META["REMOTE_ADDR"] = "127.0.0.1"

        middleware.process_request(request_profile)

        # Check rate limit info
        assert request_profile._rate_limit_info["limit"] == 30

    def test_get_client_ip_x_forwarded_for(self):
        """Test client IP extraction from X-Forwarded-For header."""
        request = RequestFactory().get("/")
        request.META["HTTP_X_FORWARDED_FOR"] = "192.168.1.1, 10.0.0.1"
        request.META["REMOTE_ADDR"] = "127.0.0.1"

        def get_response(request):
            return HttpResponse("OK")

        middleware = RateLimitMiddleware(get_response)
        ip = middleware.get_client_ip(request)

        # Should return first IP from X-Forwarded-For
        assert ip == "192.168.1.1"

    def test_get_client_ip_fallback(self):
        """Test client IP fallback to REMOTE_ADDR."""
        request = RequestFactory().get("/")
        request.META["REMOTE_ADDR"] = "192.168.1.100"

        def get_response(request):
            return HttpResponse("OK")

        middleware = RateLimitMiddleware(get_response)
        ip = middleware.get_client_ip(request)

        # Should return REMOTE_ADDR when no X-Forwarded-For
        assert ip == "192.168.1.100"

    def test_get_client_ip_default(self):
        """Test client IP default when no headers present."""
        request = RequestFactory().get("/")
        # Don't set any IP headers

        def get_response(request):
            return HttpResponse("OK")

        middleware = RateLimitMiddleware(get_response)
        ip = middleware.get_client_ip(request)

        # Should return default IP
        assert ip == "127.0.0.1"


class TestCorsMiddleware:

    @override_settings(CORS_ALLOWED_ORIGINS=["https://example.com", "https://app.syncscope.com"])
    def test_adds_cors_headers_for_allowed_origin(self):
        """Test that CORS headers are added for allowed origins."""
        request = RequestFactory().get("/auth/login")
        request.META["HTTP_ORIGIN"] = "https://example.com"

        def get_response(request):
            return HttpResponse("OK")

        middleware = CorsMiddleware(get_response)
        response = middleware(request)

        # Check CORS headers are added
        assert response["Access-Control-Allow-Origin"] == "https://example.com"
        assert response["Access-Control-Allow-Credentials"] == "true"
        assert response["Access-Control-Allow-Methods"] == "GET, POST, PUT, DELETE, OPTIONS"
        assert response["Access-Control-Allow-Headers"] == "Authorization, Content-Type, X-Requested-With"

    @override_settings(CORS_ALLOWED_ORIGINS=["https://example.com"])
    def test_no_cors_headers_for_disallowed_origin(self):
        """Test that CORS headers are not added for disallowed origins."""
        request = RequestFactory().get("/auth/login")
        request.META["HTTP_ORIGIN"] = "https://malicious.com"

        def get_response(request):
            return HttpResponse("OK")

        middleware = CorsMiddleware(get_response)
        response = middleware(request)

        # Check CORS headers are not added
        assert "Access-Control-Allow-Origin" not in response
        assert "Access-Control-Allow-Credentials" not in response
        assert "Access-Control-Allow-Methods" not in response
        assert "Access-Control-Allow-Headers" not in response

    def test_no_cors_headers_for_non_auth_paths(self):
        """Test that CORS headers are not added for non-auth paths."""
        request = RequestFactory().get("/api/docs/")
        request.META["HTTP_ORIGIN"] = "https://example.com"

        def get_response(request):
            return HttpResponse("OK")

        middleware = CorsMiddleware(get_response)
        response = middleware(request)

        # Check CORS headers are not added for non-auth paths
        assert "Access-Control-Allow-Origin" not in response

    def test_no_cors_headers_without_origin(self):
        """Test that CORS headers are not added when no origin header is present."""
        request = RequestFactory().get("/auth/login")
        # No HTTP_ORIGIN header set

        def get_response(request):
            return HttpResponse("OK")

        middleware = CorsMiddleware(get_response)
        response = middleware(request)

        # Check CORS headers are not added
        assert "Access-Control-Allow-Origin" not in response

    @override_settings(CORS_ALLOWED_ORIGINS=[])
    def test_no_cors_headers_with_empty_allowed_origins(self):
        """Test that CORS headers are not added when no origins are configured."""
        request = RequestFactory().get("/auth/login")
        request.META["HTTP_ORIGIN"] = "https://example.com"

        def get_response(request):
            return HttpResponse("OK")

        middleware = CorsMiddleware(get_response)
        response = middleware(request)

        # Check CORS headers are not added
        assert "Access-Control-Allow-Origin" not in response
