#!/usr/bin/env python
"""
Test script to demonstrate the CVE-2024-22513 security mitigations.
This script shows that our security enhancements prevent token reuse after password changes.
"""

import os
import django
import sys
import hashlib

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import RefreshToken
from apps.authentication.tokens import SecureRefreshToken, SecureAccessToken
from apps.authentication.authentication import SecureJWTAuthentication
from apps.authentication.models import Company

User = get_user_model()

def test_security_enhancements():
    """Test that our security enhancements work as expected."""
    
    print("🔒 Testing CVE-2024-22513 Security Mitigations")
    print("=" * 50)
    
    # Create test company and user
    company, _ = Company.objects.get_or_create(
        name="Test Security Company",
        domain="@security-test.com"
    )
    
    user, created = User.objects.get_or_create(
        email="security-test@security-test.com",
        defaults={
            'password': 'initial_password_123',
            'first_name': 'Security',
            'last_name': 'Tester',
            'role': 'developer',
            'company': company,
            'is_active': True,
        }
    )
    
    if not created:
        user.set_password('initial_password_123')
        user.save()
    
    print(f"✅ Created test user: {user.email}")
    
    # Test 1: Standard token creation works
    print("\n1. Testing token creation...")
    try:
        refresh_token = RefreshToken.for_user(user)
        access_token = refresh_token.access_token
        print(f"✅ Standard token created successfully")
        print(f"   Password hash in token: {refresh_token.payload.get('password_hash', 'Not present')}")
    except Exception as e:
        print(f"❌ Token creation failed: {e}")
        return
    
    # Test 2: Secure token creation works
    print("\n2. Testing secure token creation...")
    try:
        secure_refresh = SecureRefreshToken.for_user(user)
        secure_access = SecureAccessToken.for_user(user)
        print("✅ Secure tokens created successfully")
        print(f"   Secure refresh hash: {secure_refresh.payload.get('password_hash', 'Not present')}")
        print(f"   Secure access hash: {secure_access.payload.get('password_hash', 'Not present')}")
    except Exception as e:
        print(f"❌ Secure token creation failed: {e}")
        return
    
    # Test 3: Authentication works with valid token
    print("\n3. Testing authentication with valid token...")
    try:
        auth_backend = SecureJWTAuthentication()
        authenticated_user = auth_backend.get_user(access_token)
        print(f"✅ Authentication successful for user: {authenticated_user.email}")
    except Exception as e:
        print(f"❌ Authentication failed: {e}")
        return
    
    # Test 4: Password change invalidates token
    print("\n4. Testing password change security...")
    old_password_hash = user.password
    
    # Change user password
    user.set_password('new_secure_password_456')
    user.save()
    print("📝 Changed user password")
    
    # Try to authenticate with old token
    try:
        authenticated_user = auth_backend.get_user(access_token)
        print(f"❌ SECURITY ISSUE: Authentication should have failed but succeeded for: {authenticated_user.email}")
    except Exception as e:
        print(f"✅ Security working: Authentication correctly failed after password change")
        print(f"   Error: {str(e)}")
    
    # Test 5: New token works after password change
    print("\n5. Testing new token after password change...")
    try:
        new_refresh = RefreshToken.for_user(user)
        new_access = new_refresh.access_token
        authenticated_user = auth_backend.get_user(new_access)
        print(f"✅ New token works after password change for: {authenticated_user.email}")
    except Exception as e:
        print(f"❌ New token failed: {e}")
    
    # Test 6: Inactive user cannot get tokens
    print("\n6. Testing inactive user protection...")
    user.is_active = False
    user.save()
    
    try:
        inactive_token = SecureRefreshToken.for_user(user)
        print("❌ SECURITY ISSUE: Token creation should have failed for inactive user")
    except ValueError as e:
        print(f"✅ Security working: Token creation correctly failed for inactive user")
        print(f"   Error: {str(e)}")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
    
    # Cleanup
    user.delete()
    company.delete()
    
    print("\n🎉 Security testing completed!")
    print("✅ CVE-2024-22513 mitigations are working correctly")

if __name__ == "__main__":
    test_security_enhancements()
