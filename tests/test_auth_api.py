import pytest
from django.urls import reverse
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from apps.authentication.models import Company, UserSession

User = get_user_model()


@pytest.mark.django_db
class TestAuthenticationAPI:
    
    def test_user_registration_success(self, api_client):
        url = reverse('register')
        data = {
            'email': 'newuser@testcompany.com',
            'password': 'strongpassword123',
            'password_confirm': 'strongpassword123',
            'first_name': 'New',
            'last_name': 'User',
            'company_name': 'Test Company'
        }
        
        response = api_client.post(url, data)
        
        assert response.status_code == status.HTTP_201_CREATED
        assert 'user' in response.data
        assert 'tokens' in response.data
        assert 'session_token' in response.data
        assert response.data['user']['email'] == 'newuser@testcompany.com'
        
        # Check user was created
        user = User.objects.get(email='newuser@testcompany.com')
        assert user.first_name == 'New'
        assert user.last_name == 'User'
        assert user.company.name == 'Test Company'
    
    def test_user_registration_password_mismatch(self, api_client):
        url = reverse('register')
        data = {
            'email': 'newuser@testcompany.com',
            'password': 'strongpassword123',
            'password_confirm': 'differentpassword123',
            'first_name': 'New',
            'last_name': 'User',
            'company_name': 'Test Company'
        }
        
        response = api_client.post(url, data)
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Passwords don't match" in str(response.data)
    
    def test_user_registration_weak_password(self, api_client):
        url = reverse('register')
        data = {
            'email': 'newuser@testcompany.com',
            'password': '123',
            'password_confirm': '123',
            'first_name': 'New',
            'last_name': 'User',
            'company_name': 'Test Company'
        }
        
        response = api_client.post(url, data)
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
    
    def test_user_login_success(self, api_client, user):
        url = reverse('login')
        data = {
            'email': user.email,
            'password': 'testpassword123'
        }
        
        response = api_client.post(url, data)
        
        assert response.status_code == status.HTTP_200_OK
        assert 'user' in response.data
        assert 'tokens' in response.data
        assert 'session_token' in response.data
        assert response.data['user']['email'] == user.email
    
    def test_user_login_invalid_credentials(self, api_client, user):
        url = reverse('login')
        data = {
            'email': user.email,
            'password': 'wrongpassword'
        }
        
        response = api_client.post(url, data)
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'Invalid credentials' in str(response.data)
    
    def test_user_login_inactive_user(self, api_client, user):
        user.is_active = False
        user.save()
        
        url = reverse('login')
        data = {
            'email': user.email,
            'password': 'testpassword123'
        }
        
        response = api_client.post(url, data)
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'Account is disabled' in str(response.data)
    
    def test_user_logout(self, authenticated_client):
        url = reverse('logout')
        data = {}
        
        response = authenticated_client.post(url, data)
        
        assert response.status_code == status.HTTP_200_OK
        assert 'Logout successful' in response.data['message']
    
    def test_get_profile(self, authenticated_client, user):
        url = reverse('profile')
        
        response = authenticated_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['email'] == user.email
        assert response.data['first_name'] == user.first_name
        assert response.data['last_name'] == user.last_name
        assert response.data['role'] == user.role
    
    def test_update_profile(self, authenticated_client, user):
        url = reverse('profile')
        data = {
            'first_name': 'Updated',
            'last_name': 'Name'
        }
        
        response = authenticated_client.put(url, data)
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['first_name'] == 'Updated'
        assert response.data['last_name'] == 'Name'
        
        # Check user was updated
        user.refresh_from_db()
        assert user.first_name == 'Updated'
        assert user.last_name == 'Name'
    
    def test_change_password(self, authenticated_client, user):
        url = reverse('change_password')
        data = {
            'old_password': 'testpassword123',
            'new_password': 'newstrongpassword456',
            'new_password_confirm': 'newstrongpassword456'
        }
        
        response = authenticated_client.post(url, data)
        
        assert response.status_code == status.HTTP_200_OK
        assert 'Password changed successfully' in response.data['message']
        
        # Check password was changed
        user.refresh_from_db()
        assert user.check_password('newstrongpassword456')
    
    def test_change_password_wrong_old_password(self, authenticated_client):
        url = reverse('change_password')
        data = {
            'old_password': 'wrongoldpassword',
            'new_password': 'newstrongpassword456',
            'new_password_confirm': 'newstrongpassword456'
        }
        
        response = authenticated_client.post(url, data)
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'Old password is incorrect' in str(response.data)
    
    def test_change_password_mismatch(self, authenticated_client):
        url = reverse('change_password')
        data = {
            'old_password': 'testpassword123',
            'new_password': 'newstrongpassword456',
            'new_password_confirm': 'differentpassword456'
        }
        
        response = authenticated_client.post(url, data)
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "New passwords don't match" in str(response.data)


@pytest.mark.django_db
class TestTokenAPI:
    
    def test_refresh_token(self, api_client, user):
        refresh = RefreshToken.for_user(user)
        
        url = reverse('token_refresh')
        data = {
            'refresh': str(refresh)
        }
        
        response = api_client.post(url, data)
        
        assert response.status_code == status.HTTP_200_OK
        assert 'access' in response.data
        assert 'message' in response.data
    
    def test_verify_token_valid(self, api_client, user):
        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)
        
        url = reverse('verify_token')
        data = {
            'token': access_token
        }
        
        response = api_client.post(url, data)
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['valid'] is True
        assert response.data['user_id'] == str(user.id)
        assert response.data['email'] == user.email
        assert response.data['role'] == user.role
    
    def test_verify_token_invalid(self, api_client):
        url = reverse('verify_token')
        data = {
            'token': 'invalid.token.here'
        }
        
        response = api_client.post(url, data)
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.data['valid'] is False
        assert 'Invalid token' in response.data['error']
    
    def test_verify_token_no_token(self, api_client):
        url = reverse('verify_token')
        data = {}
        
        response = api_client.post(url, data)
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data['valid'] is False
        assert 'No token provided' in response.data['error']


@pytest.mark.django_db
class TestSessionAPI:
    
    def test_get_user_sessions(self, authenticated_client, user, user_session):
        session, token = user_session
        
        url = reverse('user_sessions')
        
        response = authenticated_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) >= 1
        assert any(s['id'] == str(session.id) for s in response.data)
    
    def test_terminate_specific_session(self, authenticated_client, user, user_session):
        session, token = user_session
        
        url = reverse('user_sessions')
        data = {
            'session_id': str(session.id)
        }
        
        response = authenticated_client.delete(url, data)
        
        assert response.status_code == status.HTTP_200_OK
        assert 'Session terminated' in response.data['message']
        
        # Check session was deactivated
        session.refresh_from_db()
        assert session.is_active is False
    
    def test_terminate_all_sessions(self, authenticated_client, user):
        url = reverse('user_sessions')
        data = {}
        
        response = authenticated_client.delete(url, data)
        
        assert response.status_code == status.HTTP_200_OK
        assert 'All sessions terminated' in response.data['message']


@pytest.mark.django_db
class TestUnauthorizedAccess:
    
    def test_profile_requires_authentication(self, api_client):
        url = reverse('profile')
        
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    def test_change_password_requires_authentication(self, api_client):
        url = reverse('change_password')
        data = {
            'old_password': 'testpassword123',
            'new_password': 'newpassword456',
            'new_password_confirm': 'newpassword456'
        }
        
        response = api_client.post(url, data)
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    def test_sessions_require_authentication(self, api_client):
        url = reverse('user_sessions')
        
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED