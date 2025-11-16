import uuid
from datetime import datetime, timedelta

import requests
from django.conf import settings
from django.contrib.auth import authenticate
from django.core.cache import cache
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
    email = github_data.get("email")
    if not email:
        raise ValueError("GitHub account must have a verified email address")

    email = email.lower()

    # Try to find existing user by email
    try:
        user = User.objects.get(email=email)
        # Update user info if needed
        if github_data.get("name"):
            name_parts = github_data["name"].split(" ", 1)
            if len(name_parts) > 0 and not user.first_name:
                user.first_name = name_parts[0]
            if len(name_parts) > 1 and not user.last_name:
                user.last_name = name_parts[1]

        user.save()
        return user

    except User.DoesNotExist:
        # Create new user
        name_parts = []
        if github_data.get("name"):
            name_parts = github_data["name"].split(" ", 1)

        # Handle company creation/assignment
        company = None
        if github_data.get("company"):
            company_name = github_data["company"].strip()
            if company_name:
                domain = extract_domain_from_email(email)
                company, _ = Company.objects.get_or_create(name=company_name, defaults={"domain": domain})

        user = User.objects.create_user(
            email=email,
            first_name=name_parts[0] if name_parts else "",
            last_name=name_parts[1] if len(name_parts) > 1 else "",
            company=company,
            role="developer",  # Default role for OAuth users
        )

        return user


@api_view(["GET"])
@permission_classes([AllowAny])
def github_oauth_callback(request):
    """Handle GitHub OAuth callback"""
    code = request.GET.get("code")
    state = request.GET.get("state")  # Get state parameter if present

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

            response_data = {
                "message": "GitHub authentication successful",
                "user": UserProfileSerializer(user).data,
                "tokens": tokens,
                "session_token": session_token,
            }

            # If state parameter present, this is from desktop agent - store tokens in cache
            if state:
                cache_key = f"oauth_state_{state}"
                state_data = cache.get(cache_key)

                if state_data:
                    # Update state with tokens
                    cache.set(
                        cache_key,
                        {
                            "status": "completed",
                            "user": response_data["user"],
                            "tokens": response_data["tokens"],
                            "session_token": response_data["session_token"],
                        },
                        timeout=300,  # Keep for 5 minutes to allow agent to retrieve
                    )

                    # Return user-friendly success page for desktop agent
                    from django.http import HttpResponse
                    from django.template import Context, Template

                    logo_url = request.build_absolute_uri(
                        settings.STATIC_URL.rstrip("/") + "/authentication/images/SyncScope%20Logo.png"
                    )
                    icon_url = request.build_absolute_uri(
                        settings.STATIC_URL.rstrip("/") + "/authentication/images/syncscope-logo.svg"
                    )

                    template_str = """
                    <!DOCTYPE html>
                    <html lang="en">
                    <head>
                        <meta charset="UTF-8">
                        <meta name="viewport" content="width=device-width, initial-scale=1.0">
                        <title>SyncScope Agent Login</title>
                        <link rel="icon" href="{{ icon_url }}" type="image/svg+xml">
                        <link rel="alternate icon" href="{{ icon_url }}">
                        <style>
                            * {
                                box-sizing: border-box;
                            }

                            body {
                                font-family: 'Amazon Ember', 'Segoe UI', sans-serif;
                                background: #f5f6f8;
                                color: #0f1111;
                                margin: 0;
                                min-height: 100vh;
                                display: flex;
                                align-items: center;
                                justify-content: center;
                                padding: 32px 16px;
                            }

                            .card-wrapper {
                                width: 100%;
                                max-width: 520px;
                                margin: 0 auto;
                            }

                            .card {
                                background: #fff;
                                border-radius: 16px;
                                padding: 40px 32px;
                                width: 100%;
                                text-align: center;
                                box-shadow: 0 18px 40px rgba(15, 17, 17, 0.12);
                                border: 1px solid #d5dbdb;
                            }

                            .logo {
                                max-width: 180px;
                                height: auto;
                                margin: 0 auto 24px;
                                display: block;
                                image-rendering: -webkit-optimize-contrast;
                                object-fit: contain;
                            }

                            .badge {
                                width: 88px;
                                height: 88px;
                                margin: 0 auto 24px;
                                border-radius: 50%;
                                border: 4px solid #00a650;
                                display: flex;
                                align-items: center;
                                justify-content: center;
                                background: linear-gradient(145deg, #f3fdfa, #e8f5ef);
                            }

                            .badge svg {
                                width: 40px;
                                height: 40px;
                                fill: none;
                                stroke: #00751f;
                                stroke-width: 8;
                                stroke-linecap: round;
                                stroke-linejoin: round;
                            }

                            h1 {
                                font-size: 1.75rem;
                                font-weight: 600;
                                margin-bottom: 12px;
                            }

                            .subtitle {
                                font-size: 1rem;
                                color: #5f6a6a;
                                margin-bottom: 28px;
                            }

                            .panel {
                                background: #f8fbfd;
                                border: 1px solid #d5e3ec;
                                border-radius: 12px;
                                padding: 20px 24px;
                                text-align: left;
                                margin-bottom: 20px;
                            }

                            .panel strong {
                                display: block;
                                font-size: 0.95rem;
                                margin-bottom: 8px;
                            }

                            .panel p {
                                margin: 0;
                                font-size: 0.95rem;
                                color: #374151;
                            }

                            .hint {
                                font-size: 0.9rem;
                                color: #6b7280;
                                margin-top: 16px;
                            }

                            .footer {
                                margin-top: 36px;
                                font-size: 0.85rem;
                                color: #9ca3af;
                            }

                            @media (max-width: 520px) {
                                .card {
                                    padding: 32px 24px;
                                }
                            }
                        </style>
                    </head>
                    <body>
                        <div class="card">
                            <div class="card-wrapper">
                                <img src="{{ logo_url }}" alt="SyncScope logo" class="logo" />

                                <div class="badge" role="img" aria-label="Success">
                                <svg viewBox="0 0 64 64">
                                    <path d="M16 33l8.5 8.5L48 18" />
                                </svg>
                                </div>

                                <h1>Request approved</h1>
                                <p class="subtitle">SyncScope Agent now has access to your GitHub data.</p>

                                <div class="panel">
                                    <strong>You can close this window.</strong>
                                    <p>Your desktop agent will automatically continue once it detects this approval.</p>
                                </div>

                                <p class="hint">Need to try again? Re-run the command from your terminal.</p>

                                <div class="footer">Powered by SyncScope • Secure Auth Flow</div>
                            </div>
                        </div>
                    </body>
                    </html>
                    """
                    template = Template(template_str)
                    context = Context({"logo_url": logo_url, "icon_url": icon_url})
                    html = template.render(context)
                    return HttpResponse(html, content_type="text/html")

            # Regular web OAuth flow - return JSON
            return Response(response_data, status=status.HTTP_200_OK)

    except requests.RequestException as e:
        # If state present, update cache with error
        if state:
            cache_key = f"oauth_state_{state}"
            if cache.get(cache_key):
                cache.set(
                    cache_key,
                    {"status": "error", "error": f"GitHub API error: {str(e)}"},
                    timeout=300,
                )
        return Response({"error": f"GitHub API error: {str(e)}"}, status=status.HTTP_502_BAD_GATEWAY)

    except ValueError as e:
        # If state present, update cache with error
        if state:
            cache_key = f"oauth_state_{state}"
            if cache.get(cache_key):
                cache.set(cache_key, {"status": "error", "error": str(e)}, timeout=300)
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    except Exception as e:
        # If state present, update cache with error
        if state:
            cache_key = f"oauth_state_{state}"
            if cache.get(cache_key):
                cache.set(
                    cache_key,
                    {"status": "error", "error": "OAuth authentication failed"},
                    timeout=300,
                )
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


@api_view(["POST"])
@permission_classes([AllowAny])
def github_oauth_initiate(request):
    """Initiate GitHub OAuth flow for desktop agent - returns state ID and OAuth URL"""
    if not settings.GITHUB_CLIENT_ID:
        return Response({"error": "GitHub OAuth not configured"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # Generate unique state ID for this auth session
    state_id = str(uuid.uuid4())

    # Store state in cache (expires in 10 minutes)
    cache_key = f"oauth_state_{state_id}"
    cache.set(
        cache_key,
        {
            "status": "pending",
            "created_at": datetime.utcnow().isoformat(),
        },
        timeout=600,  # 10 minutes
    )

    # Build redirect URI with state parameter
    redirect_uri = request.build_absolute_uri("/auth/github/callback/")

    # Ensure HTTPS for production deployments
    if request.META.get("HTTP_X_FORWARDED_PROTO") == "https" or "railway.app" in redirect_uri:
        redirect_uri = redirect_uri.replace("http://", "https://")

    oauth_url = (
        f"https://github.com/login/oauth/authorize"
        f"?client_id={settings.GITHUB_CLIENT_ID}"
        f"&redirect_uri={redirect_uri}"
        f"&scope=user:email"
        f"&state={state_id}"  # Include state for tracking
    )

    return Response({"state_id": state_id, "oauth_url": oauth_url, "expires_in": 600}, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([AllowAny])
def github_oauth_status(request, state_id):
    """Check OAuth authentication status for desktop agent"""
    cache_key = f"oauth_state_{state_id}"
    state_data = cache.get(cache_key)

    if not state_data:
        return Response(
            {"status": "expired", "error": "Authentication session expired or not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    if state_data["status"] == "pending":
        return Response(
            {"status": "pending", "message": "Waiting for user to complete authentication"}, status=status.HTTP_200_OK
        )

    elif state_data["status"] == "completed":
        # Return tokens and clean up
        response_data = {
            "status": "completed",
            "message": "Authentication successful",
            "user": state_data["user"],
            "tokens": state_data["tokens"],
            "session_token": state_data["session_token"],
        }

        # Delete state from cache after retrieval
        cache.delete(cache_key)

        return Response(response_data, status=status.HTTP_200_OK)

    elif state_data["status"] == "error":
        error_message = state_data.get("error", "Authentication failed")
        cache.delete(cache_key)
        return Response({"status": "error", "error": error_message}, status=status.HTTP_400_BAD_REQUEST)

    return Response({"status": "unknown", "error": "Invalid state"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
