from unittest.mock import MagicMock, patch

import requests
from cryptography.hazmat.primitives.asymmetric import rsa
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from config.testing import TEST_PUBLIC_KEY, AuthenticatedAPITestCase, bearer

from .models import Thesis


def registration_reply(items=(), status_code=200):
    """Giả lập phản hồi GET /api/registrations/?active=true của Registration Service."""
    reply = MagicMock(status_code=status_code)
    reply.json.return_value = list(items)
    return reply


REG_GET = "config.registration_api.requests.get"


class ThesisAPITests(AuthenticatedAPITestCase):
    def setUp(self):
        super().setUp()  # gắn access token hợp lệ
        self.thesis = Thesis.objects.create(
            thesis_code="DT001",
            title="Hệ thống quản lý thư viện",
            description="Ứng dụng web quản lý sách",
            supervisor="TS. Phạm Minh Tuấn",
            max_students=2,
        )
        self.list_url = "/api/theses/"
        self.detail_url = f"/api/theses/{self.thesis.id}/"

    def test_create_thesis(self):
        data = {
            "thesis_code": "DT002",
            "title": "Hệ thống đặt sân thể thao",
            "supervisor": "ThS. Hoàng Thu Hà",
            "max_students": 1,
        }
        response = self.client.post(self.list_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], "OPEN")  # mặc định OPEN
        self.assertEqual(Thesis.objects.count(), 2)

    def test_list_theses(self):
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_search_theses(self):
        # Tìm theo từ khóa có trong mô tả
        response = self.client.get(self.list_url, {"search": "web"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

        # Tìm theo mã đề tài
        response = self.client.get(self.list_url, {"search": "DT001"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

        # Từ khóa không tồn tại
        response = self.client.get(self.list_url, {"search": "blockchain"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 0)

    def test_thesis_detail(self):
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["thesis_code"], "DT001")

    def test_thesis_detail_not_found(self):
        response = self.client.get("/api/theses/9999/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_update_thesis_put(self):
        data = {
            "thesis_code": "DT001",
            "title": "Hệ thống quản lý thư viện số",
            "description": "",
            "supervisor": "TS. Phạm Minh Tuấn",
            "max_students": 3,
            "status": "OPEN",
        }
        response = self.client.put(self.detail_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.thesis.refresh_from_db()
        self.assertEqual(self.thesis.max_students, 3)

    def test_update_thesis_patch_close(self):
        response = self.client.patch(
            self.detail_url, {"status": "CLOSED"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.thesis.refresh_from_db()
        self.assertEqual(self.thesis.status, "CLOSED")

    @patch(REG_GET, return_value=registration_reply())
    def test_delete_thesis(self, mock_get):
        response = self.client.delete(self.detail_url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Thesis.objects.exists())

    def test_thesis_code_unique(self):
        data = {"thesis_code": "DT001", "title": "Trùng mã", "max_students": 1}
        response = self.client.post(self.list_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("thesis_code", response.data)

    def test_title_required(self):
        data = {"thesis_code": "DT009", "max_students": 1}
        response = self.client.post(self.list_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("title", response.data)

    def test_max_students_must_be_positive(self):
        data = {"thesis_code": "DT009", "title": "Đề tài X", "max_students": 0}
        response = self.client.post(self.list_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("max_students", response.data)


@override_settings(JWT_PUBLIC_KEY=TEST_PUBLIC_KEY)
class ThesisAuthTests(APITestCase):
    """API phải đăng nhập: thiếu token, token sai/hết hạn đều bị từ chối (401)."""

    url = "/api/theses/"

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


class ThesisPermissionTests(AuthenticatedAPITestCase):
    """Ma trận quyền đề tài theo vai trò và theo GVHD (supervisor_id)."""

    TUAN, HA = 2, 3

    def setUp(self):
        super().setUp()
        self.mine = Thesis.objects.create(thesis_code="DT001", title="Đề tài GV Tuấn", supervisor_id=self.TUAN)
        self.other = Thesis.objects.create(thesis_code="DT002", title="Đề tài GV Hà", supervisor_id=self.HA)
        self.closed = Thesis.objects.create(
            thesis_code="DT003", title="Đã đóng", supervisor_id=self.TUAN, status=Thesis.Status.CLOSED
        )

    def test_student_list_shows_only_open_theses(self):
        self.login_as("STUDENT", user_id=10, student_id=1)
        codes = [t["thesis_code"] for t in self.client.get("/api/theses/").data]
        self.assertEqual(codes, ["DT001", "DT002"])

    def test_student_can_read_closed_thesis_detail(self):
        # Registration Service cần đọc trạng thái để báo "Thesis is closed"
        self.login_as("STUDENT", user_id=10, student_id=1)
        response = self.client.get(f"/api/theses/{self.closed.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "CLOSED")

    def test_student_cannot_write(self):
        self.login_as("STUDENT", user_id=10, student_id=1)
        data = {"thesis_code": "DT009", "title": "X", "max_students": 1}
        self.assertEqual(self.client.post("/api/theses/", data, format="json").status_code, 403)
        self.assertEqual(self.client.patch(f"/api/theses/{self.mine.id}/", {"title": "Y"}, format="json").status_code, 403)
        self.assertEqual(self.client.delete(f"/api/theses/{self.mine.id}/").status_code, 403)

    def test_lecturer_creates_thesis_as_own_supervisor(self):
        self.login_as("LECTURER", user_id=self.TUAN, full_name="TS. Phạm Minh Tuấn")
        data = {"thesis_code": "DT010", "title": "Đề tài mới", "max_students": 2, "supervisor_id": self.HA}
        response = self.client.post("/api/theses/", data, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["supervisor_id"], self.TUAN)  # không tạo hộ GV khác được
        self.assertEqual(response.data["supervisor"], "TS. Phạm Minh Tuấn")
        self.assertEqual(response.data["created_by"], self.TUAN)

    def test_lecturer_updates_only_own_thesis(self):
        self.login_as("LECTURER", user_id=self.TUAN)
        response = self.client.patch(f"/api/theses/{self.mine.id}/", {"status": "CLOSED"}, format="json")
        self.assertEqual(response.status_code, 200)
        response = self.client.patch(f"/api/theses/{self.other.id}/", {"status": "CLOSED"}, format="json")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.client.delete(f"/api/theses/{self.other.id}/").status_code, 403)
        self.other.refresh_from_db()
        self.assertEqual(self.other.status, "OPEN")

    def test_lecturer_cannot_hand_thesis_to_another_lecturer(self):
        self.login_as("LECTURER", user_id=self.TUAN)
        self.client.patch(f"/api/theses/{self.mine.id}/", {"supervisor_id": self.HA}, format="json")
        self.mine.refresh_from_db()
        self.assertEqual(self.mine.supervisor_id, self.TUAN)

    def test_filter_by_supervisor(self):
        self.login_as("LECTURER", user_id=self.TUAN)
        codes = [t["thesis_code"] for t in self.client.get("/api/theses/", {"supervisor_id": self.TUAN}).data]
        self.assertEqual(codes, ["DT001", "DT003"])

    @patch(REG_GET, return_value=registration_reply())
    def test_admin_assigns_supervisor(self, mock_get):
        self.login_as("ADMIN", user_id=1)
        response = self.client.patch(f"/api/theses/{self.other.id}/", {"supervisor_id": self.TUAN}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["supervisor_id"], self.TUAN)
        self.assertEqual(self.client.delete(f"/api/theses/{self.closed.id}/").status_code, 204)

    def test_service_token_read_only(self):
        self.login_as("SERVICE", username="registration-service")
        self.assertEqual(self.client.get(f"/api/theses/{self.mine.id}/").status_code, 200)
        self.assertEqual(self.client.delete(f"/api/theses/{self.mine.id}/").status_code, 403)


class ThesisRegistrationConsistencyTests(AuthenticatedAPITestCase):
    """Xóa đề tài / giảm chỉ tiêu phải đối chiếu số đăng ký còn hiệu lực bên Registration Service."""

    def setUp(self):
        super().setUp()
        self.thesis = Thesis.objects.create(thesis_code="DT050", title="Đề tài Y", max_students=3)
        self.url = f"/api/theses/{self.thesis.id}/"

    @patch(REG_GET, return_value=registration_reply([{"id": 1}]))
    def test_delete_blocked_when_active_registrations(self, mock_get):
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["error"], "Thesis has active registrations")
        self.assertTrue(Thesis.objects.filter(id=self.thesis.id).exists())
        self.assertEqual(mock_get.call_args.kwargs["params"]["thesis_id"], self.thesis.id)

    @patch(REG_GET, side_effect=requests.Timeout("slow"))
    def test_delete_returns_503_when_registration_down(self, mock_get):
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["error"], "Registration Service unavailable")

    @patch(REG_GET, return_value=registration_reply([{"id": 1}, {"id": 2}]))
    def test_cannot_lower_max_students_below_active(self, mock_get):
        response = self.client.patch(self.url, {"max_students": 1}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("(2)", str(response.data["max_students"][0]))
        self.thesis.refresh_from_db()
        self.assertEqual(self.thesis.max_students, 3)

    @patch(REG_GET, return_value=registration_reply([{"id": 1}, {"id": 2}]))
    def test_can_lower_max_students_to_active_count(self, mock_get):
        response = self.client.patch(self.url, {"max_students": 2}, format="json")
        self.assertEqual(response.status_code, 200)

    @patch(REG_GET)
    def test_raising_max_students_does_not_call_registration(self, mock_get):
        response = self.client.patch(self.url, {"max_students": 5}, format="json")
        self.assertEqual(response.status_code, 200)
        mock_get.assert_not_called()

    @patch(REG_GET, side_effect=requests.ConnectionError("down"))
    def test_lowering_max_students_returns_503_when_registration_down(self, mock_get):
        response = self.client.patch(self.url, {"max_students": 1}, format="json")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["error"], "Registration Service unavailable")
