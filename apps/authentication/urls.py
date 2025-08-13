from django.urls import path

from .health import health_check, liveness_check, readiness_check
from .oauth import github_oauth_callback, github_oauth_url
from .views import (
    ChangePasswordView,
    CustomTokenRefreshView,
    LoginView,
    LogoutView,
    ProfileView,
    RegisterView,
    UserSessionsView,
    verify_token,
)

urlpatterns = [
    # Authentication endpoints
    path("register/", RegisterView.as_view(), name="register"),
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    # Token management
    path("refresh-token/", CustomTokenRefreshView.as_view(), name="token_refresh"),
    path("verify-token/", verify_token, name="verify_token"),
    # User profile
    path("profile/", ProfileView.as_view(), name="profile"),
    path("change-password/", ChangePasswordView.as_view(), name="change_password"),
    # Session management
    path("sessions/", UserSessionsView.as_view(), name="user_sessions"),
    # OAuth endpoints
    path("github/url/", github_oauth_url, name="github_oauth_url"),
    path("github/callback/", github_oauth_callback, name="github_oauth_callback"),
    # Health check endpoints
    path("health/", health_check, name="health_check"),
    path("health/ready/", readiness_check, name="readiness_check"),
    path("health/live/", liveness_check, name="liveness_check"),
]
