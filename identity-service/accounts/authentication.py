"""
Xác thực request tới Identity Service bằng access token (header: Authorization: Bearer <token>).

Khác với 3 service còn lại (chỉ kiểm tra chữ ký), Identity Service còn tra lại
tài khoản trong auth_db: tài khoản bị vô hiệu hóa sẽ bị chặn ngay lập tức.
"""
import jwt
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from rest_framework import exceptions
from rest_framework.authentication import BaseAuthentication, get_authorization_header

from . import tokens
from .models import RevokedAccessToken, User


def get_bearer_token(request):
    header = get_authorization_header(request).split()
    if not header or header[0].lower() != b"bearer":
        return None
    if len(header) != 2:
        raise exceptions.AuthenticationFailed(
            "Invalid Authorization header. Use: Bearer <token>", code="bad_authorization_header"
        )
    return header[1].decode("utf-8", errors="ignore")


def decode_access_token(raw_token):
    try:
        return tokens.decode(raw_token, tokens.ACCESS)
    except jwt.ExpiredSignatureError:
        raise exceptions.AuthenticationFailed("Token has expired.", code="token_expired")
    except jwt.InvalidTokenError:
        raise exceptions.AuthenticationFailed("Invalid token.", code="token_invalid")


class JWTAuthentication(BaseAuthentication):
    def authenticate(self, request):
        raw_token = get_bearer_token(request)
        if raw_token is None:
            return None
        payload = decode_access_token(raw_token)
        if payload.get("role") == "SERVICE":
            raise exceptions.AuthenticationFailed(
                "Service tokens are not accepted here.", code="token_invalid"
            )
        if RevokedAccessToken.objects.filter(pk=payload["jti"]).exists():
            raise exceptions.AuthenticationFailed("Token has been revoked.", code="token_revoked")
        user = User.objects.filter(pk=payload["sub"]).first()
        if user is None or not user.is_active:
            raise exceptions.AuthenticationFailed("User is inactive or deleted.", code="user_inactive")
        if payload.get("token_version", 0) != user.token_version:
            raise exceptions.AuthenticationFailed("Credentials have changed. Please sign in again.", code="token_revoked")
        return user, raw_token

    def authenticate_header(self, request):
        # Có header này thì DRF trả 401 (thay vì 403) khi chưa đăng nhập
        return 'Bearer realm="api"'


class JWTAuthenticationScheme(OpenApiAuthenticationExtension):
    """Cho Swagger hiện nút Authorize (dán access token vào)."""

    target_class = "accounts.authentication.JWTAuthentication"
    name = "BearerAuth"

    def get_security_definition(self, auto_schema):
        return {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}

