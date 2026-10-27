from unittest.mock import MagicMock, patch

import requests
from cryptography.hazmat.primitives.asymmetric import rsa
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from config.testing import TEST_PUBLIC_KEY, AuthenticatedAPITestCase, bearer

from .models import Student


def registration_reply(items=(), status_code=200):
    """Giả lập phản hồi GET /api/registrations/?active=true của Registration Service."""
    reply = MagicMock(status_code=status_code)
    reply.json.return_value = list(items)
    return reply


REG_GET = "config.registration_api.requests.get"


class StudentAPITests(AuthenticatedAPITestCase):
    def setUp(self):
        super().setUp()  # gắn access token hợp lệ
        self.student = Student.objects.create(
            student_code="SV001",
            full_name="Nguyễn Văn An",
            email="an.nguyen@student.edu.vn",
            class_name="CNTT1",
            major="Công nghệ thông tin",
        )
        self.list_url = "/api/students/"
        self.detail_url = f"/api/students/{self.student.id}/"

    def test_create_student(self):
        data = {
            "student_code": "SV002",
            "full_name": "Trần Văn Bình",
            "email": "binh.tran@student.edu.vn",
            "class_name": "CNTT1",
            "major": "Công nghệ thông tin",
        }
        response = self.client.post(self.list_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Student.objects.count(), 2)
        self.assertEqual(response.data["student_code"], "SV002")

    def test_list_students(self):
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_search_students_without_accent(self):
        response = self.client.get(self.list_url, {"search": "Nguyen"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        response = self.client.get(self.list_url, {"search": "Tran"})
        self.assertEqual(len(response.data), 0)

    def test_student_detail(self):
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["full_name"], "Nguyễn Văn An")

    def test_student_detail_not_found(self):
        response = self.client.get("/api/students/9999/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_update_student_put(self):
        data = {
            "student_code": "SV001",
            "full_name": "Nguyễn Văn An (updated)",
            "email": "an.nguyen@student.edu.vn",
            "class_name": "CNTT2",
            "major": "Công nghệ thông tin",
        }
        response = self.client.put(self.detail_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.student.refresh_from_db()
        self.assertEqual(self.student.class_name, "CNTT2")

    def test_update_student_patch(self):
        response = self.client.patch(self.detail_url, {"major": "KTPM"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.student.refresh_from_db()
        self.assertEqual(self.student.major, "KTPM")

    @patch(REG_GET, return_value=registration_reply())
    def test_delete_student(self, mock_get):
        response = self.client.delete(self.detail_url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Student.objects.exists())

    def test_student_code_generated_when_omitted(self):
        data = {"full_name": "No Code", "email": "nocode@student.edu.vn"}
        response = self.client.post(self.list_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["student_code"], "SV002")

    def test_student_code_unique(self):
        data = {"student_code": "SV001", "full_name": "Dup", "email": "dup@student.edu.vn"}
        response = self.client.post(self.list_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("student_code", response.data)

    def test_full_name_required(self):
        data = {"student_code": "SV009", "email": "sv9@student.edu.vn"}
        response = self.client.post(self.list_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("full_name", response.data)

    def test_invalid_email(self):
        data = {"student_code": "SV009", "full_name": "Bad Email", "email": "not-an-email"}
        response = self.client.post(self.list_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.data)


@override_settings(JWT_PUBLIC_KEY=TEST_PUBLIC_KEY)
class StudentAuthTests(APITestCase):
    """API phải đăng nhập: thiếu token, token sai/hết hạn đều bị từ chối (401)."""

    url = "/api/students/"

    def test_no_token_returns_401(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response["WWW-Authenticate"], 'Bearer realm="api"')

    def test_write_without_token_returns_401(self):
        response = self.client.post(self.url, {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_expired_token(self):
        self.client.credentials(HTTP_AUTHORIZATION=bearer(expires_in=-60))
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data["code"], "token_expired")

    def test_token_signed_by_other_key(self):
        other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.client.credentials(HTTP_AUTHORIZATION=bearer(key=other))
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data["code"], "token_invalid")

    def test_wrong_issuer_and_refresh_token_rejected(self):
        for kwargs in ({"issuer": "hacker"}, {"token_type": "refresh"}):
            self.client.credentials(HTTP_AUTHORIZATION=bearer(**kwargs))
            self.assertEqual(self.client.get(self.url).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_malformed_header(self):
        self.client.credentials(HTTP_AUTHORIZATION="Bearer")
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_valid_token_ok(self):
        self.client.credentials(HTTP_AUTHORIZATION=bearer(role="STUDENT", student_id=1))
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_200_OK)

    def test_swagger_schema_is_public(self):
        self.assertEqual(self.client.get("/api/schema/").status_code, status.HTTP_200_OK)

    @override_settings(JWT_PUBLIC_KEY="", JWT_PUBLIC_KEY_PATH="/khong/ton/tai.pem")
    def test_missing_public_key_returns_503(self):
        self.client.credentials(HTTP_AUTHORIZATION=bearer())
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)


class StudentPermissionTests(AuthenticatedAPITestCase):
    """Ma trận quyền: ADMIN toàn quyền, LECTURER chỉ xem, STUDENT chỉ xem chính mình."""

    def setUp(self):
        super().setUp()
        self.an = Student.objects.create(student_code="SV001", full_name="Nguyễn Văn An", email="an@x.vn")
        self.binh = Student.objects.create(student_code="SV002", full_name="Trần Văn Bình", email="binh@x.vn")
        self.new_data = {"student_code": "SV009", "full_name": "Mới", "email": "moi@x.vn"}

    def test_student_sees_only_own_record(self):
        self.login_as("STUDENT", user_id=10, student_id=self.an.id)
        response = self.client.get("/api/students/")
        self.assertEqual([s["id"] for s in response.data], [self.an.id])
        self.assertEqual(self.client.get(f"/api/students/{self.an.id}/").status_code, 200)

    def test_student_cannot_view_other_student(self):
        self.login_as("STUDENT", user_id=10, student_id=self.an.id)
        self.assertEqual(self.client.get(f"/api/students/{self.binh.id}/").status_code, 404)

    def test_student_account_without_student_id_sees_nothing(self):
        self.login_as("STUDENT", user_id=10, student_id=None)
        self.assertEqual(self.client.get("/api/students/").data, [])

    def test_student_cannot_modify_even_own_record(self):
        self.login_as("STUDENT", user_id=10, student_id=self.an.id)
        url = f"/api/students/{self.an.id}/"
        self.assertEqual(self.client.patch(url, {"full_name": "Hack"}, format="json").status_code, 403)
        self.assertEqual(self.client.delete(url).status_code, 403)
        self.assertEqual(self.client.post("/api/students/", self.new_data, format="json").status_code, 403)
        self.an.refresh_from_db()
        self.assertEqual(self.an.full_name, "Nguyễn Văn An")

    def test_lecturer_can_read_but_not_write(self):
        self.login_as("LECTURER", user_id=2)
        self.assertEqual(len(self.client.get("/api/students/").data), 2)
        self.assertEqual(self.client.get(f"/api/students/{self.binh.id}/").status_code, 200)
        self.assertEqual(self.client.post("/api/students/", self.new_data, format="json").status_code, 403)
        self.assertEqual(self.client.delete(f"/api/students/{self.binh.id}/").status_code, 403)

    def test_service_token_is_read_only(self):
        self.login_as("SERVICE", username="registration-service")
        self.assertEqual(self.client.get(f"/api/students/{self.an.id}/").status_code, 200)
        self.assertEqual(self.client.post("/api/students/", self.new_data, format="json").status_code, 403)

    @patch(REG_GET, return_value=registration_reply())
    def test_admin_full_access(self, mock_get):
        self.login_as("ADMIN", user_id=1)
        self.assertEqual(self.client.post("/api/students/", self.new_data, format="json").status_code, 201)
        self.assertEqual(self.client.delete(f"/api/students/{self.binh.id}/").status_code, 204)

    def test_unknown_role_is_rejected(self):
        self.login_as("HACKER", user_id=99)
        self.assertEqual(self.client.get("/api/students/").status_code, 403)


class StudentRegistrationConsistencyTests(AuthenticatedAPITestCase):
    """Xóa sinh viên phải hỏi Registration Service trước (không để đăng ký 'mồ côi')."""

    def setUp(self):
        super().setUp()
        self.student = Student.objects.create(
            student_code="SV010", full_name="Lê Văn C", email="c@student.edu.vn",
            class_name="CNTT1", major="CNTT",
        )
        self.url = f"/api/students/{self.student.id}/"

    @patch(REG_GET, return_value=registration_reply([{"id": 1, "status": "PENDING"}]))
    def test_delete_blocked_when_active_registrations(self, mock_get):
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["error"], "Student has active registrations")
        self.assertTrue(Student.objects.filter(id=self.student.id).exists())
        params = mock_get.call_args.kwargs["params"]
        self.assertEqual(params["student_id"], self.student.id)
        self.assertEqual(params["active"], "true")
        self.assertTrue(mock_get.call_args.kwargs["headers"]["Authorization"].startswith("Bearer "))

    @patch(REG_GET, side_effect=requests.ConnectionError("down"))
    def test_delete_returns_503_when_registration_down(self, mock_get):
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["error"], "Registration Service unavailable")
        self.assertTrue(Student.objects.filter(id=self.student.id).exists())

    @patch(REG_GET, return_value=registration_reply(status_code=500))
    def test_delete_returns_503_on_upstream_error(self, mock_get):
        self.assertEqual(self.client.delete(self.url).status_code, 503)

    @patch(REG_GET)
    def test_delete_missing_student_does_not_call_registration(self, mock_get):
        self.assertEqual(self.client.delete("/api/students/9999/").status_code, 404)
        mock_get.assert_not_called()
