"""
Test Registration Service.

Student Service và Thesis Service được giả lập (mock) bằng unittest.mock:
thay hàm requests.get trong external_api bằng hàm fake_get bên dưới,
nên KHÔNG cần chạy 2 service kia khi chạy test.
"""
from unittest.mock import MagicMock, patch

import requests
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Registration

STUDENT_URL = "http://127.0.0.1:8001/api/students/"
THESIS_URL = "http://127.0.0.1:8002/api/theses/"

# "Dữ liệu" của 2 service kia
FAKE_STUDENTS = {
    1: {"id": 1, "student_code": "SV001", "full_name": "Nguyễn Văn An"},
    2: {"id": 2, "student_code": "SV002", "full_name": "Trần Văn Bình"},
    3: {"id": 3, "student_code": "SV003", "full_name": "Lê Văn Cường"},
}
FAKE_THESES = {
    1: {"id": 1, "thesis_code": "DT001", "status": "OPEN", "max_students": 2},
    2: {"id": 2, "thesis_code": "DT002", "status": "CLOSED", "max_students": 2},
}


def make_response(status_code, data=None):
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = data
    return response


def fake_get(url, timeout=None):
    """Giả lập GET tới Student Service / Thesis Service."""
    assert timeout is not None, "HTTP request phải có timeout"
    for base_url, table in ((STUDENT_URL, FAKE_STUDENTS), (THESIS_URL, FAKE_THESES)):
        if url.startswith(base_url):
            obj_id = int(url[len(base_url):].strip("/"))
            if obj_id in table:
                return make_response(200, table[obj_id])
            return make_response(404, {"detail": "No Thesis matches the given query."})
    raise AssertionError(f"Unexpected URL {url}")


@patch("registrations.services.external_api.requests.get", side_effect=fake_get)
class RegistrationCreateTests(APITestCase):
    url = "/api/registrations/"

    def test_create_success_when_student_and_thesis_exist(self, mock_get):
        response = self.client.post(self.url, {"student_id": 1, "thesis_id": 1}, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], "PENDING")
        self.assertEqual(Registration.objects.count(), 1)
        # Registration Service đã thực sự gọi sang 2 service kia
        called_urls = [call.args[0] for call in mock_get.call_args_list]
        self.assertIn(f"{STUDENT_URL}1/", called_urls)
        self.assertIn(f"{THESIS_URL}1/", called_urls)

    def test_fail_when_student_not_exist(self, mock_get):
        response = self.client.post(self.url, {"student_id": 99, "thesis_id": 1}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data, {"error": "Student does not exist"})
        self.assertEqual(Registration.objects.count(), 0)

    def test_fail_when_thesis_not_exist(self, mock_get):
        response = self.client.post(self.url, {"student_id": 1, "thesis_id": 99}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data, {"error": "Thesis does not exist"})

    def test_fail_when_thesis_closed(self, mock_get):
        response = self.client.post(self.url, {"student_id": 1, "thesis_id": 2}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data, {"error": "Thesis is closed"})

    def test_fail_when_duplicate_registration(self, mock_get):
        Registration.objects.create(student_id=1, thesis_id=1)

        response = self.client.post(self.url, {"student_id": 1, "thesis_id": 1}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data, {"error": "Student has already registered for this thesis"}
        )
        self.assertEqual(Registration.objects.count(), 1)

    def test_fail_when_thesis_reached_max_students(self, mock_get):
        # Đề tài 1 có max_students = 2, đã có 2 đăng ký
        Registration.objects.create(student_id=1, thesis_id=1)
        Registration.objects.create(student_id=2, thesis_id=1)

        response = self.client.post(self.url, {"student_id": 3, "thesis_id": 1}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data, {"error": "Thesis has reached maximum students"})

    def test_rejected_registration_does_not_count(self, mock_get):
        Registration.objects.create(student_id=1, thesis_id=1)
        Registration.objects.create(
            student_id=2, thesis_id=1, status=Registration.Status.REJECTED
        )

        response = self.client.post(self.url, {"student_id": 3, "thesis_id": 1}, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_fail_when_missing_fields(self, mock_get):
        response = self.client.post(self.url, {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("student_id", response.data)
        mock_get.assert_not_called()


class ServiceUnavailableTests(APITestCase):
    url = "/api/registrations/"

    @patch(
        "registrations.services.external_api.requests.get",
        side_effect=requests.ConnectionError("connection refused"),
    )
    def test_student_service_down_returns_503(self, mock_get):
        response = self.client.post(self.url, {"student_id": 1, "thesis_id": 1}, format="json")

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(response.data, {"error": "Student Service unavailable"})

    def test_thesis_service_timeout_returns_503(self):
        def student_ok_thesis_timeout(url, timeout=None):
            if url.startswith(STUDENT_URL):
                return make_response(200, FAKE_STUDENTS[1])
            raise requests.Timeout("timed out")

        with patch(
            "registrations.services.external_api.requests.get",
            side_effect=student_ok_thesis_timeout,
        ):
            response = self.client.post(
                self.url, {"student_id": 1, "thesis_id": 1}, format="json"
            )

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(response.data, {"error": "Thesis Service unavailable"})


class RegistrationCrudTests(APITestCase):
    """CRUD + filter (không gọi service khác)."""

    def setUp(self):
        self.r1 = Registration.objects.create(
            student_id=1, thesis_id=1, status=Registration.Status.APPROVED
        )
        self.r2 = Registration.objects.create(student_id=2, thesis_id=1)
        self.r3 = Registration.objects.create(student_id=1, thesis_id=3)

    def test_list_and_filters(self):
        self.assertEqual(len(self.client.get("/api/registrations/").data), 3)
        self.assertEqual(len(self.client.get("/api/registrations/?student_id=1").data), 2)
        self.assertEqual(len(self.client.get("/api/registrations/?thesis_id=1").data), 2)
        response = self.client.get("/api/registrations/?status=APPROVED")
        self.assertEqual([r["id"] for r in response.data], [self.r1.id])

    def test_detail(self):
        response = self.client.get(f"/api/registrations/{self.r2.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["student_id"], 2)

    def test_update_status(self):
        url = f"/api/registrations/{self.r2.id}/"
        response = self.client.patch(url, {"status": "APPROVED"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response = self.client.put(url, {"status": "REJECTED"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.r2.refresh_from_db()
        self.assertEqual(self.r2.status, "REJECTED")

    def test_update_cannot_change_student_or_thesis(self):
        url = f"/api/registrations/{self.r2.id}/"
        self.client.patch(url, {"student_id": 99, "thesis_id": 99}, format="json")
        self.r2.refresh_from_db()
        self.assertEqual((self.r2.student_id, self.r2.thesis_id), (2, 1))

    def test_delete(self):
        response = self.client.delete(f"/api/registrations/{self.r3.id}/")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(Registration.objects.count(), 2)
