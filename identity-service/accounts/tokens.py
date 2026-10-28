"""
Tạo và kiểm tra JWT (RS256).

- Access token: sống ngắn (mặc định 15 phút), gửi kèm mọi request tới các service.
- Refresh token: sống dài hơn (mặc định 24 giờ), chỉ dùng để xin access token mới
  tại Identity Service. Mỗi lần làm mới sẽ cấp refresh token MỚI và thu hồi cái cũ.

Nội dung (payload) của token KHÔNG chứa mật khẩu hay dữ liệu nhạy cảm:
    iss, sub (id tài khoản), username, full_name, role, student_id, token_version, type, jti, iat, exp
"""
import functools
import uuid
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone

import jwt
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone

ACCESS = "access"
REFRESH = "refresh"


@functools.lru_cache(maxsize=4)
def _read_key_file(path):
    try:
        with open(path, "rb") as f:
            return f.read()
    except FileNotFoundError:
        raise ImproperlyConfigured(
            f"Không tìm thấy khóa JWT tại {path}. "
            "Hãy chạy: python manage.py generate_jwt_keys (trong identity-service)."
        )


def private_key():
    return settings.JWT_PRIVATE_KEY or _read_key_file(str(settings.JWT_PRIVATE_KEY_PATH))


def public_key():
    return settings.JWT_PUBLIC_KEY or _read_key_file(str(settings.JWT_PUBLIC_KEY_PATH))


def _encode(claims, lifetime):
    now = timezone.now()
    payload = {
        "iss": settings.JWT_ISSUER,
        "iat": int(now.timestamp()),
        "exp": int((now + lifetime).timestamp()),
        "jti": uuid.uuid4().hex,
        **claims,
    }
    token = jwt.encode(payload, private_key(), algorithm=settings.JWT_ALGORITHM)
    return token, payload


def user_claims(user):
    return {
        "sub": str(user.pk),
        "username": user.username,
        "full_name": user.full_name or user.username,
        "role": user.role,
        "token_version": user.token_version,
        "student_id": user.student_id,
    }


def access_lifetime():
    return timedelta(minutes=settings.ACCESS_TOKEN_LIFETIME_MINUTES)


def refresh_lifetime():
    return timedelta(hours=settings.REFRESH_TOKEN_LIFETIME_HOURS)


def create_access_token(user, lifetime=None):
    token, _ = _encode({**user_claims(user), "type": ACCESS}, lifetime or access_lifetime())
    return token


def create_refresh_token(user, lifetime=None):
    """Tạo refresh token và lưu jti vào bảng token_lammoi."""
    from .models import RefreshToken

    token, payload = _encode({**user_claims(user), "type": REFRESH}, lifetime or refresh_lifetime())
    RefreshToken.objects.create(
        jti=payload["jti"],
        user=user,
        expires_at=datetime.fromtimestamp(payload["exp"], tz=dt_timezone.utc),
    )
    return token


def create_token_pair(user):
    return {
        "access": create_access_token(user),
        "refresh": create_refresh_token(user),
        "token_type": "Bearer",
        "expires_in": int(access_lifetime().total_seconds()),
    }


def create_service_token(service_name, lifetime):
    """
    Token kỹ thuật cho service gọi service khi KHÔNG có người dùng
    (ví dụ lệnh seed_data của Registration Service).
    """
    token, _ = _encode(
        {
            "sub": f"service:{service_name}",
            "username": service_name,
            "role": "SERVICE",
            "student_id": None,
            "type": ACCESS,
        },
        lifetime,
    )
    return token


def decode(token, expected_type, verify_exp=True):
    """
    Giải mã + kiểm tra chữ ký, issuer, hạn dùng và loại token.
    Ném jwt.ExpiredSignatureError / jwt.InvalidTokenError nếu không hợp lệ.
    """
    payload = jwt.decode(
        token,
        public_key(),
        algorithms=[settings.JWT_ALGORITHM],
        issuer=settings.JWT_ISSUER,
        leeway=settings.JWT_LEEWAY_SECONDS,
        options={"require": ["exp", "iat", "sub", "jti"], "verify_exp": verify_exp},
    )
    if payload.get("type") != expected_type:
        raise jwt.InvalidTokenError(f"Expected a {expected_type} token")
    return payload
