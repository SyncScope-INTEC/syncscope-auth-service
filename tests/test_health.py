import pytest
from django.urls import reverse
from rest_framework import status


@pytest.mark.django_db
class TestHealthEndpoints:
    
    def test_health_check_success(self, api_client):
        """Test health check endpoint returns success when services are healthy."""
        url = reverse('root_health_check')
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['status'] == 'healthy'
        assert 'timestamp' in response.data
        assert 'version' in response.data
        assert 'services' in response.data
        assert 'database' in response.data['services']
        assert 'cache' in response.data['services']
    
    def test_readiness_check(self, api_client):
        """Test readiness check endpoint."""
        url = reverse('readiness_check')
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['status'] == 'ready'
    
    def test_liveness_check(self, api_client):
        """Test liveness check endpoint."""
        url = reverse('liveness_check')
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['status'] == 'alive'
    
    def test_health_check_structure(self, api_client):
        """Test health check response structure."""
        url = reverse('root_health_check')
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        data = response.data
        
        # Check required fields
        required_fields = ['status', 'timestamp', 'version', 'services']
        for field in required_fields:
            assert field in data
        
        # Check services structure
        services = data['services']
        required_services = ['database', 'cache']
        for service in required_services:
            assert service in services
            assert services[service] in ['healthy', 'unhealthy']