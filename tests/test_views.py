import os

import django
import pytest
from django.conf import settings

# Configure Django settings before importing anything else
if not settings.configured:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    django.setup()

from unittest.mock import Mock, patch

from django.http import HttpResponse
from django.test import RequestFactory
from rest_framework import status
from rest_framework.response import Response

from apps.authentication.views import api_home


class TestApiHomeView:
    """Test cases for the api_home view."""

    def test_api_home_returns_html_response(self):
        """Test that api_home returns HTML response when template exists."""
        request = RequestFactory().get("/")

        response = api_home(request)

        # Should return HTML response
        assert isinstance(response, HttpResponse)
        assert response.status_code == 200
        assert "text/html" in response.get("Content-Type", "")

    def test_api_home_context_data(self):
        """Test that api_home includes correct context data."""
        request = RequestFactory().get("/")

        with patch("apps.authentication.views.loader.get_template") as mock_template:
            mock_template_instance = Mock()
            mock_template.return_value = mock_template_instance
            mock_template_instance.render.return_value = "test content"

            response = api_home(request)

            # Check that template was called with correct context
            mock_template_instance.render.assert_called_once()
            context = mock_template_instance.render.call_args[0][0]

            # Verify main routes are present
            assert "main_routes" in context
            assert len(context["main_routes"]) == 5

            # Verify service info
            assert "service_info" in context
            assert context["service_info"]["endpoints"] == 15
            assert "JWT" in context["service_info"]["auth_methods"]
            assert "GitHub OAuth" in context["service_info"]["auth_methods"]

            # Verify API metadata
            assert context["api_title"] == "SyncScope Auth Service"
            assert context["api_version"] == "1.0.0"
            assert "Authentication and user management" in context["api_description"]

    def test_api_home_route_urls(self):
        """Test that api_home generates correct route URLs."""
        request = RequestFactory().get("/", HTTP_HOST="testserver")

        with patch("apps.authentication.views.loader.get_template") as mock_template:
            mock_template_instance = Mock()
            mock_template.return_value = mock_template_instance
            mock_template_instance.render.return_value = "test content"

            response = api_home(request)

            context = mock_template_instance.render.call_args[0][0]
            routes = context["main_routes"]

            # Check that URLs are properly formed
            api_docs_route = next(r for r in routes if r["title"] == "API Documentation")
            assert api_docs_route["url"] == "http://testserver/api/docs/"

            admin_route = next(r for r in routes if r["title"] == "Admin Interface")
            assert admin_route["url"] == "http://testserver/admin/"

            health_route = next(r for r in routes if r["title"] == "Health Check")
            assert health_route["url"] == "http://testserver/health/"

    def test_api_home_route_categories(self):
        """Test that api_home routes have correct categories and metadata."""
        request = RequestFactory().get("/")

        with patch("apps.authentication.views.loader.get_template") as mock_template:
            mock_template_instance = Mock()
            mock_template.return_value = mock_template_instance
            mock_template_instance.render.return_value = "test content"

            response = api_home(request)

            context = mock_template_instance.render.call_args[0][0]
            routes = context["main_routes"]

            # Check route categories
            doc_routes = [r for r in routes if r["category"] == "documentation"]
            assert len(doc_routes) == 3  # API docs, ReDoc, OpenAPI schema

            admin_routes = [r for r in routes if r["category"] == "admin"]
            assert len(admin_routes) == 1  # Admin interface

            monitoring_routes = [r for r in routes if r["category"] == "monitoring"]
            assert len(monitoring_routes) == 1  # Health check

            # Check that all routes have required fields
            for route in routes:
                assert "title" in route
                assert "description" in route
                assert "url" in route
                assert "icon" in route
                assert "category" in route

    @patch("apps.authentication.views.loader.get_template")
    def test_api_home_template_fallback_to_json(self, mock_template):
        """Test that api_home falls back to JSON when template doesn't exist."""
        mock_template.side_effect = Exception("Template not found")

        request = RequestFactory().get("/")

        response = api_home(request)

        # Should return DRF Response (JSON)
        assert isinstance(response, Response)
        assert response.status_code == status.HTTP_200_OK

        # Should contain expected data
        assert "main_routes" in response.data
        assert "service_info" in response.data
        assert "api_title" in response.data

    def test_api_home_https_urls(self):
        """Test that api_home generates HTTPS URLs for secure requests."""
        request = RequestFactory().get("/", HTTP_HOST="testserver", secure=True)

        with patch("apps.authentication.views.loader.get_template") as mock_template:
            mock_template_instance = Mock()
            mock_template.return_value = mock_template_instance
            mock_template_instance.render.return_value = "test content"

            response = api_home(request)

            context = mock_template_instance.render.call_args[0][0]

            # Check that base URL is HTTPS
            assert context["base_url"] == "https://testserver/"

            # Check that route URLs are HTTPS
            routes = context["main_routes"]
            for route in routes:
                assert route["url"].startswith("https://")

    def test_api_home_service_features(self):
        """Test that api_home includes correct service features."""
        request = RequestFactory().get("/")

        with patch("apps.authentication.views.loader.get_template") as mock_template:
            mock_template_instance = Mock()
            mock_template.return_value = mock_template_instance
            mock_template_instance.render.return_value = "test content"

            response = api_home(request)

            context = mock_template_instance.render.call_args[0][0]
            service_info = context["service_info"]

            # Check service features
            expected_features = ["User Management", "Session Tracking", "Health Monitoring"]
            assert service_info["features"] == expected_features

            # Check auth methods
            expected_auth_methods = ["JWT", "GitHub OAuth"]
            assert service_info["auth_methods"] == expected_auth_methods

            # Check status
            assert service_info["status"] == "Operational"
