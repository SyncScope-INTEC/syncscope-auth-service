import requests
from django.conf import settings
from django.contrib.auth import authenticate
from django.db import transaction
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import Company, User
from .serializers import UserProfileSerializer
from .utils import create_user_session, extract_domain_from_email, get_tokens_for_user


def exchange_code_for_token(code):
    """Exchange authorization code for access token with GitHub"""
    token_url = "https://github.com/login/oauth/access_token"

    data = {
        "client_id": settings.GITHUB_CLIENT_ID,
        "client_secret": settings.GITHUB_CLIENT_SECRET,
        "code": code,
    }

    headers = {"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"}

    response = requests.post(token_url, data=data, headers=headers)
    response.raise_for_status()

    return response.json().get("access_token")


def get_github_user_data(access_token):
    """Get user data from GitHub API"""
    user_url = "https://api.github.com/user"
    emails_url = "https://api.github.com/user/emails"

    headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github.v3+json"}

    user_response = requests.get(user_url, headers=headers)
    user_response.raise_for_status()
    user_data = user_response.json()

    try:
        emails_response = requests.get(emails_url, headers=headers)
        emails_response.raise_for_status()
        emails_data = emails_response.json()

        primary_email = next((email["email"] for email in emails_data if email["primary"]), None)
        if not primary_email:
            primary_email = user_data.get("email") or (emails_data[0]["email"] if emails_data else None)
    except Exception:
        primary_email = user_data.get("email")

    return {
        "id": user_data["id"],
        "login": user_data["login"],
        "email": primary_email,
        "name": user_data.get("name", ""),
        # "avatar_url": user_data.get("avatar_url"),  # Deprecated field
        "company": user_data.get("company"),
    }


def create_or_update_user_from_github(github_data):
    """Create or update user from GitHub data"""
    # DISABLED: OAuth functionality uses deprecated fields (github_id, avatar_url, is_verified)
    # This function is disabled until OAuth can be updated to work without deprecated fields
    raise ValueError("GitHub OAuth is currently disabled due to deprecated field dependencies")


@api_view(["GET"])
@permission_classes([AllowAny])
def github_oauth_callback(request):
    """Handle GitHub OAuth callback"""
    code = request.GET.get("code")

    if not code:
        return Response({"error": "Authorization code is required"}, status=status.HTTP_400_BAD_REQUEST)

    if not settings.GITHUB_CLIENT_ID or not settings.GITHUB_CLIENT_SECRET:
        return Response({"error": "GitHub OAuth not configured"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    try:
        with transaction.atomic():
            access_token = exchange_code_for_token(code)
            github_data = get_github_user_data(access_token)
            user = create_or_update_user_from_github(github_data)

            session, session_token = create_user_session(user, request)
            tokens = get_tokens_for_user(user)

            return Response(
                {
                    "message": "GitHub authentication successful",
                    "user": UserProfileSerializer(user).data,
                    "tokens": tokens,
                    "session_token": session_token,
                },
                status=status.HTTP_200_OK,
            )

    except requests.RequestException as e:
        return Response({"error": f"GitHub API error: {str(e)}"}, status=status.HTTP_502_BAD_GATEWAY)

    except ValueError as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    except Exception as e:
        return Response({"error": "OAuth authentication failed"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["GET"])
@permission_classes([AllowAny])
def github_oauth_url(request):
    """Get GitHub OAuth URL"""
    if not settings.GITHUB_CLIENT_ID:
        return Response({"error": "GitHub OAuth not configured"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # Build redirect URI with proper HTTPS handling
    redirect_uri = request.build_absolute_uri("/auth/github/callback/")

    # Ensure HTTPS for production deployments
    if request.META.get("HTTP_X_FORWARDED_PROTO") == "https" or "railway.app" in redirect_uri:
        redirect_uri = redirect_uri.replace("http://", "https://")

    oauth_url = (
        f"https://github.com/login/oauth/authorize"
        f"?client_id={settings.GITHUB_CLIENT_ID}"
        f"&redirect_uri={redirect_uri}"
        f"&scope=user:email"
    )

    return Response({"oauth_url": oauth_url}, status=status.HTTP_200_OK)
