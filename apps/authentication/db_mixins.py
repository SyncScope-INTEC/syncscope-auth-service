"""
Database mixins with retry logic for models and views
"""
from django.db import models
from config.database_retry import database_retry, RetryableQuerySet, atomic_with_retry


class RetryableModelMixin:
    """Mixin to add retry logic to model operations"""
    
    @database_retry()
    def save(self, *args, **kwargs):
        return super().save(*args, **kwargs)
    
    @database_retry()
    def delete(self, *args, **kwargs):
        return super().delete(*args, **kwargs)
    
    @database_retry()
    def refresh_from_db(self, *args, **kwargs):
        return super().refresh_from_db(*args, **kwargs)
    
    @classmethod
    @database_retry()
    def objects_get(cls, *args, **kwargs):
        return cls.objects.get(*args, **kwargs)
    
    @classmethod
    @database_retry()
    def objects_filter(cls, *args, **kwargs):
        return cls.objects.filter(*args, **kwargs)
    
    @classmethod
    @database_retry()
    def objects_create(cls, *args, **kwargs):
        return cls.objects.create(*args, **kwargs)
    
    @classmethod
    @database_retry()
    def objects_get_or_create(cls, *args, **kwargs):
        return cls.objects.get_or_create(*args, **kwargs)


class RetryableManager(models.Manager):
    """Custom manager with retry logic"""
    
    @database_retry()
    def get(self, *args, **kwargs):
        return super().get(*args, **kwargs)
    
    @database_retry()
    def filter(self, *args, **kwargs):
        return super().filter(*args, **kwargs)
    
    @database_retry()
    def create(self, *args, **kwargs):
        return super().create(*args, **kwargs)
    
    @database_retry()
    def get_or_create(self, *args, **kwargs):
        return super().get_or_create(*args, **kwargs)
    
    @database_retry()
    def update_or_create(self, *args, **kwargs):
        return super().update_or_create(*args, **kwargs)
    
    @database_retry()
    def bulk_create(self, *args, **kwargs):
        return super().bulk_create(*args, **kwargs)
    
    @database_retry()
    def exists(self):
        return super().exists()
    
    @database_retry()
    def count(self):
        return super().count()


class ServerlessViewMixin:
    """Mixin for views to handle serverless database connections"""
    
    def dispatch(self, request, *args, **kwargs):
        from config.database_retry import DatabaseHealthCheck, close_old_connections
        
        # Check database health before processing request
        if not DatabaseHealthCheck.is_healthy():
            close_old_connections()
            
            # Try one more time after closing connections
            if not DatabaseHealthCheck.is_healthy(use_cache=False):
                from rest_framework.response import Response
                from rest_framework import status
                return Response({
                    'error': 'Service temporarily unavailable',
                    'detail': 'Database connection issue'
                }, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        
        return super().dispatch(request, *args, **kwargs)
    
    def handle_exception(self, exc):
        from config.database_retry import is_retryable_error, DatabaseHealthCheck
        
        if is_retryable_error(exc):
            DatabaseHealthCheck.mark_unhealthy()
        
        return super().handle_exception(exc)