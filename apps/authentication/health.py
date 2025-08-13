from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from django.db import connection
from django.core.cache import cache
from django.conf import settings
from drf_spectacular.utils import extend_schema
import redis
import time


@extend_schema(
    tags=['Health'],
    summary='Health check endpoint',
    description='Check the health status of the service including database and cache connections.',
    responses={
        200: {
            'type': 'object',
            'properties': {
                'status': {'type': 'string', 'example': 'healthy'},
                'timestamp': {'type': 'string', 'example': '2024-01-01T12:00:00Z'},
                'version': {'type': 'string', 'example': '1.0.0'},
                'services': {
                    'type': 'object',
                    'properties': {
                        'database': {'type': 'string', 'example': 'healthy'},
                        'cache': {'type': 'string', 'example': 'healthy'}
                    }
                }
            }
        },
        503: {
            'type': 'object',
            'properties': {
                'status': {'type': 'string', 'example': 'unhealthy'},
                'errors': {'type': 'array', 'items': {'type': 'string'}}
            }
        }
    }
)
@api_view(['GET'])
@permission_classes([AllowAny])
def health_check(request):
    """
    Health check endpoint for monitoring and load balancers.
    """
    health_status = {
        'status': 'healthy',
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'version': getattr(settings, 'VERSION', '1.0.0'),
        'services': {}
    }
    
    errors = []
    
    # Check database connection
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        health_status['services']['database'] = 'healthy'
    except Exception as e:
        health_status['services']['database'] = 'unhealthy'
        errors.append(f'Database: {str(e)}')
    
    # Check cache/Redis connection
    try:
        cache.set('health_check', 'ok', 10)
        if cache.get('health_check') == 'ok':
            health_status['services']['cache'] = 'healthy'
        else:
            health_status['services']['cache'] = 'unhealthy'
            errors.append('Cache: Unable to read/write')
    except Exception as e:
        health_status['services']['cache'] = 'unhealthy'
        errors.append(f'Cache: {str(e)}')
    
    # Determine overall status
    if errors:
        health_status['status'] = 'unhealthy'
        health_status['errors'] = errors
        return Response(health_status, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    
    return Response(health_status, status=status.HTTP_200_OK)


@extend_schema(
    tags=['Health'],
    summary='Readiness check endpoint',
    description='Check if the service is ready to accept requests.',
    responses={
        200: {'type': 'object', 'properties': {'status': {'type': 'string', 'example': 'ready'}}},
        503: {'type': 'object', 'properties': {'status': {'type': 'string', 'example': 'not ready'}}}
    }
)
@api_view(['GET'])
@permission_classes([AllowAny])
def readiness_check(request):
    """
    Readiness check endpoint for Kubernetes/Railway deployments.
    """
    try:
        # Quick database check
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        
        return Response({'status': 'ready'}, status=status.HTTP_200_OK)
    except Exception:
        return Response({'status': 'not ready'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


@extend_schema(
    tags=['Health'],
    summary='Liveness check endpoint',
    description='Check if the service is alive (basic endpoint for load balancers).',
    responses={
        200: {'type': 'object', 'properties': {'status': {'type': 'string', 'example': 'alive'}}}
    }
)
@api_view(['GET'])
@permission_classes([AllowAny])
def liveness_check(request):
    """
    Simple liveness check - just returns 200 if the service is running.
    """
    return Response({'status': 'alive'}, status=status.HTTP_200_OK)