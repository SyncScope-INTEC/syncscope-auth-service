from django.contrib.auth import authenticate
from django.db import transaction
from django.utils import timezone
from django.utils.decorators import method_decorator
from django_ratelimit.decorators import ratelimit
from drf_spectacular.openapi import OpenApiTypes
from drf_spectacular.utils import OpenApiExample, OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from config.database_retry import atomic_with_retry

from .db_mixins import ServerlessViewMixin
from .models import User, UserSession
from .serializers import (
    PasswordChangeSerializer,
    UserLoginSerializer,
    UserProfileSerializer,
    UserRegistrationSerializer,
    UserSessionSerializer,
    UserUpdateSerializer,
)
from .utils import create_user_session, get_client_ip, get_tokens_for_user, invalidate_user_sessions, validate_session_token


@extend_schema_view(
    post=extend_schema(
        tags=["Authentication"],
        summary="Register a new user",
        description="Create a new user account with email, password, and basic information.",
        request=UserRegistrationSerializer,
        responses={
            201: OpenApiExample(
                "Success",
                value={
                    "message": "User registered successfully",
                    "user": {
                        "id": "uuid",
                        "email": "user@example.com",
                        "first_name": "John",
                        "last_name": "Doe",
                        "role": "developer",
                        "company": None,
                    },
                    "tokens": {"access": "jwt_access_token", "refresh": "jwt_refresh_token"},
                    "session_token": "session_token",
                },
            ),
            400: "Bad Request - Validation errors",
        },
    )
)
@method_decorator(ratelimit(key="ip", rate="5/m", method="POST"), name="post")
class RegisterView(ServerlessViewMixin, APIView):
    permission_classes = [permissions.AllowAny]

    @atomic_with_retry()
    def post(self, request):
        serializer = UserRegistrationSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            session, token = create_user_session(user, request)
            tokens = get_tokens_for_user(user)

            return Response(
                {
                    "message": "User registered successfully",
                    "user": UserProfileSerializer(user).data,
                    "tokens": tokens,
                    "session_token": token,
                },
                status=status.HTTP_201_CREATED,
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@method_decorator(ratelimit(key="ip", rate="10/m", method="POST"), name="post")
class LoginView(ServerlessViewMixin, APIView):
    permission_classes = [permissions.AllowAny]

    @atomic_with_retry()
    def post(self, request):
        serializer = UserLoginSerializer(data=request.data, context={"request": request})
        if serializer.is_valid():
            user = serializer.validated_data["user"]

            session, token = create_user_session(user, request)
            tokens = get_tokens_for_user(user)

            user.last_login = timezone.now()
            user.save(update_fields=["last_login"])

            return Response(
                {
                    "message": "Login successful",
                    "user": UserProfileSerializer(user).data,
                    "tokens": tokens,
                    "session_token": token,
                },
                status=status.HTTP_200_OK,
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LogoutView(ServerlessViewMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        try:
            refresh_token = request.data.get("refresh_token")
            session_token = request.data.get("session_token")

            if refresh_token:
                token = RefreshToken(refresh_token)
                token.blacklist()

            if session_token:
                session = validate_session_token(session_token)
                if session and session.user == request.user:
                    session.deactivate()
            else:
                invalidate_user_sessions(request.user)

            return Response({"message": "Logout successful"}, status=status.HTTP_200_OK)

        except TokenError:
            pass

        return Response({"message": "Logout completed"}, status=status.HTTP_200_OK)


class ProfileView(ServerlessViewMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        serializer = UserProfileSerializer(request.user)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request):
        serializer = UserUpdateSerializer(request.user, data=request.data, partial=True)
        if serializer.is_valid():
            user = serializer.save()
            return Response(UserProfileSerializer(user).data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ChangePasswordView(ServerlessViewMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = PasswordChangeSerializer(data=request.data, context={"request": request})
        if serializer.is_valid():
            serializer.save()

            invalidate_user_sessions(request.user)

            return Response({"message": "Password changed successfully"}, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@method_decorator(ratelimit(key="ip", rate="30/m", method="POST"), name="post")
class CustomTokenRefreshView(TokenRefreshView):
    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code == 200:
            response.data["message"] = "Token refreshed successfully"
        return response


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
@ratelimit(key="ip", rate="60/m", method="POST")
def verify_token(request):
    """Endpoint for other services to verify JWT tokens"""
    token = request.data.get("token")
    if not token:
        return Response({"valid": False, "error": "No token provided"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        from rest_framework_simplejwt.tokens import AccessToken

        access_token = AccessToken(token)
        user_id = access_token.payload.get("user_id")

        try:
            user = User.objects.get(id=user_id, is_active=True)
            return Response(
                {
                    "valid": True,
                    "user_id": str(user.id),
                    "email": user.email,
                    "role": user.role,
                    "company_id": str(user.company.id) if user.company else None,
                },
                status=status.HTTP_200_OK,
            )
        except User.DoesNotExist:
            return Response({"valid": False, "error": "User not found"}, status=status.HTTP_404_NOT_FOUND)

    except InvalidToken:
        return Response({"valid": False, "error": "Invalid token"}, status=status.HTTP_401_UNAUTHORIZED)


class UserSessionsView(ServerlessViewMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """Get user's active sessions"""
        sessions = UserSession.objects.filter(user=request.user, is_active=True, expires_at__gt=timezone.now())
        serializer = UserSessionSerializer(sessions, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def delete(self, request):
        """Terminate specific session or all sessions"""
        session_id = request.data.get("session_id")

        if session_id:
            try:
                session = UserSession.objects.get(id=session_id, user=request.user, is_active=True)
                session.deactivate()
                return Response({"message": "Session terminated"}, status=status.HTTP_200_OK)
            except UserSession.DoesNotExist:
                return Response({"error": "Session not found"}, status=status.HTTP_404_NOT_FOUND)
        else:
            invalidate_user_sessions(request.user)
            return Response({"message": "All sessions terminated"}, status=status.HTTP_200_OK)
