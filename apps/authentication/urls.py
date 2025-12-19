from django.urls import path

from .health import health_check, liveness_check, readiness_check
from .oauth import github_oauth_callback, github_oauth_initiate, github_oauth_status, github_oauth_url
from .views import (
    ChangePasswordView,
    CustomTokenRefreshView,
    ForgotPasswordView,
    LoginView,
    LogoutView,
    ProfileView,
    RegisterView,
    ResetPasswordView,
    SupervisedUserDetailView,
    SupervisedUserListCreateView,
    UserByIdView,
    UserImageView,
    UserSessionsView,
    VerifyResetCodeView,
    api_home,
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
    path("users/<uuid:user_id>/", UserByIdView.as_view(), name="user_by_id"),
    path("change-password/", ChangePasswordView.as_view(), name="change_password"),
    # Password reset
    path("forgot-password/", ForgotPasswordView.as_view(), name="forgot_password"),
    path("verify-reset-code/", VerifyResetCodeView.as_view(), name="verify_reset_code"),
    path("reset-password/", ResetPasswordView.as_view(), name="reset_password"),
    # User images
    path("users/<uuid:user_id>/image/", UserImageView.as_view(), name="user_image"),
    # Session management
    path("sessions/", UserSessionsView.as_view(), name="user_sessions"),
    # Supervision management
    path("supervised-users/", SupervisedUserListCreateView.as_view(), name="supervised_users"),
    path("supervised-users/<uuid:pk>/", SupervisedUserDetailView.as_view(), name="supervised_user_detail"),
    # OAuth endpoints
    path("github/url/", github_oauth_url, name="github_oauth_url"),
    path("github/callback/", github_oauth_callback, name="github_oauth_callback"),
    # Desktop agent OAuth endpoints
    path("github/initiate/", github_oauth_initiate, name="github_oauth_initiate"),
    path("github/status/<str:state_id>/", github_oauth_status, name="github_oauth_status"),
    # Health check endpoints
    path("health/", health_check, name="health_check"),
    path("health/ready/", readiness_check, name="readiness_check"),
    path("health/live/", liveness_check, name="liveness_check"),
]
