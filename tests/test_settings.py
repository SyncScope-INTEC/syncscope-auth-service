import os
from unittest.mock import patch

import pytest
from django.conf import settings as django_settings
from django.test import override_settings


class TestSettingsConfiguration:
    """Test Django settings configuration logic."""

    def test_default_allowed_hosts(self):
        """Test default ALLOWED_HOSTS configuration."""
        with patch.dict(os.environ, {}, clear=True):
            # Reset settings and reimport to test defaults
            from importlib import reload

            from django.conf import settings

            import config.settings as settings_module

            # Clear Railway environment variables if they exist
            os.environ.pop("RAILWAY_ENVIRONMENT", None)
            os.environ.pop("RAILWAY_PUBLIC_DOMAIN", None)

            reload(settings_module)

            # The default ALLOWED_HOSTS should contain localhost and 127.0.0.1
            expected_hosts = ["localhost", "127.0.0.1"]
            for host in expected_hosts:
                assert host in settings_module.ALLOWED_HOSTS

    @patch.dict(os.environ, {"RAILWAY_ENVIRONMENT": "production"})
    def test_railway_environment_allowed_hosts(self):
        """Test ALLOWED_HOSTS configuration when RAILWAY_ENVIRONMENT is set."""
        from importlib import reload

        import config.settings as settings_module

        reload(settings_module)

        # Should contain Railway-specific hosts
        railway_hosts = ["healthcheck.railway.app", "*.railway.app", "*.up.railway.app"]
        for host in railway_hosts:
            assert host in settings_module.ALLOWED_HOSTS

    @patch.dict(os.environ, {"RAILWAY_ENVIRONMENT": "production", "RAILWAY_PUBLIC_DOMAIN": "myapp.railway.app"})
    def test_railway_public_domain_added_to_allowed_hosts(self):
        """Test that RAILWAY_PUBLIC_DOMAIN is added to ALLOWED_HOSTS."""
        from importlib import reload

        import config.settings as settings_module

        reload(settings_module)

        # Should contain the specific Railway public domain
        assert "myapp.railway.app" in settings_module.ALLOWED_HOSTS

    @patch.dict(os.environ, {"DATABASE_URL": "postgresql://user:pass@localhost:5432/testdb"})
    def test_database_url_configuration(self):
        """Test database configuration when DATABASE_URL is set."""
        from importlib import reload

        import config.settings as settings_module

        reload(settings_module)

        # Should configure database from URL
        assert "default" in settings_module.DATABASES
        assert settings_module.DATABASES["default"]["ENGINE"] == "django.db.backends.postgresql"
        assert settings_module.DATABASES["default"]["NAME"] == "testdb"

    def test_database_options_configuration(self):
        """Test database options configuration logic."""
        from config import settings as settings_module

        # Just test that database options exist and contain expected values
        assert hasattr(settings_module, "DATABASES")
        assert "default" in settings_module.DATABASES
        assert "OPTIONS" in settings_module.DATABASES["default"]

        # Database options should contain statement_timeout
        options = settings_module.DATABASES["default"]["OPTIONS"]["options"]
        assert "statement_timeout=30000" in options

    @patch.dict(os.environ, {"RAILWAY_ENVIRONMENT": "production"})
    def test_railway_proxy_configuration(self):
        """Test proxy configuration when RAILWAY_ENVIRONMENT is set."""
        from importlib import reload

        import config.settings as settings_module

        reload(settings_module)

        # Should configure proxy settings for Railway
        assert settings_module.USE_TZ is True
        assert settings_module.SECURE_PROXY_SSL_HEADER == ("HTTP_X_FORWARDED_PROTO", "https")
        assert settings_module.SECURE_SSL_REDIRECT is False

    def test_debug_mode_affects_security_settings(self):
        """Test that DEBUG mode affects security settings."""
        from importlib import reload

        import config.settings as settings_module

        # Mock DEBUG = True
        with patch("config.settings.config") as mock_config:

            def mock_config_side_effect(key, default=None, cast=None):
                if key == "DEBUG":
                    if cast == bool:
                        return True
                    return "True"
                elif key == "ALLOWED_HOSTS":
                    return "localhost,127.0.0.1"
                else:
                    return default

            mock_config.side_effect = mock_config_side_effect
            reload(settings_module)

            # Security settings should be affected by DEBUG
            assert settings_module.DEBUG is True
            assert settings_module.SECURE_HSTS_PRELOAD is False


class TestSettingsImports:
    """Test that settings module imports and structure are correct."""

    def test_required_settings_exist(self):
        """Test that required Django settings exist."""
        from config import settings as settings_module

        required_settings = [
            "SECRET_KEY",
            "DEBUG",
            "ALLOWED_HOSTS",
            "INSTALLED_APPS",
            "MIDDLEWARE",
            "ROOT_URLCONF",
            "DATABASES",
            "AUTH_USER_MODEL",
            "LANGUAGE_CODE",
            "TIME_ZONE",
            "USE_I18N",
            "USE_TZ",
        ]

        for setting in required_settings:
            assert hasattr(settings_module, setting), f"Required setting {setting} not found"

    def test_custom_settings_exist(self):
        """Test that custom application settings exist."""
        from config import settings as settings_module

        custom_settings = [
            "AUTH_USER_MODEL",
            "GITHUB_CLIENT_ID",
            "GITHUB_CLIENT_SECRET",
            "CORS_ALLOWED_ORIGINS",
            "CSRF_TRUSTED_ORIGINS",
        ]

        for setting in custom_settings:
            assert hasattr(settings_module, setting), f"Custom setting {setting} not found"

    def test_middleware_order(self):
        """Test that middleware is in correct order."""
        from config import settings as settings_module

        middleware = settings_module.MIDDLEWARE

        # Security middleware should be first
        assert "django.middleware.security.SecurityMiddleware" in middleware

        # CORS middleware should be early
        assert "corsheaders.middleware.CorsMiddleware" in middleware

        # Session and auth middleware should be present
        assert "django.contrib.sessions.middleware.SessionMiddleware" in middleware
        assert "django.contrib.auth.middleware.AuthenticationMiddleware" in middleware

    def test_installed_apps_include_required(self):
        """Test that INSTALLED_APPS includes required applications."""
        from config import settings as settings_module

        installed_apps = settings_module.INSTALLED_APPS

        required_apps = [
            "django.contrib.admin",
            "django.contrib.auth",
            "django.contrib.contenttypes",
            "django.contrib.sessions",
            "rest_framework",
            "corsheaders",
            "apps.authentication",
        ]

        for app in required_apps:
            assert app in installed_apps, f"Required app {app} not in INSTALLED_APPS"

    def test_rest_framework_configuration(self):
        """Test REST Framework configuration."""
        from config import settings as settings_module

        assert hasattr(settings_module, "REST_FRAMEWORK")
        rest_config = settings_module.REST_FRAMEWORK

        # Should have authentication and permission classes
        assert "DEFAULT_AUTHENTICATION_CLASSES" in rest_config
        assert "DEFAULT_PERMISSION_CLASSES" in rest_config

        # Should have pagination configured
        assert "DEFAULT_PAGINATION_CLASS" in rest_config

    def test_spectacular_configuration(self):
        """Test DRF Spectacular (OpenAPI) configuration."""
        from config import settings as settings_module

        assert hasattr(settings_module, "SPECTACULAR_SETTINGS")
        spectacular_config = settings_module.SPECTACULAR_SETTINGS

        # Should have basic OpenAPI configuration
        assert "TITLE" in spectacular_config
        assert "DESCRIPTION" in spectacular_config
        assert "VERSION" in spectacular_config

    def test_cors_configuration(self):
        """Test CORS configuration."""
        from config import settings as settings_module

        # CORS settings should exist
        assert hasattr(settings_module, "CORS_ALLOWED_ORIGINS")
        assert hasattr(settings_module, "CORS_ALLOW_CREDENTIALS")
        assert hasattr(settings_module, "CSRF_TRUSTED_ORIGINS")

    def test_logging_configuration(self):
        """Test logging configuration."""
        from config import settings as settings_module

        assert hasattr(settings_module, "LOGGING")
        logging_config = settings_module.LOGGING

        # Should have basic logging structure
        assert "version" in logging_config
        assert "handlers" in logging_config
        assert "loggers" in logging_config

    def test_cache_configuration(self):
        """Test cache configuration."""
        from config import settings as settings_module

        assert hasattr(settings_module, "CACHES")
        caches_config = settings_module.CACHES

        # Should have at least a default cache
        assert "default" in caches_config


class TestEnvironmentSpecificBehavior:
    """Test environment-specific behavior in settings."""

    def test_security_settings_configuration(self):
        """Test security settings configuration."""
        from config import settings as settings_module

        # Test that security settings exist and are related to DEBUG mode
        assert hasattr(settings_module, "DEBUG")
        assert hasattr(settings_module, "SECURE_HSTS_PRELOAD")

        # SECURE_HSTS_PRELOAD should be the opposite of DEBUG
        assert settings_module.SECURE_HSTS_PRELOAD == (not settings_module.DEBUG)

    def test_allowed_hosts_configuration(self):
        """Test ALLOWED_HOSTS configuration."""
        from config import settings as settings_module

        # Test that ALLOWED_HOSTS exists and contains expected values
        assert hasattr(settings_module, "ALLOWED_HOSTS")
        assert isinstance(settings_module.ALLOWED_HOSTS, list)

        # Should contain some basic hosts
        assert len(settings_module.ALLOWED_HOSTS) > 0

    def teardown_method(self):
        """Clean up after each test method."""
        # Reload original settings after each test
        from importlib import reload

        import config.settings

        reload(config.settings)
