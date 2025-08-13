import requests
from django.conf import settings
from django.contrib.auth import authenticate
from django.db import transaction
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import User, Company
from .serializers import UserProfileSerializer
from .utils import create_user_session, get_tokens_for_user, extract_domain_from_email


def exchange_code_for_token(code):
    """Exchange authorization code for access token with GitHub"""
    token_url = 'https://github.com/login/oauth/access_token'
    
    data = {
        'client_id': settings.GITHUB_CLIENT_ID,
        'client_secret': settings.GITHUB_CLIENT_SECRET,
        'code': code,
    }
    
    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    
    response = requests.post(token_url, data=data, headers=headers)
    response.raise_for_status()
    
    return response.json().get('access_token')


def get_github_user_data(access_token):
    """Get user data from GitHub API"""
    user_url = 'https://api.github.com/user'
    emails_url = 'https://api.github.com/user/emails'
    
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Accept': 'application/vnd.github.v3+json'
    }
    
    user_response = requests.get(user_url, headers=headers)
    user_response.raise_for_status()
    user_data = user_response.json()
    
    emails_response = requests.get(emails_url, headers=headers)
    emails_response.raise_for_status()
    emails_data = emails_response.json()
    
    primary_email = next(
        (email['email'] for email in emails_data if email['primary']), 
        user_data.get('email')
    )
    
    return {
        'id': user_data['id'],
        'login': user_data['login'],
        'email': primary_email,
        'name': user_data.get('name', ''),
        'avatar_url': user_data.get('avatar_url'),
        'company': user_data.get('company'),
    }


def create_or_update_user_from_github(github_data):
    """Create or update user from GitHub data"""
    github_id = str(github_data['id'])
    email = github_data['email']
    
    if not email:
        raise ValueError("GitHub account must have a public email")
    
    email = email.lower()
    name_parts = github_data.get('name', '').split(' ', 1)
    first_name = name_parts[0] if name_parts else github_data['login']
    last_name = name_parts[1] if len(name_parts) > 1 else ''
    
    try:
        user = User.objects.get(github_id=github_id)
        user.email = email
        user.first_name = first_name
        user.last_name = last_name
        user.avatar_url = github_data.get('avatar_url')
        user.is_verified = True
        user.save()
        return user
    except User.DoesNotExist:
        pass
    
    try:
        user = User.objects.get(email=email)
        user.github_id = github_id
        user.avatar_url = github_data.get('avatar_url')
        user.is_verified = True
        user.save()
        return user
    except User.DoesNotExist:
        pass
    
    domain = extract_domain_from_email(email)
    company = None
    
    if github_data.get('company'):
        company, _ = Company.objects.get_or_create(
            name=github_data['company'],
            defaults={'domain': domain}
        )
    
    user = User.objects.create_user(
        email=email,
        first_name=first_name,
        last_name=last_name,
        github_id=github_id,
        avatar_url=github_data.get('avatar_url'),
        company=company,
        is_verified=True,
        password=None
    )
    
    return user


@api_view(['POST'])
@permission_classes([AllowAny])
def github_oauth_callback(request):
    """Handle GitHub OAuth callback"""
    code = request.data.get('code')
    
    if not code:
        return Response({
            'error': 'Authorization code is required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    if not settings.GITHUB_CLIENT_ID or not settings.GITHUB_CLIENT_SECRET:
        return Response({
            'error': 'GitHub OAuth not configured'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    try:
        with transaction.atomic():
            access_token = exchange_code_for_token(code)
            github_data = get_github_user_data(access_token)
            user = create_or_update_user_from_github(github_data)
            
            session, session_token = create_user_session(user, request)
            tokens = get_tokens_for_user(user)
            
            return Response({
                'message': 'GitHub authentication successful',
                'user': UserProfileSerializer(user).data,
                'tokens': tokens,
                'session_token': session_token
            }, status=status.HTTP_200_OK)
            
    except requests.RequestException as e:
        return Response({
            'error': f'GitHub API error: {str(e)}'
        }, status=status.HTTP_502_BAD_GATEWAY)
    
    except ValueError as e:
        return Response({
            'error': str(e)
        }, status=status.HTTP_400_BAD_REQUEST)
    
    except Exception as e:
        return Response({
            'error': 'OAuth authentication failed'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([AllowAny])
def github_oauth_url(request):
    """Get GitHub OAuth URL"""
    if not settings.GITHUB_CLIENT_ID:
        return Response({
            'error': 'GitHub OAuth not configured'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    redirect_uri = request.build_absolute_uri('/auth/github/callback/')
    
    oauth_url = (
        f"https://github.com/login/oauth/authorize"
        f"?client_id={settings.GITHUB_CLIENT_ID}"
        f"&redirect_uri={redirect_uri}"
        f"&scope=user:email"
    )
    
    return Response({
        'oauth_url': oauth_url
    }, status=status.HTTP_200_OK)