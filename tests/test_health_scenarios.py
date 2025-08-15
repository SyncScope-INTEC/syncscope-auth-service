from unittest.mock import Mock, patch

import pytest
from django.db import OperationalError
from django.urls import reverse
from rest_framework import status


@pytest.mark.django_db
class TestHealthCheckErrorScenarios:

    @patch("django.db.connection.cursor")
    def test_health_check_database_failure(self, mock_cursor, api_client):
        """Test health check when database is unavailable."""
        mock_cursor.side_effect = OperationalError("Database connection failed")

        url = reverse("root_health_check")
        response = api_client.get(url)

        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert response.data["status"] == "unhealthy"
        assert "errors" in response.data
        assert any("Database" in error for error in response.data["errors"])
        assert response.data["services"]["database"] == "unhealthy"

    @patch("django.core.cache.cache.set")
    @patch("django.core.cache.cache.get")
    def test_health_check_cache_failure(self, mock_cache_get, mock_cache_set, api_client):
        """Test health check when cache is unavailable."""
        mock_cache_set.side_effect = Exception("Redis connection failed")
        mock_cache_get.return_value = None

        url = reverse("root_health_check")
        response = api_client.get(url)

        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert response.data["status"] == "unhealthy"
        assert "errors" in response.data
        assert any("Cache" in error for error in response.data["errors"])
        assert response.data["services"]["cache"] == "unhealthy"

    @patch("django.core.cache.cache.set")
    @patch("django.core.cache.cache.get")
    def test_health_check_cache_read_write_failure(self, mock_cache_get, mock_cache_set, api_client):
        """Test health check when cache read/write fails."""
        mock_cache_set.return_value = True
        mock_cache_get.return_value = None  # Failed to read what we wrote

        url = reverse("root_health_check")
        response = api_client.get(url)

        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert response.data["status"] == "unhealthy"
        assert "Cache: Unable to read/write" in response.data["errors"]
        assert response.data["services"]["cache"] == "unhealthy"

    @patch("django.db.connection.cursor")
    @patch("django.core.cache.cache.set")
    @patch("django.core.cache.cache.get")
    def test_health_check_both_services_fail(self, mock_cache_get, mock_cache_set, mock_cursor, api_client):
        """Test health check when both database and cache fail."""
        mock_cursor.side_effect = OperationalError("Database connection failed")
        mock_cache_set.side_effect = Exception("Redis connection failed")

        url = reverse("root_health_check")
        response = api_client.get(url)

        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert response.data["status"] == "unhealthy"
        assert len(response.data["errors"]) == 2
        assert response.data["services"]["database"] == "unhealthy"
        assert response.data["services"]["cache"] == "unhealthy"

    @patch("django.db.connection.cursor")
    def test_readiness_check_database_failure(self, mock_cursor, api_client):
        """Test readiness check when database is unavailable."""
        mock_cursor.side_effect = OperationalError("Database connection failed")

        url = reverse("readiness_check")
        response = api_client.get(url)

        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert response.data["status"] == "not ready"

    def test_liveness_check_always_succeeds(self, api_client):
        """Test that liveness check always returns 200."""
        url = reverse("liveness_check")
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == "alive"

    def test_health_check_response_structure_complete(self, api_client):
        """Test complete health check response structure."""
        url = reverse("root_health_check")
        response = api_client.get(url)

        # Should succeed in test environment
        assert response.status_code == status.HTTP_200_OK
        data = response.data

        # Verify all required fields are present
        assert "status" in data
        assert "timestamp" in data
        assert "version" in data
        assert "services" in data

        # Verify timestamp format
        import re

        timestamp_pattern = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z"
        assert re.match(timestamp_pattern, data["timestamp"])

        # Verify services structure
        services = data["services"]
        assert "database" in services
        assert "cache" in services
        assert services["database"] in ["healthy", "unhealthy"]
        assert services["cache"] in ["healthy", "unhealthy"]


@pytest.mark.django_db
class TestHealthCheckSettings:

    @patch("django.conf.settings.VERSION", "2.0.0")
    def test_health_check_custom_version(self, api_client):
        """Test health check with custom version setting."""
        url = reverse("root_health_check")
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["version"] == "2.0.0"

    def test_health_check_default_version(self, api_client):
        """Test health check with default version when not set."""
        url = reverse("root_health_check")
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        # Should default to "1.0.0" when VERSION setting is not available
        assert "version" in response.data
