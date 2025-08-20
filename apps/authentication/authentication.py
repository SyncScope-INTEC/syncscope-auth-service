"""
Custom JWT authentication backend with enhanced security for CVE-2024-22513 mitigation.
"""

import hashlib

from django.contrib.auth import get_user_model
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

User = get_user_model()


class SecureJWTAuthentication(JWTAuthentication):
    """
    Enhanced JWT authentication with additional user validation checks
    to mitigate CVE-2024-22513 vulnerability.
    """

    def get_user(self, validated_token):
        """
        Enhanced user retrieval with additional security checks.
        """
        try:
            user_id = validated_token.get("user_id")
            if not user_id:
                raise InvalidToken("Token contained no recognizable user identification")

            user = User.objects.get(id=user_id)

            # Additional security checks
            if not user.is_active:
                raise InvalidToken("User is inactive")

            # Check if password has been changed (invalidate token if so)
            stored_hash = validated_token.get("password_hash")
            if stored_hash and hasattr(user, "password") and user.password:
                current_hash = hashlib.md5(user.password.encode()).hexdigest()
                if stored_hash != current_hash:
                    raise InvalidToken("The user's password has been changed")

            return user

        except User.DoesNotExist:
            raise InvalidToken("User not found")
        except Exception as e:
            raise InvalidToken(f"Token validation failed: {str(e)}")

    def authenticate(self, request):
        """
        Enhanced authentication with additional security logging.
        """
        try:
            result = super().authenticate(request)
            if result:
                user, token = result
                # Log successful authentication
                import logging

                logger = logging.getLogger("apps.authentication")
                logger.info(f"JWT authentication successful for user {user.id}")
            return result
        except Exception as e:
            # Log failed authentication attempts
            import logging

            logger = logging.getLogger("apps.authentication")
            logger.warning(f"JWT authentication failed: {str(e)}")
            raise
