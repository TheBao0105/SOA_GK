"""
Test Identity Service: đăng nhập, khóa tài khoản, refresh/đăng xuất, đổi mật khẩu,
phân quyền API quản trị tài khoản.

Khóa RSA được tạo tạm trong bộ nhớ khi chạy test (không đụng tới thư mục keys/).
"""
import tempfile
from datetime import timedelta
from io import StringIO
from pathlib import Path

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.core.cache import cache
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from . import tokens
from .models import AuditLog, RefreshToken, User

_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
TEST_PRIVATE_KEY = _key.private_bytes(
    serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
)
TEST_PUBLIC_KEY = _key.public_key().public_bytes(
    serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
)

PASSWORD = "Str0ng-Pass!2026"


@override_settings(
    JWT_PRIVATE_KEY=TEST_PRIVATE_KEY,
    JWT_PUBLIC_KEY=TEST_PUBLIC_KEY,
    MAX_FAILED_LOGINS=5,
    LOCKOUT_MINUTES=15,
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],  # chỉ cho test chạy nhanh
)
class IdentityTestCase(APITestCase):
    def setUp(self):
        cache.clear()  # reset bộ đếm throttle giữa các test
        self.admin = self.make_user("admin", User.Role.ADMIN)
        self.lecturer = self.make_user("gv01", User.Role.LECTURER)
        self.student = self.make_user("sv001", User.Role.STUDENT, student_id=1)

    def make_user(self, username, role, **extra):
        user = User(username=username, email=f"{username}@qnu.edu.vn", role=role, **extra)
        user.set_password(PASSWORD)
        user.save()
        return user

    def login(self, username, password=PASSWORD):
        return self.client.post("/api/auth/login/", {"username": username, "password": password}, format="json")

    def auth(self, user):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens.create_access_token(user)}")


class LoginTests(IdentityTestCase):
    def test_login_with_username(self):
        response = self.login("sv001")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["token_type"], "Bearer")
        self.assertEqual(response.data["user"]["role"], "STUDENT")
        self.assertEqual(response.data["user"]["student_id"], 1)

        payload = tokens.decode(response.data["access"], tokens.ACCESS)
        self.assertEqual(payload["sub"], str(self.student.pk))
        self.assertEqual(payload["role"], "STUDENT")
        self.assertEqual(payload["student_id"], 1)
        self.assertEqual(payload["full_name"], "sv001")  # chưa có họ tên -> dùng username
        self.assertEqual(RefreshToken.objects.filter(user=self.student).count(), 1)

    def test_login_with_email_case_insensitive(self):
        response = self.login("SV001@QNU.EDU.VN")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_response_and_token_do_not_contain_password(self):
        response = self.login("sv001")
        self.assertNotIn("password", response.data["user"])
        self.assertNotIn(PASSWORD, response.content.decode())
        payload = jwt.decode(response.data["access"], options={"verify_signature": False})
        self.assertNotIn("password", payload)

    def test_wrong_password_returns_401_and_counts(self):
        response = self.login("sv001", "wrong-password")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data["code"], "invalid_credentials")
        self.student.refresh_from_db()
        self.assertEqual(self.student.failed_login_count, 1)

    def test_unknown_user_returns_same_error(self):
        response = self.login("khong-ton-tai")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data["code"], "invalid_credentials")

    def test_account_locked_after_too_many_failures(self):
        for _ in range(4):
            self.assertEqual(self.login("sv001", "wrong").status_code, 401)
        response = self.login("sv001", "wrong")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["code"], "account_locked")

        # Đúng mật khẩu nhưng vẫn đang bị khóa
        response = self.login("sv001")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["code"], "account_locked")
        self.assertTrue(AuditLog.objects.filter(action=AuditLog.Action.ACCOUNT_LOCKED).exists())

    def test_lock_expires(self):
        self.student.locked_until = timezone.now() - timedelta(seconds=1)
        self.student.save()
        self.assertEqual(self.login("sv001").status_code, status.HTTP_200_OK)

    def test_successful_login_resets_counter(self):
        self.login("sv001", "wrong")
        self.login("sv001")
        self.student.refresh_from_db()
        self.assertEqual(self.student.failed_login_count, 0)

    def test_disabled_account(self):
        self.student.is_active = False
        self.student.save()
        response = self.login("sv001")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["code"], "account_disabled")
        # Sai mật khẩu thì không tiết lộ tài khoản bị vô hiệu hóa
        self.assertEqual(self.login("sv001", "wrong").data["code"], "invalid_credentials")

    def test_login_requires_fields(self):
        response = self.client.post("/api/auth/login/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class TokenTests(IdentityTestCase):
    def test_me_requires_token(self):
        response = self.client.get("/api/auth/me/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_me_with_token(self):
        self.auth(self.student)
        response = self.client.get("/api/auth/me/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["username"], "sv001")

    def test_expired_access_token(self):
        token = tokens.create_access_token(self.student, lifetime=timedelta(seconds=-60))
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        response = self.client.get("/api/auth/me/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data["code"], "token_expired")

    def test_tampered_token(self):
        token = tokens.create_access_token(self.student)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token[:-4]}abcd")
        response = self.client.get("/api/auth/me/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data["code"], "token_invalid")

    def test_token_signed_with_other_key_is_rejected(self):
        other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        fake = jwt.encode(
            {"sub": str(self.admin.pk), "role": "ADMIN", "type": "access", "iss": "identity-service",
             "iat": int(timezone.now().timestamp()), "exp": int(timezone.now().timestamp()) + 600, "jti": "x"},
            other, algorithm="RS256",
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {fake}")
        self.assertEqual(self.client.get("/api/auth/me/").status_code, status.HTTP_401_UNAUTHORIZED)

    def test_refresh_token_cannot_be_used_as_access_token(self):
        refresh = self.login("sv001").data["refresh"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh}")
        self.assertEqual(self.client.get("/api/auth/me/").status_code, status.HTTP_401_UNAUTHORIZED)

    def test_disabled_user_token_rejected_immediately(self):
        self.auth(self.student)
        self.student.is_active = False
        self.student.save()
        response = self.client.get("/api/auth/me/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_refresh_rotates_token(self):
        refresh = self.login("sv001").data["refresh"]
        response = self.client.post("/api/auth/refresh/", {"refresh": refresh}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertNotEqual(response.data["refresh"], refresh)

    def test_reused_refresh_token_revokes_all_sessions(self):
        refresh = self.login("sv001").data["refresh"]
        new_refresh = self.client.post("/api/auth/refresh/", {"refresh": refresh}, format="json").data["refresh"]
        # Dùng lại token cũ -> bị từ chối và mọi phiên bị thu hồi
        response = self.client.post("/api/auth/refresh/", {"refresh": refresh}, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data["code"], "token_revoked")
        response = self.client.post("/api/auth/refresh/", {"refresh": new_refresh}, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_expired_refresh_token(self):
        token = tokens.create_refresh_token(self.student, lifetime=timedelta(seconds=-60))
        response = self.client.post("/api/auth/refresh/", {"refresh": token}, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data["code"], "token_expired")

    def test_refresh_for_disabled_account(self):
        refresh = self.login("sv001").data["refresh"]
        self.student.is_active = False
        self.student.save()
        response = self.client.post("/api/auth/refresh/", {"refresh": refresh}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_logout_revokes_refresh_token(self):
        data = self.login("sv001").data
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {data['access']}")
        response = self.client.post("/api/auth/logout/", {"refresh": data["refresh"]}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.client.credentials()
        response = self.client.post("/api/auth/refresh/", {"refresh": data["refresh"]}, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_service_token_not_accepted_by_identity(self):
        token = tokens.create_service_token("registration-service", timedelta(minutes=5))
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(self.client.get("/api/auth/me/").status_code, status.HTTP_401_UNAUTHORIZED)


class ProfileAndPasswordTests(IdentityTestCase):
    def test_user_cannot_change_own_role(self):
        self.auth(self.student)
        response = self.client.patch("/api/auth/me/", {"role": "ADMIN", "full_name": "An"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.student.refresh_from_db()
        self.assertEqual(self.student.role, User.Role.STUDENT)
        self.assertEqual(self.student.full_name, "An")

    def test_change_password_wrong_old(self):
        self.auth(self.student)
        response = self.client.post(
            "/api/auth/change-password/", {"old_password": "sai", "new_password": "N3w-Pass!2026"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("old_password", response.data)

    def test_change_password_weak_new(self):
        self.auth(self.student)
        response = self.client.post(
            "/api/auth/change-password/", {"old_password": PASSWORD, "new_password": "123"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("new_password", response.data)

    def test_change_password_success_revokes_old_sessions(self):
        old_refresh = self.login("sv001").data["refresh"]
        self.auth(self.student)
        response = self.client.post(
            "/api/auth/change-password/", {"old_password": PASSWORD, "new_password": "N3w-Pass!2026"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.client.credentials()
        self.assertEqual(
            self.client.post("/api/auth/refresh/", {"refresh": old_refresh}, format="json").status_code, 401
        )
        self.assertEqual(self.login("sv001", "N3w-Pass!2026").status_code, 200)
        self.assertEqual(self.login("sv001", PASSWORD).status_code, 401)


class UserAdminTests(IdentityTestCase):
    url = "/api/users/"

    def test_requires_authentication(self):
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_student_and_lecturer_cannot_manage_accounts(self):
        for user in (self.student, self.lecturer):
            self.auth(user)
            self.assertEqual(self.client.get(self.url).status_code, status.HTTP_403_FORBIDDEN)
            response = self.client.patch(f"{self.url}{user.pk}/", {"role": "ADMIN"}, format="json")
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.student.refresh_from_db()
        self.assertEqual(self.student.role, User.Role.STUDENT)

    def test_admin_lists_users_without_password(self):
        self.auth(self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 3)
        self.assertTrue(all("password" not in u for u in response.data))
        self.assertEqual(len(self.client.get(self.url, {"role": "student"}).data), 1)

    def test_admin_creates_user_with_hashed_password(self):
        self.auth(self.admin)
        response = self.client.post(self.url, {
            "username": "sv002", "email": "sv002@qnu.edu.vn", "role": "STUDENT",
            "student_id": 2, "password": "Mua-Thu!2026x",
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertNotIn("password", response.data)
        user = User.objects.get(username="sv002")
        self.assertNotEqual(user.password, "Mua-Thu!2026x")
        self.assertTrue(user.check_password("Mua-Thu!2026x"))

    def test_create_user_validation(self):
        self.auth(self.admin)
        response = self.client.post(self.url, {"username": "x", "email": "x@qnu.edu.vn"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password", response.data)
        response = self.client.post(self.url, {
            "username": "gv02", "email": "gv02@qnu.edu.vn", "role": "LECTURER",
            "student_id": 5, "password": "Mua-Thu!2026x",
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("student_id", response.data)
        response = self.client.post(self.url, {
            "username": "sv009", "email": "sv009@qnu.edu.vn", "role": "STUDENT",
            "student_id": 1, "password": "Mua-Thu!2026x",
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)  # student_id 1 đã có tài khoản

    def test_admin_cannot_demote_or_disable_self(self):
        self.auth(self.admin)
        url = f"{self.url}{self.admin.pk}/"
        self.assertEqual(self.client.patch(url, {"role": "STUDENT"}, format="json").status_code, 400)
        self.assertEqual(self.client.patch(url, {"is_active": False}, format="json").status_code, 400)
        self.assertEqual(self.client.delete(url).status_code, 400)

    def test_admin_disables_user_and_sessions_are_revoked(self):
        refresh = self.login("sv001").data["refresh"]
        self.auth(self.admin)
        response = self.client.patch(f"{self.url}{self.student.pk}/", {"is_active": False}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.client.credentials()
        self.assertEqual(
            self.client.post("/api/auth/refresh/", {"refresh": refresh}, format="json").status_code, 401
        )

    def test_admin_unlocks_user(self):
        self.student.locked_until = timezone.now() + timedelta(minutes=10)
        self.student.save()
        self.auth(self.admin)
        response = self.client.post(f"{self.url}{self.student.pk}/unlock/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.login("sv001").status_code, 200)

    def test_audit_log_admin_only(self):
        self.login("sv001")
        self.auth(self.student)
        self.assertEqual(self.client.get("/api/audit-logs/").status_code, 403)
        self.auth(self.admin)
        response = self.client.get("/api/audit-logs/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data[0]["action"], "LOGIN_SUCCESS")


class CommandTests(IdentityTestCase):
    def test_generate_jwt_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            priv, pub = Path(tmp) / "k" / "private.pem", Path(tmp) / "k" / "public.pem"
            with override_settings(JWT_PRIVATE_KEY_PATH=priv, JWT_PUBLIC_KEY_PATH=pub):
                call_command("generate_jwt_keys", stdout=StringIO())
                self.assertTrue(priv.exists() and pub.exists())
                with self.assertRaises(Exception):
                    call_command("generate_jwt_keys", stdout=StringIO())  # không ghi đè nếu thiếu --force

    def test_seed_users_is_idempotent(self):
        call_command("seed_users", stdout=StringIO())
        call_command("seed_users", stdout=StringIO())
        self.assertEqual(User.objects.filter(username="sv002", student_id=2).count(), 1)
        self.assertTrue(User.objects.get(username="admin").role == User.Role.ADMIN)

    def test_issue_service_token(self):
        out = StringIO()
        call_command("issue_service_token", "registration-service", stdout=out, stderr=StringIO())
        payload = tokens.decode(out.getvalue().strip(), tokens.ACCESS)
        self.assertEqual(payload["role"], "SERVICE")

    def test_schema_is_public(self):
        self.assertEqual(self.client.get("/api/schema/").status_code, 200)


class RevocationTests(IdentityTestCase):
    def test_old_access_token_revoked_after_password_change(self):
        token=tokens.create_access_token(self.student)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        response=self.client.post("/api/auth/change-password/",{"old_password":PASSWORD,"new_password":"New-Secure-Pass!2027"},format="json")
        self.assertEqual(response.status_code,200)
        self.assertEqual(self.client.get("/api/auth/me/").status_code,401)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")
        self.assertEqual(self.client.get("/api/auth/me/").status_code,200)

    def test_old_access_revoked_after_role_or_student_mapping_changes(self):
        for field,value in (("student_id",9),("role","LECTURER")):
            self.student.refresh_from_db()
            token=tokens.create_access_token(self.student)
            self.auth(self.admin)
            self.assertEqual(self.client.patch(f"/api/users/{self.student.pk}/",{field:value, **({"student_id":None} if field=="role" else {})},format="json").status_code,200)
            self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
            self.assertEqual(self.client.get("/api/auth/me/").status_code,401)


class LogoutRevocationTests(IdentityTestCase):
    def test_logout_revokes_current_access_but_not_other_login(self):
        first=self.login("sv001").data
        second=self.login("sv001").data
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {first['access']}")
        self.assertEqual(self.client.post("/api/auth/logout/",{"refresh":first['refresh']},format="json").status_code,200)
        self.assertEqual(self.client.get("/api/auth/me/").status_code,401)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {second['access']}")
        self.assertEqual(self.client.get("/api/auth/me/").status_code,200)

    def test_logout_all_devices_revokes_all_access_tokens(self):
        first=self.login("sv001").data
        second=self.login("sv001").data
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {first['access']}")
        self.assertEqual(self.client.post("/api/auth/logout/",{"all_devices":True},format="json").status_code,200)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {second['access']}")
        self.assertEqual(self.client.get("/api/auth/me/").status_code,401)
