"""
Tiện ích cho test: tạo cặp khóa RSA tạm trong bộ nhớ và ký JWT giống Identity Service,
để test chạy được mà không cần bật Identity Service.
"""
import time
import uuid

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.test import override_settings
from rest_framework.test import APITestCase

_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
TEST_PRIVATE_KEY = _key.private_bytes(
    serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
)
TEST_PUBLIC_KEY = _key.public_key().public_bytes(
    serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
)


def make_token(user_id=1, role="ADMIN", student_id=None, username="tester", full_name="Người thử",
               expires_in=900, token_type="access", issuer="identity-service", key=TEST_PRIVATE_KEY):
    now = int(time.time())
    payload = {
        "iss": issuer,
        "sub": f"service:{username}" if role == "SERVICE" else str(user_id),
        "username": username,
        "full_name": full_name,
        "role": role,
        "student_id": student_id,
        "type": token_type,
        "jti": uuid.uuid4().hex,
        "iat": now,
        "exp": now + expires_in,
    }
    return jwt.encode(payload, key, algorithm="RS256")


def bearer(**kwargs):
    return f"Bearer {make_token(**kwargs)}"


@override_settings(JWT_PUBLIC_KEY=TEST_PUBLIC_KEY)
class AuthenticatedAPITestCase(APITestCase):
    """APITestCase đã gắn sẵn access token hợp lệ (mặc định role ADMIN)."""

    token_kwargs = {}

    def setUp(self):
        super().setUp()
        self.client.credentials(HTTP_AUTHORIZATION=bearer(**self.token_kwargs))

    def login_as(self, role, user_id=1, student_id=None, **kwargs):
        """Đổi người gọi API, ví dụ: self.login_as("STUDENT", user_id=5, student_id=1)."""
        self.client.credentials(
            HTTP_AUTHORIZATION=bearer(role=role, user_id=user_id, student_id=student_id, **kwargs)
        )
