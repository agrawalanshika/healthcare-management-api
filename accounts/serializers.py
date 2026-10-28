from django.contrib.auth.password_validation import validate_password
from django.db import IntegrityError
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import User


class RegisterSerializer(serializers.ModelSerializer):
    name = serializers.CharField(max_length=150)
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(
        write_only=True, style={"input_type": "password"}, trim_whitespace=False
    )

    class Meta:
        model = User
        fields = ("id", "name", "email", "password")
        read_only_fields = ("id",)

    def validate_email(self, value):
        email = value.strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return email

    def validate(self, attrs):
        # Run Django's configured password validators against the candidate user.
        candidate = User(email=attrs.get("email", ""), name=attrs.get("name", ""))
        try:
            validate_password(attrs["password"], user=candidate)
        except Exception as exc:  # DjangoValidationError
            messages = getattr(exc, "messages", [str(exc)])
            raise serializers.ValidationError({"password": list(messages)})
        return attrs

    def create(self, validated_data):
        try:
            # create_user hashes the password with Django's configured hasher.
            return User.objects.create_user(
                email=validated_data["email"],
                password=validated_data["password"],
                name=validated_data["name"],
            )
        except IntegrityError:
            # Race condition safety net: the database constraint rejected a duplicate.
            raise serializers.ValidationError(
                {"email": ["A user with this email already exists."]}
            )


class LoginSerializer(TokenObtainPairSerializer):
    """Authenticate with email + password and return an access token."""

    def validate(self, attrs):
        email_field = self.username_field  # "email"
        if isinstance(attrs.get(email_field), str):
            attrs[email_field] = attrs[email_field].strip().lower()
        data = super().validate(attrs)  # raises 401 on invalid credentials
        return {
            "access": data["access"],
            "user": {
                "id": self.user.id,
                "name": self.user.name,
                "email": self.user.email,
            },
        }
