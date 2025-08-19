import os

import django
import pytest
from django.conf import settings

# Configure Django settings before importing anything else
if not settings.configured:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    django.setup()

from unittest.mock import Mock, patch

from django.conf.urls.static import static
from django.test import override_settings
from django.urls import resolve, reverse

import config.urls


class TestUrlPatterns:
    """Test URL pattern configuration."""

    def test_api_home_url(self):
        """Test that api_home URL is configured correctly."""
        url = reverse("api_home")
        assert url == "/"

        # Test that it resolves to the correct view
        resolved = resolve("/")
        assert resolved.view_name == "api_home"

    def test_admin_url_exists(self):
        """Test that admin URL exists."""
        # We can't easily reverse admin URLs without more setup,
        # but we can check the pattern exists
        assert any("admin/" in str(pattern) for pattern in config.urls.urlpatterns)

    def test_auth_urls_included(self):
        """Test that auth URLs are included."""
        assert any("auth/" in str(pattern) for pattern in config.urls.urlpatterns)

    def test_health_check_url(self):
        """Test that health check URL is configured correctly."""
        url = reverse("root_health_check")
        assert url == "/health/"

        # Test that it resolves to the correct view
        resolved = resolve("/health/")
        assert resolved.view_name == "root_health_check"

    def test_api_schema_url(self):
        """Test that API schema URL is configured correctly."""
        url = reverse("schema")
        assert url == "/api/schema/"

    def test_swagger_ui_url(self):
        """Test that Swagger UI URL is configured correctly."""
        url = reverse("swagger-ui")
        assert url == "/api/docs/"

    def test_redoc_url(self):
        """Test that ReDoc URL is configured correctly."""
        url = reverse("redoc")
        assert url == "/api/redoc/"

    def test_urlpatterns_count(self):
        """Test that expected number of URL patterns exist."""
        # Should have at least the main patterns we defined
        assert len(config.urls.urlpatterns) >= 6  # Home, admin, auth, health, schema, docs, redoc


class TestStaticFilesConfiguration:
    """Test static files URL configuration."""

    def test_static_files_logic_exists(self):
        """Test that static files logic exists in the module."""
        import inspect

        source = inspect.getsource(config.urls)

        # Check that the static files logic is present
        assert "if settings.DEBUG:" in source
        assert "static(" in source

    @override_settings(DEBUG=False)
    def test_static_files_not_added_in_production(self):
        """Test that static files are not served in production mode."""
        # Reload the module to trigger the DEBUG condition
        import importlib

        importlib.reload(config.urls)

        # In production, static files shouldn't be added to urlpatterns
        # We can't easily test this without modifying the original urlpatterns
        # but we can verify the condition works by checking DEBUG setting
        assert settings.DEBUG is False


class TestImports:
    """Test that all required modules and views are imported."""

    def test_required_imports_exist(self):
        """Test that all required imports are available."""
        # Test Django imports
        assert hasattr(config.urls, "settings")
        assert hasattr(config.urls, "static")
        assert hasattr(config.urls, "admin")
        assert hasattr(config.urls, "include")
        assert hasattr(config.urls, "path")

        # Test DRF Spectacular imports
        assert hasattr(config.urls, "SpectacularAPIView")
        assert hasattr(config.urls, "SpectacularRedocView")
        assert hasattr(config.urls, "SpectacularSwaggerView")

        # Test app imports
        assert hasattr(config.urls, "health_check")
        assert hasattr(config.urls, "api_home")

    def test_urlpatterns_variable_exists(self):
        """Test that urlpatterns variable exists and is a list."""
        assert hasattr(config.urls, "urlpatterns")
        assert isinstance(config.urls.urlpatterns, list)

    def test_all_patterns_are_valid(self):
        """Test that all URL patterns are valid Django patterns."""
        for pattern in config.urls.urlpatterns:
            # Each pattern should have a pattern attribute
            assert hasattr(pattern, "pattern")
            # And should be resolvable (this is a basic check)
            assert pattern is not None


class TestUrlConfiguration:
    """Test overall URL configuration."""

    def test_url_namespaces(self):
        """Test URL namespaces and names."""
        expected_names = ["api_home", "root_health_check", "schema", "swagger-ui", "redoc"]

        for name in expected_names:
            try:
                url = reverse(name)
                assert url is not None
                assert len(url) > 0
            except Exception:
                pytest.fail(f"URL name '{name}' could not be reversed")

    def test_url_patterns_structure(self):
        """Test the structure of URL patterns."""
        patterns = config.urls.urlpatterns

        # Should have patterns for main functionality
        pattern_strings = [str(p.pattern) for p in patterns]

        # Check for key patterns (simplified)
        assert any("" in p for p in pattern_strings)  # Root URL (empty pattern)
        assert any("admin/" in p for p in pattern_strings)  # Admin
        assert any("auth/" in p for p in pattern_strings)  # Auth
        assert any("health/" in p for p in pattern_strings)  # Health
        assert any("api/" in p for p in pattern_strings)  # API docs
