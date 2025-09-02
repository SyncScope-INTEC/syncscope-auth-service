"""
URL configuration for syncscope-auth-service project.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView

from apps.authentication.health import health_check
from apps.authentication.views import api_home

urlpatterns = [
    # Home page
    path("", api_home, name="api_home"),
    path("admin/", admin.site.urls),
    path("auth/", include("apps.authentication.urls")),
    # Root health check
    path("health/", health_check, name="root_health_check"),
    # API Documentation
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
]

# Serve static files in development
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
