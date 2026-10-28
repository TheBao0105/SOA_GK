from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import User

# Không serializer nào đọc ra trường "password" (hash) của tài khoản.


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField(help_text="Username hoặc email")
    password = serializers.CharField(write_only=True, trim_whitespace=False, style={"input_type": "password"})


class RefreshSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField(required=False, allow_blank=True)
    all_devices = serializers.BooleanField(required=False, default=False)


class TokenPairSerializer(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField()
    token_type = serializers.CharField()
    expires_in = serializers.IntegerField()


class MeSerializer(serializers.ModelSerializer):
    """Hồ sơ của chính mình: chỉ được sửa email và họ tên (KHÔNG sửa được role)."""

    class Meta:
        model = User
        fields = [
            "id", "username", "email", "full_name", "role", "student_id",
            "is_active", "last_login", "date_joined",
        ]
        read_only_fields = [
            "id", "username", "role", "student_id", "is_active", "last_login", "date_joined",
        ]


class LoginResponseSerializer(TokenPairSerializer):
    user = MeSerializer()


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True, trim_whitespace=False)
    new_password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate_old_password(self, value):
        if not self.context["request"].user.check_password(value):
            raise serializers.ValidationError("Old password is incorrect.")
        return value

    def validate(self, attrs):
        if attrs["old_password"] == attrs["new_password"]:
            raise serializers.ValidationError(
                {"new_password": ["New password must be different from the old password."]}
            )
        try:
            validate_password(attrs["new_password"], self.context["request"].user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"new_password": list(exc.messages)})
        return attrs


class UserAdminSerializer(serializers.ModelSerializer):
    """Dùng cho Admin quản lý tài khoản. password chỉ ghi, không bao giờ đọc ra."""

    password = serializers.CharField(
        write_only=True, required=False, trim_whitespace=False, style={"input_type": "password"}
    )

    class Meta:
        model = User
        fields = [
            "id", "username", "email", "full_name", "role", "student_id", "is_active",
            "locked_until", "failed_login_count", "last_login", "date_joined", "password",
        ]
        read_only_fields = ["id", "locked_until", "failed_login_count", "last_login", "date_joined"]

    def validate(self, attrs):
        request = self.context["request"]
        instance = self.instance

        if instance is None and not attrs.get("password"):
            raise serializers.ValidationError({"password": ["This field is required."]})

        if attrs.get("password"):
            candidate = instance or User(
                username=attrs.get("username", ""), email=attrs.get("email", "")
            )
            try:
                validate_password(attrs["password"], candidate)
            except DjangoValidationError as exc:
                raise serializers.ValidationError({"password": list(exc.messages)})

        role = attrs.get("role", instance.role if instance else User.Role.STUDENT)
        student_id = attrs.get("student_id", instance.student_id if instance else None)
        if role != User.Role.STUDENT and student_id is not None:
            raise serializers.ValidationError({"student_id": ["Only STUDENT accounts can have student_id."]})
        if student_id is not None:
            clash = User.objects.filter(student_id=student_id)
            if instance is not None:
                clash = clash.exclude(pk=instance.pk)
            if clash.exists():
                raise serializers.ValidationError(
                    {"student_id": ["This student is already linked to another account."]}
                )

        # Admin không được tự hạ quyền / tự khóa chính mình (tránh mất quyền quản trị)
        if instance is not None and instance.pk == request.user.pk:
            if attrs.get("role", instance.role) != User.Role.ADMIN:
                raise serializers.ValidationError({"role": ["You cannot change your own role."]})
            if attrs.get("is_active", True) is False:
                raise serializers.ValidationError({"is_active": ["You cannot deactivate your own account."]})
        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        for key, value in validated_data.items():
            setattr(instance, key, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance


class AuditLogSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    created_at = serializers.DateTimeField()
    action = serializers.CharField()
    actor_id = serializers.IntegerField(allow_null=True)
    target_id = serializers.IntegerField(allow_null=True)
    username = serializers.CharField()
    ip_address = serializers.CharField()
    detail = serializers.CharField()
