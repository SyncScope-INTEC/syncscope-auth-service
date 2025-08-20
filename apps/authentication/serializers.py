from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import Company, User, UserSession


class CompanySerializer(serializers.ModelSerializer):
    class Meta:
        model = Company
        fields = ["id", "name", "domain", "created_at"]
        read_only_fields = ["id", "created_at"]

    def validate_domain(self, value):
        if not value.startswith("@"):
            value = f"@{value}"
        return value


class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True)
    company_name = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = User
        fields = ["email", "first_name", "last_name", "password", "password_confirm", "company_name", "role"]
        extra_kwargs = {"role": {"default": "developer"}}

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
    email = serializers.EmailField(required=False)
    password = serializers.CharField(write_only=True, required=False)

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
            "avatar_url",
            "is_verified",
            "created_at",
            "updated_at",
            "date_joined",
            "is_active",
        ]
        read_only_fields = ["id", "email", "is_verified", "created_at", "updated_at"]


class UserUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "avatar_url", "timezone"]

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
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, validators=[validate_password])
    new_password_confirm = serializers.CharField(write_only=True)

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
        fields = ["id", "user", "created_at", "expires_at", "is_active", "user_agent", "ip_address", "last_used"]
        read_only_fields = fields
