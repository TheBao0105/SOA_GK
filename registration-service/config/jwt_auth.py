"""
Xác minh JWT do Identity Service (port 8004) cấp.

Service này không có bảng tài khoản. Chữ ký RS256 luôn được xác minh bằng khóa công khai.
Khi JWT_CHECK_ACCOUNT_STATE=True (mặc định production), gọi thêm Identity qua REST
để kiểm tra trạng thái/quyền và thu hồi token ngay. Nếu tắt, xác minh hoàn toàn tại chỗ.

File này giống hệt nhau ở student-service, thesis-service và registration-service.
"""
import functools
import logging

import jwt
import requests
from django.conf import settings
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from rest_framework import exceptions, status
from rest_framework.authentication import BaseAuthentication, get_authorization_header

logger = logging.getLogger(__name__)


class AuthNotConfigured(exceptions.APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "Authentication is not configured on this service (missing JWT public key)."
    default_code = "auth_not_configured"


class TokenUser:
    """
    Người dùng lấy từ JWT (không có trong database của service này).

    request.user.id, .role, .student_id dùng để phân quyền ở các giai đoạn sau.
    """

    is_authenticated = True
    is_anonymous = False
    is_active = True

    def __init__(self, payload):
        self.payload = payload
        self.role = payload.get("role")
        self.is_service = self.role == "SERVICE"
        self.id = None if self.is_service else int(payload["sub"])
        self.pk = self.id
        self.username = payload.get("username", "")
        self.full_name = payload.get("full_name") or self.username
        self.student_id = payload.get("student_id")

    def __str__(self):
        return self.username


@functools.lru_cache(maxsize=4)
def _read_key_file(path):
    with open(path, "rb") as f:
        return f.read()


def get_public_key():
    if settings.JWT_PUBLIC_KEY:  # dùng trong test
        return settings.JWT_PUBLIC_KEY
    path = str(settings.JWT_PUBLIC_KEY_PATH)
    try:
        return _read_key_file(path)
    except FileNotFoundError:
        logger.error(
            "JWT public key not found at %s. Run 'python manage.py generate_jwt_keys' in identity-service.",
            path,
        )
        raise AuthNotConfigured()


def decode_access_token(raw_token):
    try:
        payload = jwt.decode(
            raw_token,
            get_public_key(),
            algorithms=[settings.JWT_ALGORITHM],
            issuer=settings.JWT_ISSUER,
            leeway=settings.JWT_LEEWAY_SECONDS,
            options={"require": ["exp", "iat", "sub"]},
        )
    except jwt.ExpiredSignatureError:
        raise exceptions.AuthenticationFailed("Token has expired.", code="token_expired")
    except jwt.InvalidTokenError:
        raise exceptions.AuthenticationFailed("Invalid token.", code="token_invalid")

    if payload.get("type") != "access":
        raise exceptions.AuthenticationFailed("Invalid token.", code="token_invalid")
    if payload.get("role") != "SERVICE" and not str(payload.get("sub", "")).isdigit():
        raise exceptions.AuthenticationFailed("Invalid token.", code="token_invalid")
    return payload


class JWTAuthentication(BaseAuthentication):
    """Đọc header  Authorization: Bearer <access token>"""

    def authenticate(self, request):
        header = get_authorization_header(request).split()
        if not header or header[0].lower() != b"bearer":
            return None  # không gửi token -> IsAuthenticated sẽ trả 401
        if len(header) != 2:
            raise exceptions.AuthenticationFailed(
                "Invalid Authorization header. Use: Bearer <token>", code="bad_authorization_header"
            )
        raw_token = header[1].decode("utf-8", errors="ignore")
        payload = decode_access_token(raw_token)
        if settings.JWT_CHECK_ACCOUNT_STATE and payload.get("role") != "SERVICE":
            try:
                response = requests.get(
                    f"{settings.IDENTITY_SERVICE_URL}/api/auth/me/",
                    headers={"Authorization": f"Bearer {raw_token}"},
                    timeout=settings.EXTERNAL_API_TIMEOUT,
                )
            except requests.RequestException:
                raise IdentityUnavailable()
            if response.status_code in (401, 403):
                raise exceptions.AuthenticationFailed("Account or token is no longer active.", code="token_revoked")
            if response.status_code != 200:
                raise IdentityUnavailable()
            try:
                user = response.json()
                valid = (isinstance(user, dict) and str(user.get("id")) == str(payload["sub"])
                         and user.get("is_active") is True and user.get("role") == payload.get("role")
                         and user.get("student_id") == payload.get("student_id"))
            except ValueError:
                raise IdentityUnavailable()
            if not valid:
                raise exceptions.AuthenticationFailed("Account permissions have changed.", code="token_revoked")
        return TokenUser(payload), raw_token

    def authenticate_header(self, request):
        return 'Bearer realm="api"'


class JWTAuthenticationScheme(OpenApiAuthenticationExtension):
    """Cho Swagger hiện nút Authorize (dán access token lấy từ Identity Service)."""

    target_class = "config.jwt_auth.JWTAuthentication"
    name = "BearerAuth"

    def get_security_definition(self, auto_schema):
        return {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}


class IdentityUnavailable(exceptions.APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "Identity Service unavailable; account state cannot be verified."
    default_code = "identity_unavailable"
