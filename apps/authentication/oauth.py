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

                    html = """
                    <!DOCTYPE html>
                    <html>
                    <head>
                        <title>SyncScope - Authentication Success</title>
                        <meta name="viewport" content="width=device-width, initial-scale=1.0">
                        <style>
                            * {
                                margin: 0;
                                padding: 0;
                                box-sizing: border-box;
                            }

                            body {
                                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Helvetica Neue', sans-serif;
                                display: flex;
                                justify-content: center;
                                align-items: center;
                                min-height: 100vh;
                                background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f1419 100%);
                                padding: 20px;
                            }

                            .container {
                                background: rgba(255, 255, 255, 0.98);
                                padding: 3rem 2.5rem;
                                border-radius: 20px;
                                box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
                                text-align: center;
                                max-width: 500px;
                                width: 100%;
                                animation: slideIn 0.5s ease-out;
                            }

                            @keyframes slideIn {
                                from {
                                    opacity: 0;
                                    transform: translateY(30px);
                                }
                                to {
                                    opacity: 1;
                                    transform: translateY(0);
                                }
                            }

                            .logo-container {
                                margin-bottom: 2rem;
                                display: flex;
                                justify-content: center;
                                align-items: center;
                            }

                            .logo {
                                width: 120px;
                                height: 120px;
                                animation: pulse 2s ease-in-out infinite;
                            }

                            @keyframes pulse {
                                0%, 100% {
                                    transform: scale(1);
                                }
                                50% {
                                    transform: scale(1.05);
                                }
                            }

                            .success-icon {
                                width: 80px;
                                height: 80px;
                                margin: 0 auto 1.5rem;
                                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                                border-radius: 50%;
                                display: flex;
                                align-items: center;
                                justify-content: center;
                                animation: scaleIn 0.5s ease-out 0.3s both;
                            }

                            @keyframes scaleIn {
                                from {
                                    transform: scale(0);
                                }
                                to {
                                    transform: scale(1);
                                }
                            }

                            .checkmark {
                                font-size: 3rem;
                                color: white;
                                font-weight: bold;
                            }

                            h1 {
                                color: #1a1a2e;
                                margin-bottom: 1rem;
                                font-size: 2.2rem;
                                font-weight: 700;
                                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                                -webkit-background-clip: text;
                                -webkit-text-fill-color: transparent;
                                background-clip: text;
                            }

                            .subtitle {
                                color: #4a5568;
                                font-size: 1.1rem;
                                margin-bottom: 1.5rem;
                                line-height: 1.6;
                            }

                            .message {
                                background: #f7fafc;
                                border-left: 4px solid #667eea;
                                padding: 1.25rem;
                                border-radius: 8px;
                                color: #2d3748;
                                font-size: 1rem;
                                line-height: 1.7;
                                margin-top: 1.5rem;
                            }

                            .message strong {
                                color: #1a202c;
                                font-weight: 600;
                            }

                            .footer {
                                margin-top: 2rem;
                                padding-top: 1.5rem;
                                border-top: 1px solid #e2e8f0;
                                color: #718096;
                                font-size: 0.9rem;
                            }
                        </style>
                    </head>
                    <body>
                        <div class="container">
                            <div class="logo-container">
                                <svg class="logo" viewBox="0 0 200 200" xmlns="http://www.w3.org/2000/svg">
                                    <!-- SyncScope Logo SVG -->
                                    <defs>
                                        <linearGradient id="grad1" x1="0%" y1="0%" x2="100%" y2="100%">
                                            <stop offset="0%" style="stop-color:#CDFF00;stop-opacity:1" />
                                            <stop offset="100%" style="stop-color:#9AFF00;stop-opacity:1" />
                                        </linearGradient>
                                        <linearGradient id="grad2" x1="0%" y1="0%" x2="100%" y2="100%">
                                            <stop offset="0%" style="stop-color:#B794F4;stop-opacity:1" />
                                            <stop offset="100%" style="stop-color:#9F7AEA;stop-opacity:1" />
                                        </linearGradient>
                                    </defs>
                                    <!-- Yellow S -->
                                    <path d="M 80,50 L 100,50 L 100,90 L 120,90 L 120,110 L 100,110 L 100,150 L 80,150 L 80,110 L 60,110 L 60,90 L 80,90 Z"
                                          fill="url(#grad1)" stroke="none"/>
                                    <!-- Purple S -->
                                    <path d="M 100,60 L 120,60 L 120,100 L 140,100 L 140,120 L 120,120 L 120,160 L 100,160 L 100,120 L 80,120 L 80,100 L 100,100 Z"
                                          fill="url(#grad2)" stroke="none" opacity="0.9"/>
                                </svg>
                            </div>

                            <div class="success-icon">
                                <div class="checkmark">✓</div>
                            </div>

                            <h1>Authentication Successful!</h1>

                            <p class="subtitle">
                                You have successfully authenticated with GitHub.
                            </p>

                            <div class="message">
                                <strong>You can now close this window</strong> and return to the SyncScope application to start tracking your development activity.
                            </div>

                            <div class="footer">
                                Powered by SyncScope
                            </div>
                        </div>
                    </body>
                    </html>
                    """
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
