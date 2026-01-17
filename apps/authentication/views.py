import logging
import os

from django.contrib.auth import authenticate
from django.db import transaction
from django.http import FileResponse, Http404, HttpResponse
from django.template import loader
from django.utils import timezone
from django.utils.decorators import method_decorator
from django_ratelimit.decorators import ratelimit
from drf_spectacular.openapi import OpenApiTypes
from drf_spectacular.utils import OpenApiExample, OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from config.database_retry import atomic_with_retry

from .db_mixins import ServerlessViewMixin
from .models import PasswordResetToken, SupervisedUser, User, UserSession
from .serializers import (
    AcceptInvitationResponseSerializer,
    AcceptInvitationSerializer,
    AuthResponseSerializer,
    ChangeInitialPasswordResponseSerializer,
    ChangeInitialPasswordSerializer,
    CompanyInvitationSerializer,
    ErrorResponseSerializer,
    ForgotPasswordResponseSerializer,
    ForgotPasswordSerializer,
    InviteUserResponseSerializer,
    InviteUserSerializer,
    LogoutResponseSerializer,
    LogoutSerializer,
    PasswordChangeResponseSerializer,
    PasswordChangeSerializer,
    ResetPasswordResponseSerializer,
    ResetPasswordSerializer,
    SessionTerminationResponseSerializer,
    SessionTerminationSerializer,
    SetupAccountResponseSerializer,
    SetupAccountSerializer,
    SupervisedUserCreateSerializer,
    SupervisedUserSerializer,
    TokenRefreshRequestSerializer,
    TokenRefreshResponseSerializer,
    TokenVerificationResponseSerializer,
    TokenVerificationSerializer,
    UserLoginSerializer,
    UserProfileSerializer,
    UserRegistrationSerializer,
    UserSessionSerializer,
    UserUpdateSerializer,
    VerifyResetCodeResponseSerializer,
    VerifyResetCodeSerializer,
)
from .utils import (
    create_user_session,
    generate_reset_code,
    generate_temp_password,
    get_client_ip,
    get_tokens_for_user,
    hash_token,
    invalidate_user_sessions,
    send_reset_email,
    send_welcome_email,
    validate_session_token,
)

logger = logging.getLogger(__name__)


@extend_schema_view(
    post=extend_schema(
        tags=["Authentication"],
        summary="Register a new user",
        description="Create a new user account with email, password, and basic information.",
        request=UserRegistrationSerializer,
        responses={
            201: AuthResponseSerializer,
            400: ErrorResponseSerializer,
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


@extend_schema_view(
    post=extend_schema(
        tags=["Authentication"],
        summary="User login",
        description="Authenticate user with email and password. Returns JWT tokens and session token.",
        request=UserLoginSerializer,
        responses={
            200: AuthResponseSerializer,
            400: ErrorResponseSerializer,
        },
    )
)
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

            # Check if user needs to change their password (temporary password from Stripe setup)
            response_data = {
                "message": "Login successful",
                "user": UserProfileSerializer(user).data,
                "tokens": tokens,
                "session_token": token,
            }

            if user.requires_password_change:
                response_data["requires_password_change"] = True
                response_data["message"] = "Login successful. You must change your temporary password before continuing."

            return Response(response_data, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema_view(
    post=extend_schema(
        tags=["Authentication"],
        summary="User logout",
        description="Logout user by blacklisting refresh token and/or terminating session.",
        request=LogoutSerializer,
        responses={200: LogoutResponseSerializer},
    )
)
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
                    session.delete()
            else:
                invalidate_user_sessions(request.user)

            return Response({"message": "Logout successful"}, status=status.HTTP_200_OK)

        except TokenError:
            pass

        return Response({"message": "Logout completed"}, status=status.HTTP_200_OK)


@extend_schema_view(
    get=extend_schema(
        tags=["User Profile"],
        summary="Get user profile",
        description="Get current user's profile information.",
        responses={200: UserProfileSerializer},
    ),
    put=extend_schema(
        tags=["User Profile"],
        summary="Update user profile",
        description="Update current user's profile information.",
        request=UserUpdateSerializer,
        responses={200: UserProfileSerializer, 400: ErrorResponseSerializer},
    ),
)
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


@extend_schema(
    tags=["User Profile"],
    summary="Get user by ID",
    description="Get user details by user ID. **Authentication required: Include 'Bearer <access_token>' in Authorization header.**",
    parameters=[
        OpenApiParameter(
            name="user_id",
            type=OpenApiTypes.UUID,
            location=OpenApiParameter.PATH,
            description="User ID (UUID)",
            required=True,
        )
    ],
    responses={
        200: UserProfileSerializer,
        404: ErrorResponseSerializer,
        401: ErrorResponseSerializer,
    },
)
class UserByIdView(ServerlessViewMixin, APIView):
    """Get user details by user ID"""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, user_id):
        """Get user by ID"""
        try:
            user = User.objects.get(id=user_id)
            serializer = UserProfileSerializer(user)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)


@extend_schema_view(
    post=extend_schema(
        tags=["User Profile"],
        summary="Change password",
        description="Change current user's password. Requires old password for verification. **Authentication required: Include 'Bearer <access_token>' in Authorization header.**",
        request=PasswordChangeSerializer,
        responses={
            200: PasswordChangeResponseSerializer,
            400: ErrorResponseSerializer,
            401: ErrorResponseSerializer,
        },
    )
)
class ChangePasswordView(ServerlessViewMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = PasswordChangeSerializer(data=request.data, context={"request": request})
        if serializer.is_valid():
            serializer.save()

            invalidate_user_sessions(request.user)

            return Response({"message": "Password changed successfully"}, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    tags=["Authentication"],
    summary="Refresh JWT token",
    description="Refresh access token using refresh token.",
    request=TokenRefreshRequestSerializer,
    responses={
        200: TokenRefreshResponseSerializer,
        401: ErrorResponseSerializer,
    },
)
@method_decorator(ratelimit(key="ip", rate="30/m", method="POST"), name="post")
class CustomTokenRefreshView(TokenRefreshView):
    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code == 200:
            response.data["message"] = "Token refreshed successfully"
        return response


@extend_schema(
    tags=["Authentication"],
    summary="Verify JWT token",
    description="Verify JWT token validity and return user information. Used by other services for authentication.",
    request=TokenVerificationSerializer,
    responses={
        200: TokenVerificationResponseSerializer,
        400: TokenVerificationResponseSerializer,
        401: TokenVerificationResponseSerializer,
        404: TokenVerificationResponseSerializer,
    },
)
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

    except (InvalidToken, TokenError):
        return Response({"valid": False, "error": "Invalid token"}, status=status.HTTP_401_UNAUTHORIZED)


@extend_schema_view(
    get=extend_schema(
        tags=["Session Management"],
        summary="Get active user sessions",
        description="Retrieve all active sessions for the current user.",
        responses={200: UserSessionSerializer(many=True)},
    ),
    delete=extend_schema(
        tags=["Session Management"],
        summary="Terminate user sessions",
        description="Terminate a specific session by ID or all user sessions if no session_id provided.",
        request=SessionTerminationSerializer,
        responses={
            200: SessionTerminationResponseSerializer,
            404: ErrorResponseSerializer,
        },
    ),
)
class UserSessionsView(ServerlessViewMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """Get user's active sessions"""
        sessions = UserSession.objects.filter(user=request.user, expires_at__gt=timezone.now())
        serializer = UserSessionSerializer(sessions, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def delete(self, request):
        """Terminate specific session or all sessions"""
        session_id = request.data.get("session_id")

        if session_id:
            try:
                # Validate UUID format
                import uuid

                uuid.UUID(session_id)

                session = UserSession.objects.get(id=session_id, user=request.user)
                session.delete()
                return Response({"message": "Session terminated"}, status=status.HTTP_200_OK)
            except (ValueError, UserSession.DoesNotExist):
                return Response({"error": "Session not found"}, status=status.HTTP_404_NOT_FOUND)
        else:
            invalidate_user_sessions(request.user)
            return Response({"message": "All sessions terminated"}, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([permissions.AllowAny])
def api_home(request):
    """
    API Home page showing main navigation routes and service links.
    """
    # Define the main navigation routes
    main_routes = [
        {
            "title": "API Documentation",
            "description": "Interactive API documentation with live testing",
            "url": request.build_absolute_uri("/api/docs/"),
            "icon": "📖",
            "category": "documentation",
        },
        {
            "title": "ReDoc Documentation",
            "description": "Clean, three-panel OpenAPI documentation",
            "url": request.build_absolute_uri("/api/redoc/"),
            "icon": "📚",
            "category": "documentation",
        },
        {
            "title": "OpenAPI Schema",
            "description": "Raw OpenAPI specification in JSON format",
            "url": request.build_absolute_uri("/api/schema/"),
            "icon": "⚙️",
            "category": "documentation",
        },
        {
            "title": "Admin Interface",
            "description": "Django admin panel for user and system management",
            "url": request.build_absolute_uri("/admin/"),
            "icon": "🔧",
            "category": "admin",
        },
        {
            "title": "Health Check",
            "description": "Service health status and monitoring",
            "url": request.build_absolute_uri("/health/"),
            "icon": "❤️",
            "category": "monitoring",
        },
    ]

    # Quick stats about the service
    service_info = {
        "endpoints": 15,
        "auth_methods": ["JWT", "GitHub OAuth"],
        "features": ["User Management", "Session Tracking", "Health Monitoring"],
        "status": "Operational",
    }

    context = {
        "main_routes": main_routes,
        "service_info": service_info,
        "api_title": "SyncScope Auth Service",
        "api_version": "1.0.0",
        "api_description": "Authentication and user management service for SyncScope platform",
        "base_url": request.build_absolute_uri("/"),
    }

    # Check if JSON format is explicitly requested
    if request.GET.get("format") == "json":
        return Response(context, status=status.HTTP_200_OK)

    # Try to render HTML template first, fallback to JSON
    try:
        # Check if this is a test case that explicitly uses a mock template
        import sys

        is_testing = "pytest" in sys.modules or "test" in sys.argv
        template = loader.get_template("authentication/api_home.html")
        return HttpResponse(template.render(context, request))
    except:
        # Fallback to JSON response if template doesn't exist
        return Response(context, status=status.HTTP_200_OK)


@extend_schema_view(
    get=extend_schema(
        tags=["Supervision"],
        summary="List supervised users",
        description="Get list of users supervised by the current user or all supervised users if admin.",
    ),
    post=extend_schema(
        tags=["Supervision"],
        summary="Create supervision relationship",
        description="Create a new supervisor-supervised user relationship.",
        request=SupervisedUserCreateSerializer,
    ),
)
class SupervisedUserListCreateView(ServerlessViewMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """Get supervised users based on user role"""
        user = request.user

        if user.role == "admin":
            # Admins can see all supervised relationships in their company
            supervised_users = SupervisedUser.objects.filter(supervisor__company=user.company).select_related(
                "user", "supervisor"
            )
        elif user.role == "supervisor":
            # Supervisors can see their own supervised users
            supervised_users = SupervisedUser.objects.filter(supervisor=user).select_related("user", "supervisor")
        else:
            # Developers can see their own supervision relationships
            supervised_users = SupervisedUser.objects.filter(user=user).select_related("user", "supervisor")

        serializer = SupervisedUserSerializer(supervised_users, many=True)
        return Response(serializer.data)

    @atomic_with_retry()
    def post(self, request):
        """Create a new supervision relationship"""
        user = request.user

        # Only admins and supervisors can create supervision relationships
        if user.role not in ["admin", "supervisor"]:
            return Response(
                {"error": "Only admins and supervisors can create supervision relationships"}, status=status.HTTP_403_FORBIDDEN
            )

        serializer = SupervisedUserCreateSerializer(data=request.data)
        if serializer.is_valid():
            supervised_user = serializer.save()
            response_serializer = SupervisedUserSerializer(supervised_user)
            return Response(response_serializer.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema_view(
    get=extend_schema(
        tags=["Supervision"],
        summary="Get supervision relationship",
        description="Get details of a specific supervision relationship.",
    ),
    put=extend_schema(
        tags=["Supervision"],
        summary="Update supervision relationship",
        description="Update monitoring settings for a supervision relationship.",
    ),
    delete=extend_schema(
        tags=["Supervision"],
        summary="Delete supervision relationship",
        description="Remove a supervision relationship.",
    ),
)
class SupervisedUserDetailView(ServerlessViewMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self, pk, user):
        """Get supervision relationship with permission checking"""
        try:
            supervised_user = SupervisedUser.objects.select_related("user", "supervisor").get(pk=pk)

            # Check permissions
            if user.role == "admin" and user.company == supervised_user.supervisor.company:
                return supervised_user
            elif user.role == "supervisor" and user == supervised_user.supervisor:
                return supervised_user
            elif user == supervised_user.user:
                return supervised_user
            else:
                return None

        except SupervisedUser.DoesNotExist:
            return None

    def get(self, request, pk):
        """Get supervision relationship details"""
        supervised_user = self.get_object(pk, request.user)
        if not supervised_user:
            return Response({"error": "Supervision relationship not found"}, status=status.HTTP_404_NOT_FOUND)

        serializer = SupervisedUserSerializer(supervised_user)
        return Response(serializer.data)

    @atomic_with_retry()
    def put(self, request, pk):
        """Update supervision relationship"""
        supervised_user = self.get_object(pk, request.user)
        if not supervised_user:
            return Response({"error": "Supervision relationship not found"}, status=status.HTTP_404_NOT_FOUND)

        # Only supervisors and admins can update
        if request.user.role not in ["admin", "supervisor"]:
            return Response(
                {"error": "Only supervisors and admins can update supervision relationships"}, status=status.HTTP_403_FORBIDDEN
            )

        # Only allow updating monitoring_enabled field
        monitoring_enabled = request.data.get("monitoring_enabled")
        if monitoring_enabled is not None:
            supervised_user.monitoring_enabled = monitoring_enabled
            supervised_user.save()

        serializer = SupervisedUserSerializer(supervised_user)
        return Response(serializer.data)

    @atomic_with_retry()
    def delete(self, request, pk):
        """Delete supervision relationship"""
        supervised_user = self.get_object(pk, request.user)
        if not supervised_user:
            return Response({"error": "Supervision relationship not found"}, status=status.HTTP_404_NOT_FOUND)

        # Only supervisors and admins can delete
        if request.user.role not in ["admin", "supervisor"]:
            return Response(
                {"error": "Only supervisors and admins can delete supervision relationships"}, status=status.HTTP_403_FORBIDDEN
            )

        supervised_user.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema_view(
    post=extend_schema(
        tags=["User Profile"],
        summary="Upload user profile image",
        description="Upload a profile image for a specific user. Only admins can upload images for other users. Users can only upload images for themselves.",
        parameters=[
            OpenApiParameter(
                name="user_id",
                type=OpenApiTypes.UUID,
                location=OpenApiParameter.PATH,
                description="UUID of the user",
            )
        ],
        request={
            "multipart/form-data": {
                "type": "object",
                "properties": {
                    "image": {"type": "string", "format": "binary", "description": "Profile image file (PNG/JPEG, max 5MB)"}
                },
            }
        },
        responses={
            200: {"type": "object", "properties": {"message": {"type": "string"}, "profile_image_path": {"type": "string"}}},
            400: ErrorResponseSerializer,
            403: ErrorResponseSerializer,
            404: ErrorResponseSerializer,
        },
    ),
    get=extend_schema(
        tags=["User Profile"],
        summary="Get user profile image",
        description="Retrieve a user's profile image. Users can only retrieve their own images unless they are admins.",
        parameters=[
            OpenApiParameter(
                name="user_id",
                type=OpenApiTypes.UUID,
                location=OpenApiParameter.PATH,
                description="UUID of the user",
            )
        ],
        responses={
            200: {"type": "string", "format": "binary", "description": "Profile image file"},
            404: ErrorResponseSerializer,
            403: ErrorResponseSerializer,
        },
    ),
)
class UserImageView(ServerlessViewMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def get_user_or_403(self, user_id, requesting_user):
        """Get user with permission checking"""
        try:
            target_user = User.objects.get(id=user_id)

            # Check permissions: users can only access their own images, admins can access any
            if target_user == requesting_user or requesting_user.role == "admin":
                return target_user
            else:
                return None

        except (User.DoesNotExist, ValueError):
            return None

    @atomic_with_retry()
    def post(self, request, user_id):
        """Upload profile image for a user"""
        target_user = self.get_user_or_403(user_id, request.user)
        if not target_user:
            return Response({"error": "User not found or access denied"}, status=status.HTTP_403_FORBIDDEN)

        image = request.FILES.get("image")
        if not image:
            return Response({"error": "No image file provided"}, status=status.HTTP_400_BAD_REQUEST)

        # Validate file type
        allowed_types = ["image/png", "image/jpeg", "image/jpg"]
        if image.content_type not in allowed_types:
            return Response({"error": "Only PNG and JPEG images are allowed"}, status=status.HTTP_400_BAD_REQUEST)

        # Validate file size (5MB limit)
        max_size = 5 * 1024 * 1024  # 5MB in bytes
        if image.size > max_size:
            return Response({"error": "Image file too large. Maximum size is 5MB"}, status=status.HTTP_400_BAD_REQUEST)

        # Use Railway volume mounted at /images
        images_dir = "/images"

        # Add logging for debugging
        import logging

        logger = logging.getLogger(__name__)

        # Check if images directory exists and is writable
        try:
            if not os.path.exists(images_dir):
                logger.info(f"Creating images directory: {images_dir}")
                os.makedirs(images_dir, exist_ok=True)

            # Test if directory is writable
            test_file = os.path.join(images_dir, ".test_write")
            logger.info(f"Testing write permissions to: {images_dir}")

            with open(test_file, "w") as f:
                f.write("test")
            os.remove(test_file)

            logger.info(f"Successfully verified write access to: {images_dir}")

        except (OSError, PermissionError) as e:
            logger.error(f"Cannot write to {images_dir}: {str(e)}. Using fallback directory.")
            # Fallback to /tmp directory
            images_dir = "/tmp/images"
            if not os.path.exists(images_dir):
                os.makedirs(images_dir, exist_ok=True)
            logger.info(f"Using fallback directory: {images_dir}")

        # Keep original filename but prefix with user_id to avoid conflicts
        filename = f"{target_user.id}_{image.name}"
        file_path = os.path.join(images_dir, filename)

        # Remove old image if it exists
        if target_user.profile_image_path:
            # Handle both /images and /tmp/images paths
            old_filename = os.path.basename(target_user.profile_image_path)
            for old_dir in ["/images", "/tmp/images"]:
                old_file_path = os.path.join(old_dir, old_filename)
                if os.path.exists(old_file_path):
                    try:
                        os.remove(old_file_path)
                        break
                    except OSError:
                        pass  # Continue even if we can't delete the old file

        # Save new image
        try:
            with open(file_path, "wb+") as destination:
                for chunk in image.chunks():
                    destination.write(chunk)

            # Update user's profile_image_path (store just filename, not full path)
            target_user.profile_image_path = filename
            target_user.save(update_fields=["profile_image_path"])

            return Response(
                {"message": "Profile image uploaded successfully", "profile_image_path": filename}, status=status.HTTP_200_OK
            )

        except Exception as e:
            # Better error logging with directory info
            logger.error(f"Image upload failed for user {target_user.id}: {str(e)}")
            logger.error(f"Images directory: {images_dir}")
            logger.error(f"File path: {file_path}")
            logger.error(f"Directory exists: {os.path.exists(images_dir)}")
            logger.error(
                f"Directory permissions: {oct(os.stat(images_dir).st_mode)[-3:] if os.path.exists(images_dir) else 'N/A'}"
            )

            return Response({"error": f"Failed to save image file: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def get(self, request, user_id):
        """Retrieve profile image for a user"""
        target_user = self.get_user_or_403(user_id, request.user)
        if not target_user:
            return Response({"error": "User not found or access denied"}, status=status.HTTP_403_FORBIDDEN)

        if not target_user.profile_image_path:
            raise Http404("Profile image not found")

        # Construct full file path - check both /images and /tmp/images
        filename = target_user.profile_image_path
        file_path = None

        # Try both possible directories
        for images_dir in ["/images", "/tmp/images"]:
            potential_path = os.path.join(images_dir, filename)
            if os.path.exists(potential_path):
                file_path = potential_path
                break

        if not file_path:
            raise Http404("Profile image file not found")

        # Return the image file
        try:
            # Determine content type based on file extension
            content_type = "image/jpeg"  # default
            if file_path.lower().endswith(".png"):
                content_type = "image/png"

            return FileResponse(
                open(file_path, "rb"),
                content_type=content_type,
                as_attachment=False,
                filename=os.path.basename(target_user.profile_image_path),
            )
        except Exception as e:
            raise Http404("Could not retrieve profile image")


@extend_schema_view(
    post=extend_schema(
        tags=["Password Reset"],
        summary="Request password reset code",
        description="Request a 6-digit password reset code to be sent via email. Rate limited to 3 requests per hour.",
        request=ForgotPasswordSerializer,
        responses={
            200: ForgotPasswordResponseSerializer,
            400: ErrorResponseSerializer,
            429: ErrorResponseSerializer,
        },
    )
)
@method_decorator(ratelimit(key="ip", rate="3/h", method="POST"), name="post")
class ForgotPasswordView(ServerlessViewMixin, APIView):
    """Request password reset code"""

    permission_classes = [permissions.AllowAny]

    @atomic_with_retry()
    def post(self, request):
        serializer = ForgotPasswordSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        email = serializer.validated_data["email"]

        try:
            user = User.objects.get(email=email, is_active=True)

            # Invalidate any existing reset tokens for this user
            PasswordResetToken.invalidate_user_tokens(user)

            # Generate new 6-digit code
            reset_code = generate_reset_code()
            code_hash = hash_token(reset_code)

            # Create reset token
            PasswordResetToken.objects.create(user=user, code_hash=code_hash)

            # Send email via alerts service
            user_name = user.full_name or user.email
            email_sent = send_reset_email(user.email, user_name, reset_code)

            if not email_sent:
                return Response(
                    {"error": "Failed to send reset email. Please try again later."},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

        except User.DoesNotExist:
            # Don't reveal that user doesn't exist for security
            pass

        # Always return success to prevent user enumeration
        return Response(
            {
                "message": "If an account with that email exists, a password reset code has been sent. The code will expire in 1 hour."
            },
            status=status.HTTP_200_OK,
        )


@extend_schema_view(
    post=extend_schema(
        tags=["Password Reset"],
        summary="Verify password reset code",
        description="Verify that a 6-digit reset code is valid before attempting password reset. Maximum 5 attempts allowed.",
        request=VerifyResetCodeSerializer,
        responses={
            200: VerifyResetCodeResponseSerializer,
            400: ErrorResponseSerializer,
        },
    )
)
class VerifyResetCodeView(ServerlessViewMixin, APIView):
    """Verify password reset code without resetting password"""

    permission_classes = [permissions.AllowAny]

    @atomic_with_retry()
    def post(self, request):
        serializer = VerifyResetCodeSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        email = serializer.validated_data["email"]
        code = serializer.validated_data["code"]
        code_hash = hash_token(code)

        try:
            user = User.objects.get(email=email, is_active=True)

            # Get the most recent valid token
            reset_token = (
                PasswordResetToken.objects.filter(user=user, code_hash=code_hash, is_used=False, is_invalidated=False)
                .order_by("-created_at")
                .first()
            )

            if not reset_token:
                return Response(
                    {"valid": False, "message": "Invalid or expired reset code"}, status=status.HTTP_400_BAD_REQUEST
                )

            # Check if token is valid
            if not reset_token.is_valid():
                if reset_token.is_expired():
                    return Response(
                        {"valid": False, "message": "Reset code has expired. Please request a new one."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                elif reset_token.attempts >= 5:
                    return Response(
                        {
                            "valid": False,
                            "message": "Maximum verification attempts exceeded. Please request a new reset code.",
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                else:
                    return Response(
                        {"valid": False, "message": "Invalid or expired reset code"}, status=status.HTTP_400_BAD_REQUEST
                    )

            return Response({"valid": True, "message": "Reset code is valid"}, status=status.HTTP_200_OK)

        except User.DoesNotExist:
            return Response({"valid": False, "message": "Invalid or expired reset code"}, status=status.HTTP_400_BAD_REQUEST)


@extend_schema_view(
    post=extend_schema(
        tags=["Password Reset"],
        summary="Reset password with code",
        description="Reset password using the 6-digit code received via email. All active sessions will be terminated.",
        request=ResetPasswordSerializer,
        responses={
            200: ResetPasswordResponseSerializer,
            400: ErrorResponseSerializer,
        },
    )
)
class ResetPasswordView(ServerlessViewMixin, APIView):
    """Reset password using verification code"""

    permission_classes = [permissions.AllowAny]

    @atomic_with_retry()
    def post(self, request):
        serializer = ResetPasswordSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        email = serializer.validated_data["email"]
        code = serializer.validated_data["code"]
        new_password = serializer.validated_data["new_password"]
        code_hash = hash_token(code)

        try:
            user = User.objects.get(email=email, is_active=True)

            # Get the most recent valid token
            reset_token = (
                PasswordResetToken.objects.filter(user=user, code_hash=code_hash, is_used=False, is_invalidated=False)
                .order_by("-created_at")
                .first()
            )

            if not reset_token:
                return Response({"error": "Invalid or expired reset code"}, status=status.HTTP_400_BAD_REQUEST)

            # Increment attempts
            reset_token.increment_attempts()

            # Check if token is still valid after incrementing
            if not reset_token.is_valid():
                if reset_token.is_expired():
                    return Response(
                        {"error": "Reset code has expired. Please request a new one."}, status=status.HTTP_400_BAD_REQUEST
                    )
                elif reset_token.is_invalidated:
                    return Response(
                        {"error": "Maximum attempts exceeded. Please request a new reset code."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                else:
                    return Response({"error": "Invalid or expired reset code"}, status=status.HTTP_400_BAD_REQUEST)

            # Reset password
            user.set_password(new_password)
            user.save(update_fields=["password"])

            # Mark token as used
            reset_token.mark_as_used()

            # Invalidate all active sessions (log out all devices)
            invalidate_user_sessions(user)

            return Response(
                {"message": "Password has been reset successfully. Please log in with your new password."},
                status=status.HTTP_200_OK,
            )

        except User.DoesNotExist:
            return Response({"error": "Invalid or expired reset code"}, status=status.HTTP_400_BAD_REQUEST)


@extend_schema_view(
    post=extend_schema(
        tags=["Account Setup"],
        summary="Setup account after Stripe payment",
        description="Create or update user account with temporary password after Stripe payment. Sends welcome email with credentials. Public endpoint - no authentication required.",
        request=SetupAccountSerializer,
        responses={
            200: SetupAccountResponseSerializer,
            201: SetupAccountResponseSerializer,
            400: ErrorResponseSerializer,
            500: ErrorResponseSerializer,
        },
    )
)
@method_decorator(ratelimit(key="ip", rate="5/m", method="POST"), name="post")
class SetupAccountView(ServerlessViewMixin, APIView):
    """Setup account after Stripe payment with temporary password"""

    permission_classes = [permissions.AllowAny]

    @atomic_with_retry()
    def post(self, request):
        serializer = SetupAccountSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        email = serializer.validated_data["email"]
        first_name = serializer.validated_data.get("first_name", "")
        last_name = serializer.validated_data.get("last_name", "")
        plan = serializer.validated_data.get("plan", "starter")

        # Generate temporary password
        temp_password = generate_temp_password()

        # Check if user already exists
        try:
            user = User.objects.get(email=email)
            user_created = False

            # Update existing user with new temporary password
            user.set_password(temp_password)
            user.requires_password_change = True

            # Update name and plan if provided
            if first_name:
                user.first_name = first_name
            if last_name:
                user.last_name = last_name
            user.plan = plan

            user.save()

        except User.DoesNotExist:
            # Create new user
            user_created = True
            user = User.objects.create_user(
                email=email,
                password=temp_password,
                first_name=first_name or "User",
                last_name=last_name or "",
                plan=plan,
                requires_password_change=True,
            )

        # Send welcome email with temporary password
        user_name = user.full_name or user.email
        email_sent = send_welcome_email(user.email, user_name, temp_password, plan)

        if not email_sent:
            return Response(
                {"error": "Account created but failed to send welcome email. Please contact support."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        status_code = status.HTTP_201_CREATED if user_created else status.HTTP_200_OK
        message = "Account created successfully" if user_created else "Account updated successfully"

        return Response(
            {
                "message": f"{message}. Welcome email sent with temporary password.",
                "email": user.email,
                "user_id": str(user.id),
                "user_created": user_created,
            },
            status=status_code,
        )


@extend_schema_view(
    post=extend_schema(
        tags=["Account Setup"],
        summary="Change initial temporary password",
        description="Change temporary password received via email to a new permanent password. Requires authentication with temporary password. Returns new JWT tokens.",
        request=ChangeInitialPasswordSerializer,
        responses={
            200: ChangeInitialPasswordResponseSerializer,
            400: ErrorResponseSerializer,
            401: ErrorResponseSerializer,
        },
    )
)
class ChangeInitialPasswordView(ServerlessViewMixin, APIView):
    """Change initial temporary password to permanent password"""

    permission_classes = [permissions.IsAuthenticated]

    @atomic_with_retry()
    def post(self, request):
        serializer = ChangeInitialPasswordSerializer(data=request.data, context={"request": request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user = request.user
        new_password = serializer.validated_data["new_password"]

        # Set new password and clear the requires_password_change flag
        user.set_password(new_password)
        user.requires_password_change = False
        user.save(update_fields=["password", "requires_password_change"])

        # Invalidate all existing sessions (force re-login everywhere)
        invalidate_user_sessions(user)

        # Generate new tokens for this session
        tokens = get_tokens_for_user(user)

        return Response(
            {"message": "Password changed successfully. Please use your new password for future logins.", "tokens": tokens},
            status=status.HTTP_200_OK,
        )


@extend_schema_view(
    post=extend_schema(
        tags=["Company Invitations"],
        summary="Invite a user to join your company",
        description="Send an invitation email to a new user to join your company. Requires authentication. The invitee will receive an email with a link to accept the invitation and join via GitHub OAuth.",
        request=InviteUserSerializer,
        responses={
            201: InviteUserResponseSerializer,
            400: ErrorResponseSerializer,
            401: ErrorResponseSerializer,
            403: ErrorResponseSerializer,
        },
    ),
    get=extend_schema(
        tags=["Company Invitations"],
        summary="List company invitations",
        description="Get a list of all invitations sent by users in your company. Requires authentication.",
        responses={
            200: CompanyInvitationSerializer(many=True),
            401: ErrorResponseSerializer,
        },
    ),
)
class CompanyInvitationView(ServerlessViewMixin, APIView):
    """Create and list company invitations"""

    permission_classes = [permissions.IsAuthenticated]

    @atomic_with_retry()
    def post(self, request):
        """Send a company invitation"""
        from .models import CompanyInvitation
        from .utils import send_invitation_email

        user = request.user

        # Check if user has a company
        if not user.company:
            return Response(
                {"error": "You must be associated with a company to send invitations"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check if user can invite (must be admin or supervisor)
        if user.role not in ["admin", "supervisor"]:
            return Response(
                {"error": "Only administrators and supervisors can send invitations"},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = InviteUserSerializer(data=request.data, context={"request": request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        invitee_email = serializer.validated_data["invitee_email"]
        role = serializer.validated_data["role"]

        # Check for existing pending invitation
        existing_invitation = CompanyInvitation.objects.filter(
            company=user.company,
            invitee_email=invitee_email,
            is_accepted=False,
        ).first()

        if existing_invitation:
            if existing_invitation.is_expired():
                # Delete expired invitation to allow sending a new one
                existing_invitation.delete()
            else:
                # Active invitation already exists
                return Response(
                    {
                        "error": f"An invitation has already been sent to {invitee_email}. Please wait for it to expire or be accepted."
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Create the invitation
        invitation = CompanyInvitation.objects.create(
            company=user.company, inviter=user, invitee_email=invitee_email, role=role
        )

        # Send invitation email
        email_sent = send_invitation_email(
            invitee_email=invitee_email,
            inviter_name=user.full_name or user.email,
            inviter_email=user.email,
            company_name=user.company.name,
            role=role,
            invitation_token=invitation.token,
        )

        if not email_sent:
            # Still return success even if email fails, but log it
            logger.warning(f"Failed to send invitation email to {invitee_email}")

        return Response(
            {
                "message": f"Invitation sent to {invitee_email}",
                "invitation_id": invitation.id,
                "invitee_email": invitee_email,
            },
            status=status.HTTP_201_CREATED,
        )

    def get(self, request):
        """List all invitations for the user's company"""
        from .models import CompanyInvitation

        user = request.user

        if not user.company:
            return Response([], status=status.HTTP_200_OK)

        # Get all invitations for the company
        invitations = CompanyInvitation.objects.filter(company=user.company).order_by("-created_at")
        serializer = CompanyInvitationSerializer(invitations, many=True)

        return Response(serializer.data, status=status.HTTP_200_OK)


@extend_schema_view(
    post=extend_schema(
        tags=["Company Invitations"],
        summary="Accept a company invitation",
        description="Accept a company invitation using the token from the email. This endpoint should be called after the user authenticates via GitHub OAuth. The user will be associated with the company.",
        request=AcceptInvitationSerializer,
        responses={
            200: AcceptInvitationResponseSerializer,
            400: ErrorResponseSerializer,
            401: ErrorResponseSerializer,
        },
    ),
    get=extend_schema(
        tags=["Company Invitations"],
        summary="Validate invitation token",
        description="Validate an invitation token without accepting it. Returns invitation details if valid.",
        responses={
            200: CompanyInvitationSerializer,
            400: ErrorResponseSerializer,
        },
    ),
)
class AcceptInvitationView(ServerlessViewMixin, APIView):
    """Accept or validate a company invitation"""

    permission_classes = [permissions.IsAuthenticated]

    @atomic_with_retry()
    def post(self, request):
        """Accept a company invitation"""
        from .models import CompanyInvitation

        serializer = AcceptInvitationSerializer(data=request.data, context={"request": request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        invitation = serializer.context["invitation"]
        user = request.user

        # Check if user is already part of a different company
        if user.company and user.company != invitation.company:
            return Response(
                {"error": f"You are already part of {user.company.name}. Please contact support to change companies."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Accept the invitation (this also updates the user's company and role)
        try:
            invitation.accept(user)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        # Serialize user data
        from .serializers import UserProfileSerializer

        user.refresh_from_db()
        user_serializer = UserProfileSerializer(user)

        return Response(
            {
                "message": f"Welcome to {invitation.company.name}!",
                "user": user_serializer.data,
                "company_name": invitation.company.name,
            },
            status=status.HTTP_200_OK,
        )

    def get(self, request):
        """Validate invitation token and return invitation details"""
        from .models import CompanyInvitation

        token = request.query_params.get("token")
        if not token:
            return Response({"error": "Token is required"}, status=status.HTTP_400_BAD_REQUEST)

        invitation = CompanyInvitation.get_active_invitation(token)
        if not invitation:
            return Response({"error": "Invalid or expired invitation token"}, status=status.HTTP_400_BAD_REQUEST)

        serializer = CompanyInvitationSerializer(invitation)
        return Response(serializer.data, status=status.HTTP_200_OK)
