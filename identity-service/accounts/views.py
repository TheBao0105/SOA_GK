"""
API của Identity Service.

    POST /api/auth/login/            đăng nhập bằng username hoặc email -> access + refresh
    POST /api/auth/refresh/          đổi refresh token lấy cặp token mới (refresh cũ bị thu hồi)
    POST /api/auth/logout/           thu hồi refresh token (đăng xuất)
    POST /api/auth/change-password/  đổi mật khẩu (thu hồi mọi refresh token cũ)
    GET/PATCH /api/auth/me/          xem / sửa hồ sơ của chính mình
    /api/users/...                   quản lý tài khoản (chỉ ADMIN)
    GET /api/audit-logs/             nhật ký đăng nhập / quản trị (chỉ ADMIN)
"""
import logging
from datetime import datetime, timedelta, timezone as dt_timezone

import jwt
from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.db.models import Q
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import generics, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from . import tokens
from .models import AuditLog, RefreshToken, RevokedAccessToken, User
from .permissions import IsAdminRole
from .serializers import (
    AuditLogSerializer,
    ChangePasswordSerializer,
    LoginResponseSerializer,
    LoginSerializer,
    LogoutSerializer,
    MeSerializer,
    RefreshSerializer,
    TokenPairSerializer,
    UserAdminSerializer,
)

logger = logging.getLogger("accounts")

ErrorSerializer = inline_serializer(
    name="AuthError", fields={"detail": serializers.CharField(), "code": serializers.CharField()}
)


def auth_error(detail, code, http_status=status.HTTP_401_UNAUTHORIZED, **extra):
    return Response({"detail": detail, "code": code, **extra}, status=http_status)


def client_ip(request):
    return request.META.get("REMOTE_ADDR", "")[:45]


def audit(action, request, *, user=None, actor=None, username="", detail=""):
    """Ghi nhật ký. Tuyệt đối không ghi mật khẩu hay token."""
    AuditLog.objects.create(
        action=action,
        actor_id=getattr(actor, "pk", None),
        target_id=getattr(user, "pk", None),
        username=(username or getattr(user, "username", ""))[:150],
        ip_address=client_ip(request),
        detail=detail[:255],
    )


def revoke_all_refresh_tokens(user):
    RefreshToken.objects.filter(user=user, revoked_at__isnull=True).update(revoked_at=timezone.now())


# ---------------------------------------------------------------- Đăng nhập
class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    @extend_schema(
        summary="Đăng nhập (username hoặc email + mật khẩu)",
        request=LoginSerializer,
        responses={200: LoginResponseSerializer, 401: ErrorSerializer, 403: ErrorSerializer},
    )
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        identifier = serializer.validated_data["username"].strip()
        password = serializer.validated_data["password"]

        lookup = Q(email__iexact=identifier) if "@" in identifier else Q(username=identifier)

        with transaction.atomic():
            # Khóa dòng tài khoản để đếm số lần sai chính xác khi có nhiều request cùng lúc
            user = User.objects.select_for_update().filter(lookup).first()

            if user is None:
                User().set_password(password)  # tốn thời gian như khi có tài khoản -> khó dò username
                # Không ghi lại chuỗi người dùng gõ: có khi họ gõ nhầm mật khẩu vào ô username
                audit(AuditLog.Action.LOGIN_FAILED, request, detail="unknown user")
                return auth_error("Invalid username or password.", "invalid_credentials")

            if user.is_locked:
                return auth_error(
                    "Account is temporarily locked because of too many failed logins.",
                    "account_locked",
                    status.HTTP_403_FORBIDDEN,
                    locked_until=user.locked_until.isoformat(),
                )

            if not user.check_password(password):
                user.failed_login_count += 1
                if user.failed_login_count >= settings.MAX_FAILED_LOGINS:
                    user.failed_login_count = 0
                    user.locked_until = timezone.now() + timedelta(minutes=settings.LOCKOUT_MINUTES)
                    user.save(update_fields=["failed_login_count", "locked_until"])
                    audit(AuditLog.Action.ACCOUNT_LOCKED, request, user=user)
                    logger.warning("Account %s locked after too many failed logins", user.username)
                    return auth_error(
                        "Account is temporarily locked because of too many failed logins.",
                        "account_locked",
                        status.HTTP_403_FORBIDDEN,
                        locked_until=user.locked_until.isoformat(),
                    )
                user.save(update_fields=["failed_login_count"])
                audit(AuditLog.Action.LOGIN_FAILED, request, user=user)
                return auth_error("Invalid username or password.", "invalid_credentials")

            # Mật khẩu đúng: chỉ khi đó mới cho biết tài khoản bị vô hiệu hóa
            if not user.is_active:
                return auth_error("Account is disabled.", "account_disabled", status.HTTP_403_FORBIDDEN)

            user.failed_login_count = 0
            user.locked_until = None
            user.last_login = timezone.now()
            user.save(update_fields=["failed_login_count", "locked_until", "last_login"])
            pair = tokens.create_token_pair(user)
            audit(AuditLog.Action.LOGIN_SUCCESS, request, user=user)

        return Response({**pair, "user": MeSerializer(user).data})


# ---------------------------------------------------------------- Làm mới token
class RefreshView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "refresh"

    @extend_schema(
        summary="Lấy access token mới bằng refresh token",
        request=RefreshSerializer,
        responses={200: TokenPairSerializer, 401: ErrorSerializer, 403: ErrorSerializer},
    )
    def post(self, request):
        serializer = RefreshSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            payload = tokens.decode(serializer.validated_data["refresh"], tokens.REFRESH)
        except jwt.ExpiredSignatureError:
            return auth_error("Refresh token has expired.", "token_expired")
        except jwt.InvalidTokenError:
            return auth_error("Invalid refresh token.", "token_invalid")

        with transaction.atomic():
            record = (
                RefreshToken.objects.select_for_update()
                .select_related("user")
                .filter(jti=payload["jti"])
                .first()
            )
            if record is None:
                return auth_error("Refresh token is not recognised.", "token_invalid")
            user = record.user
            if record.revoked_at is not None:
                # Token đã bị thu hồi mà vẫn được dùng lại -> có thể bị đánh cắp:
                # thu hồi toàn bộ phiên của tài khoản này.
                revoke_all_refresh_tokens(user)
                audit(AuditLog.Action.TOKEN_REUSE, request, user=user)
                logger.warning("Revoked refresh token reused for user %s", user.username)
                return auth_error("Refresh token has been revoked.", "token_revoked")
            if not user.is_active:
                return auth_error("Account is disabled.", "account_disabled", status.HTTP_403_FORBIDDEN)
            if user.is_locked:
                return auth_error("Account is temporarily locked.", "account_locked", status.HTTP_403_FORBIDDEN)

            record.revoked_at = timezone.now()
            record.save(update_fields=["revoked_at"])
            pair = tokens.create_token_pair(user)
        return Response(pair)


# ---------------------------------------------------------------- Đăng xuất
class LogoutView(APIView):
    @extend_schema(
        summary="Đăng xuất: thu hồi access/refresh token (all_devices=true để thu hồi mọi phiên)",
        request=LogoutSerializer,
        responses={200: inline_serializer("LogoutResponse", {"detail": serializers.CharField()})},
    )
    @transaction.atomic
    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if serializer.validated_data.get("refresh"):
            try:
                tokens.decode(serializer.validated_data["refresh"], tokens.REFRESH, verify_exp=False)
            except jwt.InvalidTokenError:
                return auth_error("Invalid refresh token.", "token_invalid", status.HTTP_400_BAD_REQUEST)
        access_payload = tokens.decode(request.auth, tokens.ACCESS, verify_exp=False)
        RevokedAccessToken.objects.get_or_create(
            jti=access_payload["jti"],
            defaults={"expires_at": datetime.fromtimestamp(access_payload["exp"], tz=dt_timezone.utc)},
        )
        if serializer.validated_data["all_devices"]:
            User.objects.filter(pk=request.user.pk).update(token_version=F("token_version") + 1)
            revoke_all_refresh_tokens(request.user)
        elif serializer.validated_data.get("refresh"):
            try:
                payload = tokens.decode(
                    serializer.validated_data["refresh"], tokens.REFRESH, verify_exp=False
                )
            except jwt.InvalidTokenError:
                return auth_error("Invalid refresh token.", "token_invalid", status.HTTP_400_BAD_REQUEST)
            RefreshToken.objects.filter(
                jti=payload["jti"], user=request.user, revoked_at__isnull=True
            ).update(revoked_at=timezone.now())
        audit(AuditLog.Action.LOGOUT, request, user=request.user)
        return Response({"detail": "Logged out."})


# ---------------------------------------------------------------- Đổi mật khẩu
class ChangePasswordView(APIView):
    @extend_schema(
        summary="Đổi mật khẩu (mọi phiên cũ bị thu hồi, trả về cặp token mới)",
        request=ChangePasswordSerializer,
        responses={200: TokenPairSerializer},
    )
    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = request.user
        with transaction.atomic():
            user.set_password(serializer.validated_data["new_password"])
            User.objects.filter(pk=user.pk).update(token_version=F("token_version") + 1)
            user.refresh_from_db(fields=["token_version"])
            user.save(update_fields=["password"])
            revoke_all_refresh_tokens(user)
            pair = tokens.create_token_pair(user)
        audit(AuditLog.Action.PASSWORD_CHANGED, request, user=user, actor=user)
        return Response(pair)


# ---------------------------------------------------------------- Hồ sơ của tôi
@extend_schema(summary="Hồ sơ tài khoản đang đăng nhập")
class MeView(generics.RetrieveUpdateAPIView):
    serializer_class = MeSerializer
    http_method_names = ["get", "patch", "head", "options"]

    def get_object(self):
        return self.request.user


# ---------------------------------------------------------------- Quản lý tài khoản (ADMIN)
@extend_schema(
    parameters=[
        OpenApiParameter("role", str, enum=[r.value for r in User.Role], description="Lọc theo vai trò"),
        OpenApiParameter("search", str, description="Tìm theo username / email / họ tên"),
    ]
)
class UserViewSet(viewsets.ModelViewSet):
    """CRUD tài khoản - chỉ ADMIN. Mật khẩu chỉ ghi, không bao giờ trả về."""

    serializer_class = UserAdminSerializer
    permission_classes = [IsAuthenticated, IsAdminRole]

    def get_queryset(self):
        queryset = User.objects.all()
        role = self.request.query_params.get("role")
        if role:
            queryset = queryset.filter(role=role.upper())
        search = self.request.query_params.get("search", "").strip()
        if search:
            queryset = queryset.filter(
                Q(username__icontains=search) | Q(email__icontains=search) | Q(full_name__icontains=search)
            )
        return queryset

    def perform_create(self, serializer):
        user = serializer.save()
        audit(AuditLog.Action.USER_CREATED, self.request, user=user, actor=self.request.user)

    @transaction.atomic
    def perform_update(self, serializer):
        password_changed = bool(serializer.validated_data.get("password"))
        deactivated = serializer.validated_data.get("is_active") is False
        role_changed = (
            "role" in serializer.validated_data
            and serializer.validated_data["role"] != serializer.instance.role
        )
        mapping_changed = ("student_id" in serializer.validated_data and serializer.validated_data["student_id"] != serializer.instance.student_id)
        user = serializer.save()
        # Đổi mật khẩu / khóa / đổi vai trò -> buộc đăng nhập lại
        if password_changed or deactivated or role_changed or mapping_changed:
            User.objects.filter(pk=user.pk).update(token_version=F("token_version") + 1)
            user.refresh_from_db(fields=["token_version"])
            revoke_all_refresh_tokens(user)
        audit(
            AuditLog.Action.USER_UPDATED, self.request, user=user, actor=self.request.user,
            detail=",".join(sorted(k for k in serializer.validated_data if k != "password"))
            + (",password" if password_changed else ""),
        )

    def destroy(self, request, *args, **kwargs):
        user = self.get_object()
        if user.pk == request.user.pk:
            return Response(
                {"detail": "You cannot delete your own account."}, status=status.HTTP_400_BAD_REQUEST
            )
        audit(AuditLog.Action.USER_DELETED, request, user=user, actor=request.user)
        return super().destroy(request, *args, **kwargs)

    @extend_schema(summary="Mở khóa tài khoản bị khóa tạm do đăng nhập sai", request=None)
    @action(detail=True, methods=["post"])
    def unlock(self, request, pk=None):
        user = self.get_object()
        user.locked_until = None
        user.failed_login_count = 0
        user.save(update_fields=["locked_until", "failed_login_count"])
        audit(AuditLog.Action.USER_UNLOCKED, request, user=user, actor=request.user)
        return Response(self.get_serializer(user).data)


@extend_schema(summary="Nhật ký đăng nhập / quản trị tài khoản (chỉ ADMIN)", responses=AuditLogSerializer(many=True))
class AuditLogListView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    def get(self, request):
        logs = AuditLog.objects.all()[:200]
        return Response(AuditLogSerializer(logs, many=True).data)
