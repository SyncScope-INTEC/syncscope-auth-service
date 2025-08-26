from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import Company, SupervisedUser, User, UserSession


class CompanySerializer(serializers.ModelSerializer):
    class Meta:
        model = Company
        fields = ["id", "name", "domain", "industry", "size", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_domain(self, value):
        if value and not value.startswith("@"):
            value = f"@{value}"
        return value


class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True,
        validators=[validate_password],
        help_text="Password must be at least 8 characters long",
        style={"input_type": "password"},
    )
    password_confirm = serializers.CharField(
        write_only=True, help_text="Re-enter password for confirmation", style={"input_type": "password"}
    )
    company_name = serializers.CharField(
        write_only=True,
        required=False,
        help_text="Optional company name. If provided, a new company will be created or linked.",
    )

    class Meta:
        model = User
        fields = ["email", "first_name", "last_name", "password", "password_confirm", "company_name", "role"]
        extra_kwargs = {
            "role": {"default": "developer", "help_text": "User role: developer, supervisor, or admin"},
            "email": {"help_text": "User's email address (must be unique)"},
            "first_name": {"help_text": "User's first name"},
            "last_name": {"help_text": "User's last name"},
        }

    def validate(self, attrs):
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError("Passwords don't match")

        email = attrs.get("email", "").lower()
        domain = f"@{email.split('@')[1]}" if "@" in email else None

        if attrs.get("company_name"):
            company, created = Company.objects.get_or_create(name=attrs["company_name"], defaults={"domain": domain})
            if not created and company.domain != domain:
                raise serializers.ValidationError(f"Email domain must match company domain: {company.domain}")
            attrs["company"] = company

        return attrs

    def create(self, validated_data):
        validated_data.pop("password_confirm")
        validated_data.pop("company_name", None)
        password = validated_data.pop("password")

        user = User.objects.create_user(password=password, **validated_data)
        return user


class UserLoginSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True, help_text="User's email address")
    password = serializers.CharField(
        write_only=True, required=True, help_text="User's password", style={"input_type": "password"}
    )

    def validate(self, attrs):
        email = attrs.get("email", "")
        password = attrs.get("password")

        if not email or not password:
            raise serializers.ValidationError("Must include email and password")

        email = email.lower()

        if email and password:
            try:
                user = User.objects.get(email=email)

                if not user.is_active:
                    raise serializers.ValidationError("Account is disabled")

                authenticated_user = authenticate(request=self.context.get("request"), email=email, password=password)

                if not authenticated_user:
                    raise serializers.ValidationError("Invalid credentials")

            except User.DoesNotExist:
                raise serializers.ValidationError("Invalid credentials")

        else:
            raise serializers.ValidationError("Must include email and password")

        attrs["user"] = user
        return attrs


class UserProfileSerializer(serializers.ModelSerializer):
    company = CompanySerializer(read_only=True)
    full_name = serializers.CharField(read_only=True)
    timezone = serializers.CharField()
    date_joined = serializers.DateTimeField(read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "role",
            "timezone",
            "company",
            "created_at",
            "updated_at",
            "date_joined",
            "is_active",
        ]
        read_only_fields = ["id", "email", "created_at", "updated_at"]


class UserUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "timezone"]

    def validate_first_name(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("First name cannot be empty")
        return value

    def validate_last_name(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("Last name cannot be empty")
        return value

    def update(self, instance, validated_data):
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance


class PasswordChangeSerializer(serializers.Serializer):
    old_password = serializers.CharField(
        write_only=True, help_text="Current password for verification", style={"input_type": "password"}
    )
    new_password = serializers.CharField(
        write_only=True,
        validators=[validate_password],
        help_text="New password (must be at least 8 characters long)",
        style={"input_type": "password"},
    )
    new_password_confirm = serializers.CharField(
        write_only=True,
        required=False,
        help_text="Confirm new password (optional but recommended)",
        style={"input_type": "password"},
    )

    def validate_old_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Old password is incorrect")
        return value

    def validate(self, attrs):
        # Only validate password confirmation if it's provided
        new_password_confirm = attrs.get("new_password_confirm")
        if new_password_confirm is not None:
            if attrs["new_password"] != new_password_confirm:
                raise serializers.ValidationError("New passwords don't match")
        return attrs

    def save(self):
        user = self.context["request"].user
        user.set_password(self.validated_data["new_password"])
        user.save()
        return user


class UserSessionSerializer(serializers.ModelSerializer):
    user = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = UserSession
        fields = ["id", "user", "created_at", "expires_at", "user_agent", "ip_address"]
        read_only_fields = fields


class SupervisedUserSerializer(serializers.ModelSerializer):
    user = UserProfileSerializer(read_only=True)
    supervisor = UserProfileSerializer(read_only=True)

    class Meta:
        model = SupervisedUser
        fields = ["id", "user", "supervisor", "monitoring_enabled", "agent_last_heartbeat", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at", "agent_last_heartbeat"]


class TokenVerificationSerializer(serializers.Serializer):
    """Serializer for token verification requests"""

    token = serializers.CharField(help_text="JWT access token to verify", required=True)


class LogoutSerializer(serializers.Serializer):
    """Serializer for logout requests"""

    refresh_token = serializers.CharField(required=False, help_text="JWT refresh token to blacklist")
    session_token = serializers.CharField(required=False, help_text="Session token to terminate")


class TokenRefreshRequestSerializer(serializers.Serializer):
    """Serializer for token refresh requests"""

    refresh = serializers.CharField(help_text="JWT refresh token", required=True)


class SessionTerminationSerializer(serializers.Serializer):
    """Serializer for session termination requests"""

    session_id = serializers.UUIDField(
        required=False, help_text="Specific session ID to terminate. If not provided, all sessions will be terminated."
    )


class AuthResponseSerializer(serializers.Serializer):
    """Response serializer for authentication endpoints"""

    message = serializers.CharField()
    user = UserProfileSerializer()
    tokens = serializers.DictField(child=serializers.CharField())
    session_token = serializers.CharField()


class LogoutResponseSerializer(serializers.Serializer):
    """Response serializer for logout endpoint"""

    message = serializers.CharField()


class TokenRefreshResponseSerializer(serializers.Serializer):
    """Response serializer for token refresh endpoint"""

    access = serializers.CharField()
    message = serializers.CharField()


class TokenVerificationResponseSerializer(serializers.Serializer):
    """Response serializer for token verification endpoint"""

    valid = serializers.BooleanField()
    user_id = serializers.CharField(required=False)
    email = serializers.CharField(required=False)
    role = serializers.CharField(required=False)
    company_id = serializers.CharField(required=False, allow_null=True)
    error = serializers.CharField(required=False)


class PasswordChangeResponseSerializer(serializers.Serializer):
    """Response serializer for password change endpoint"""

    message = serializers.CharField()


class SessionTerminationResponseSerializer(serializers.Serializer):
    """Response serializer for session termination endpoint"""

    message = serializers.CharField()


class ErrorResponseSerializer(serializers.Serializer):
    """Generic error response serializer"""

    error = serializers.CharField()


class SupervisedUserCreateSerializer(serializers.ModelSerializer):
    user_id = serializers.UUIDField(write_only=True, help_text="UUID of the user to be supervised")
    supervisor_id = serializers.UUIDField(write_only=True, help_text="UUID of the supervisor user")

    class Meta:
        model = SupervisedUser
        fields = ["user_id", "supervisor_id", "monitoring_enabled"]

    def validate(self, attrs):
        user_id = attrs.get("user_id")
        supervisor_id = attrs.get("supervisor_id")

        if user_id == supervisor_id:
            raise serializers.ValidationError("A user cannot supervise themselves")

        try:
            user = User.objects.get(id=user_id)
            supervisor = User.objects.get(id=supervisor_id)
        except User.DoesNotExist:
            raise serializers.ValidationError("Invalid user or supervisor")

        if supervisor.role not in ["admin", "supervisor"]:
            raise serializers.ValidationError("Supervisor must have admin or supervisor role")

        # Check if relationship already exists
        if SupervisedUser.objects.filter(user=user, supervisor=supervisor).exists():
            raise serializers.ValidationError("This supervision relationship already exists")

        attrs["user"] = user
        attrs["supervisor"] = supervisor
        return attrs

    def create(self, validated_data):
        validated_data.pop("user_id")
        validated_data.pop("supervisor_id")
        return super().create(validated_data)
