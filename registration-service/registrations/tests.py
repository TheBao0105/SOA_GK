"""
Test Registration Service.

Student Service và Thesis Service được giả lập (mock) bằng unittest.mock:
thay hàm requests.get trong external_api bằng hàm fake_get bên dưới,
nên KHÔNG cần chạy 2 service kia khi chạy test.
"""
from io import StringIO
from unittest.mock import MagicMock, patch

import requests
from django.core.management import CommandError, call_command
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from config.testing import TEST_PUBLIC_KEY, AuthenticatedAPITestCase, bearer

from datetime import timedelta

from django.utils import timezone

from .models import ProgressNote, Registration, RegistrationLock, RegistrationPeriod

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


def open_period(**kwargs):
    """Tạo một đợt đăng ký đang mở (mặc định mỗi sinh viên tối đa 1 đăng ký hiệu lực)."""
    now = timezone.now()
    data = {"name": "Đợt test", "start_at": now - timedelta(days=1), "end_at": now + timedelta(days=30)}
    data.update(kwargs)
    return RegistrationPeriod.objects.create(**data)


class RegistrationTestCase(AuthenticatedAPITestCase):
    """Đã đăng nhập (ADMIN) và có sẵn một đợt đăng ký đang mở."""

    def setUp(self):
        super().setUp()
        self.period = open_period()


def make_response(status_code, data=None):
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = data
    return response


def fake_get(url, headers=None, timeout=None):
    """Giả lập GET tới Student Service / Thesis Service."""
    assert timeout is not None, "HTTP request phải có timeout"
    if not (headers or {}).get("Authorization", "").startswith("Bearer "):
        return make_response(401, {"detail": "Authentication credentials were not provided."})
    for base_url, table in ((STUDENT_URL, FAKE_STUDENTS), (THESIS_URL, FAKE_THESES)):
        if url.startswith(base_url):
            obj_id = int(url[len(base_url):].strip("/"))
            if obj_id in table:
                return make_response(200, table[obj_id])
            return make_response(404, {"detail": "No Thesis matches the given query."})
    raise AssertionError(f"Unexpected URL {url}")


@patch("registrations.services.external_api.requests.get", side_effect=fake_get)
class RegistrationCreateTests(RegistrationTestCase):
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


class ServiceUnavailableTests(RegistrationTestCase):
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
        def student_ok_thesis_timeout(url, headers=None, timeout=None):
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


class RegistrationCrudTests(RegistrationTestCase):
    """CRUD + filter (không gọi service khác)."""

    def setUp(self):
        super().setUp()
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
        response = self.client.put(url, {"status": "REJECTED", "reject_reason": "Không phù hợp"}, format="json")
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


@override_settings(JWT_PUBLIC_KEY=TEST_PUBLIC_KEY)
class RegistrationAuthTests(APITestCase):
    """Đăng nhập + chuyển tiếp token sang Student/Thesis Service."""

    url = "/api/registrations/"

    def setUp(self):
        open_period()

    def test_no_token_returns_401_and_does_not_call_other_services(self):
        with patch("registrations.services.external_api.requests.get") as mock_get:
            response = self.client.post(self.url, {"student_id": 1, "thesis_id": 1}, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        mock_get.assert_not_called()
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_expired_token(self):
        self.client.credentials(HTTP_AUTHORIZATION=bearer(expires_in=-60))
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data["code"], "token_expired")

    @patch("registrations.services.external_api.requests.get", side_effect=fake_get)
    def test_user_token_is_forwarded_to_other_services(self, mock_get):
        header = bearer(user_id=7, role="STUDENT", student_id=1)
        self.client.credentials(HTTP_AUTHORIZATION=header)
        response = self.client.post(self.url, {"student_id": 1, "thesis_id": 1}, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        for call in mock_get.call_args_list:
            self.assertEqual(call.kwargs["headers"]["Authorization"], header)

    def test_other_service_rejects_token_returns_502(self):
        self.client.credentials(HTTP_AUTHORIZATION=bearer())
        with patch(
            "registrations.services.external_api.requests.get",
            return_value=make_response(401, {"detail": "Token has expired."}),
        ):
            response = self.client.post(self.url, {"student_id": 1, "thesis_id": 1}, format="json")
        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        self.assertEqual(response.data, {"error": "Student Service rejected the credentials"})
        self.assertEqual(Registration.objects.count(), 0)

    def test_non_json_response_is_treated_as_unavailable(self):
        self.client.credentials(HTTP_AUTHORIZATION=bearer())
        bad = make_response(200)
        bad.json.side_effect = ValueError("not json")
        with patch("registrations.services.external_api.requests.get", return_value=bad):
            response = self.client.post(self.url, {"student_id": 1, "thesis_id": 1}, format="json")
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)


class SeedDataTests(APITestCase):
    """seed_data không có người dùng -> dùng SERVICE_TOKEN."""

    @override_settings(SERVICE_TOKEN="service-token-abc")
    def test_seed_uses_service_token(self):
        def fake_search(url, headers=None, timeout=None):
            self.assertEqual(headers, {"Authorization": "Bearer service-token-abc"})
            if "/api/students/" in url:
                code = url.split("search=")[1]
                return make_response(200, [{"id": int(code[-1]), "student_code": code}])
            code = url.split("search=")[1]
            return make_response(200, [{"id": int(code[-1]), "thesis_code": code}])

        with patch("registrations.services.external_api.requests.get", side_effect=fake_search):
            call_command("seed_data", stdout=StringIO())
        self.assertEqual(Registration.objects.count(), 3)

    @override_settings(SERVICE_TOKEN="")
    def test_seed_without_service_token_gives_clear_error(self):
        with patch("registrations.services.external_api.requests.get", side_effect=fake_get):
            with self.assertRaisesMessage(CommandError, "SERVICE_TOKEN"):
                call_command("seed_data", stdout=StringIO())


# ---------------------------------------------------------------- Phân quyền (Giai đoạn 2)
TUAN, HA = 2, 3
THESES_WITH_SUPERVISOR = {
    1: {"id": 1, "thesis_code": "DT001", "status": "OPEN", "max_students": 3, "supervisor_id": TUAN},
    2: {"id": 2, "thesis_code": "DT002", "status": "OPEN", "max_students": 3, "supervisor_id": HA},
}


def fake_get_rbac(url, headers=None, timeout=None):
    """Như fake_get, thêm GET /api/theses/?supervisor_id= (lọc đề tài theo GVHD)."""
    if url.startswith(THESIS_URL + "?supervisor_id="):
        sid = int(url.split("=")[1])
        return make_response(200, [t for t in THESES_WITH_SUPERVISOR.values() if t["supervisor_id"] == sid])
    if url.startswith(THESIS_URL):
        obj_id = int(url[len(THESIS_URL):].strip("/"))
        thesis = THESES_WITH_SUPERVISOR.get(obj_id)
        return make_response(200, thesis) if thesis else make_response(404, {})
    return fake_get(url, headers=headers, timeout=timeout)


@patch("registrations.services.external_api.requests.get", side_effect=fake_get_rbac)
class RegistrationPermissionTests(RegistrationTestCase):
    url = "/api/registrations/"

    def setUp(self):
        super().setUp()
        self.r_an_dt1 = Registration.objects.create(student_id=1, thesis_id=1)                 # GV Tuấn
        self.r_binh_dt2 = Registration.objects.create(student_id=2, thesis_id=2)               # GV Hà
        self.r_an_dt2 = Registration.objects.create(
            student_id=1, thesis_id=2, status=Registration.Status.APPROVED
        )

    def detail(self, reg):
        return f"{self.url}{reg.id}/"

    # ---- Sinh viên
    def test_student_registers_for_self(self, mock_get):
        Registration.objects.all().delete()
        self.login_as("STUDENT", user_id=20, student_id=3)
        response = self.client.post(self.url, {"student_id": 3, "thesis_id": 1}, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_student_cannot_register_for_someone_else(self, mock_get):
        self.login_as("STUDENT", user_id=20, student_id=3)
        response = self.client.post(self.url, {"student_id": 2, "thesis_id": 1}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data, {"error": "Students can only register for themselves"})
        mock_get.assert_not_called()

    def test_student_account_not_linked(self, mock_get):
        self.login_as("STUDENT", user_id=20, student_id=None)
        response = self.client.post(self.url, {"student_id": 1, "thesis_id": 1}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_student_sees_only_own_registrations(self, mock_get):
        self.login_as("STUDENT", user_id=10, student_id=1)
        ids = sorted(r["id"] for r in self.client.get(self.url).data)
        self.assertEqual(ids, sorted([self.r_an_dt1.id, self.r_an_dt2.id]))
        # Lọc theo sinh viên khác cũng không lộ dữ liệu
        self.assertEqual(self.client.get(self.url, {"student_id": 2}).data, [])
        self.assertEqual(self.client.get(self.detail(self.r_binh_dt2)).status_code, 404)

    def test_student_cannot_approve(self, mock_get):
        self.login_as("STUDENT", user_id=10, student_id=1)
        response = self.client.patch(self.detail(self.r_an_dt1), {"status": "APPROVED"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.r_an_dt1.refresh_from_db()
        self.assertEqual(self.r_an_dt1.status, "PENDING")

    def test_student_cancels_own_pending_only(self, mock_get):
        self.login_as("STUDENT", user_id=10, student_id=1)
        cancel = lambda r: self.client.post(f"{self.detail(r)}cancel/")  # noqa: E731
        self.assertEqual(cancel(self.r_an_dt2).status_code, 400)   # đã APPROVED
        self.assertEqual(cancel(self.r_binh_dt2).status_code, 404)  # của người khác
        self.assertEqual(cancel(self.r_an_dt1).status_code, 200)
        self.r_an_dt1.refresh_from_db()
        self.assertEqual(self.r_an_dt1.status, "CANCELLED")
        self.assertEqual(Registration.objects.count(), 3)  # hủy không xóa dòng
        self.assertEqual(self.client.delete(self.detail(self.r_an_dt1)).status_code, 403)  # xóa hẳn chỉ ADMIN

    # ---- Giảng viên
    def test_lecturer_sees_only_registrations_of_own_theses(self, mock_get):
        self.login_as("LECTURER", user_id=TUAN)
        ids = [r["id"] for r in self.client.get(self.url).data]
        self.assertEqual(ids, [self.r_an_dt1.id])
        called = [c.args[0] for c in mock_get.call_args_list]
        self.assertIn(f"{THESIS_URL}?supervisor_id={TUAN}", called)

    def test_lecturer_approves_own_thesis_registration(self, mock_get):
        self.login_as("LECTURER", user_id=TUAN)
        response = self.client.patch(self.detail(self.r_an_dt1), {"status": "APPROVED"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "APPROVED")

    def test_lecturer_cannot_approve_other_lecturers_registration(self, mock_get):
        self.login_as("LECTURER", user_id=TUAN)
        response = self.client.patch(self.detail(self.r_binh_dt2), {"status": "APPROVED"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.r_binh_dt2.refresh_from_db()
        self.assertEqual(self.r_binh_dt2.status, "PENDING")

    def test_lecturer_cannot_create_or_delete(self, mock_get):
        self.login_as("LECTURER", user_id=TUAN)
        response = self.client.post(self.url, {"student_id": 3, "thesis_id": 1}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.delete(self.detail(self.r_an_dt1)).status_code, 403)

    def test_lecturer_scope_when_thesis_service_down(self, mock_get):
        self.login_as("LECTURER", user_id=TUAN)
        mock_get.side_effect = requests.ConnectionError("down")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(response.data, {"error": "Thesis Service unavailable"})

    # ---- Admin / service
    def test_admin_sees_and_manages_everything(self, mock_get):
        self.login_as("ADMIN", user_id=1)
        self.assertEqual(len(self.client.get(self.url).data), 3)
        response = self.client.patch(
            self.detail(self.r_binh_dt2), {"status": "REJECTED", "reject_reason": "Hết chỗ"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.delete(self.detail(self.r_an_dt2)).status_code, 204)

    def test_service_token_read_only(self, mock_get):
        self.login_as("SERVICE", username="grading-service")
        self.assertEqual(len(self.client.get(self.url).data), 3)
        response = self.client.patch(self.detail(self.r_an_dt1), {"status": "APPROVED"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


# ---------------------------------------------------------------- Nghiệp vụ đăng ký (Giai đoạn 3)
@patch("registrations.services.external_api.requests.get", side_effect=fake_get_rbac)
class RegistrationWorkflowTests(RegistrationTestCase):
    url = "/api/registrations/"

    def register(self, student_id, thesis_id):
        return self.client.post(self.url, {"student_id": student_id, "thesis_id": thesis_id}, format="json")

    # ---- Đợt đăng ký
    def test_no_open_period(self, mock_get):
        self.period.delete()
        response = self.register(1, 1)
        self.assertEqual(response.data, {"error": "Registration period is closed"})
        mock_get.assert_not_called()

    def test_period_expired_or_inactive(self, mock_get):
        self.period.end_at = timezone.now() - timedelta(minutes=1)
        self.period.save()
        self.assertEqual(self.register(1, 1).data, {"error": "Registration period is closed"})
        open_period(is_active=False)
        self.assertEqual(self.register(1, 1).data, {"error": "Registration period is closed"})

    def test_registration_records_period(self, mock_get):
        response = self.register(1, 1)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["period"], self.period.id)

    # ---- Khóa chống đăng ký đồng thời (SQL Server)
    def test_lock_rows_created_before_transaction(self, mock_get):
        self.assertEqual(self.register(1, 1).status_code, 201)
        self.assertEqual(
            set(RegistrationLock.objects.values_list("key", flat=True)), {"thesis:1", "student:1"}
        )
        RegistrationLock.ensure("thesis:1", "student:1")  # gọi lại không lỗi, không trùng
        self.assertEqual(RegistrationLock.objects.count(), 2)

    def test_deadlock_is_retried(self, mock_get):
        from django.db import OperationalError

        real_acquire = RegistrationLock.acquire.__func__
        calls = []

        def flaky(cls, *keys):
            calls.append(keys)
            if len(calls) == 1:
                raise OperationalError("Transaction was deadlocked (1205)")
            return real_acquire(cls, *keys)

        with patch("registrations.views.time.sleep"), \
                patch.object(RegistrationLock, "acquire", classmethod(flaky)):
            response = self.register(1, 1)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(calls), 2)
        self.assertEqual(Registration.objects.count(), 1)

    def test_persistent_deadlock_returns_503_not_500(self, mock_get):
        from django.db import OperationalError

        with patch("registrations.views.time.sleep"), \
                patch.object(RegistrationLock, "acquire", side_effect=OperationalError("deadlock")):
            response = self.register(1, 1)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data, {"error": "Registration Service is busy, please try again"})
        self.assertEqual(Registration.objects.count(), 0)

    # ---- Giới hạn của sinh viên
    def test_student_limited_to_one_active_registration(self, mock_get):
        self.assertEqual(self.register(1, 1).status_code, 201)
        response = self.register(1, 2)
        self.assertEqual(response.data, {"error": "Student already has an active registration"})

    def test_limit_is_configurable_per_period(self, mock_get):
        self.period.max_active_per_student = 2
        self.period.save()
        self.assertEqual(self.register(1, 1).status_code, 201)
        self.assertEqual(self.register(1, 2).status_code, 201)

    def test_capacity_checked_before_student_limit(self, mock_get):
        THESES_WITH_SUPERVISOR[2]["max_students"] = 1
        try:
            Registration.objects.create(student_id=9, thesis_id=2)
            Registration.objects.create(student_id=1, thesis_id=1)
            self.assertEqual(self.register(1, 2).data, {"error": "Thesis has reached maximum students"})
        finally:
            THESES_WITH_SUPERVISOR[2]["max_students"] = 3

    def test_lock_is_taken_before_counting(self, mock_get):
        with patch("registrations.views.RegistrationLock.acquire", wraps=RegistrationLock.acquire) as acquire:
            self.register(1, 1)
        acquire.assert_called_once_with("thesis:1", "student:1")

    # ---- Hủy và đăng ký lại
    def test_cancel_frees_slot_and_allows_new_registration(self, mock_get):
        reg = Registration.objects.create(student_id=1, thesis_id=1, period=self.period)
        self.login_as("STUDENT", user_id=10, student_id=1)
        response = self.client.post(f"{self.url}{reg.id}/cancel/")
        self.assertEqual(response.data["status"], "CANCELLED")
        self.assertEqual(response.data["cancelled_by"], 10)
        self.assertIsNotNone(response.data["cancelled_at"])
        # Đổi đề tài: hủy xong đăng ký đề tài khác
        self.assertEqual(self.register(1, 2).status_code, 201)

    def test_re_register_reuses_row_after_cancel_or_reject(self, mock_get):
        reg = Registration.objects.create(
            student_id=1, thesis_id=1, status=Registration.Status.REJECTED, reject_reason="x", processed_by=2
        )
        response = self.register(1, 1)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["id"], reg.id)
        self.assertEqual(response.data["status"], "PENDING")
        self.assertEqual(response.data["reject_reason"], "")
        self.assertIsNone(response.data["processed_by"])
        self.assertEqual(Registration.objects.count(), 1)

    def test_cancelled_and_rejected_do_not_take_slots(self, mock_get):
        THESES_WITH_SUPERVISOR[1]["max_students"] = 1
        try:
            Registration.objects.create(student_id=8, thesis_id=1, status=Registration.Status.CANCELLED)
            Registration.objects.create(student_id=9, thesis_id=1, status=Registration.Status.REJECTED)
            self.assertEqual(self.register(1, 1).status_code, 201)
        finally:
            THESES_WITH_SUPERVISOR[1]["max_students"] = 3

    def test_student_cannot_cancel_when_period_closed(self, mock_get):
        reg = Registration.objects.create(student_id=1, thesis_id=1, period=self.period)
        self.period.is_active = False
        self.period.save()
        self.login_as("STUDENT", user_id=10, student_id=1)
        response = self.client.post(f"{self.url}{reg.id}/cancel/")
        self.assertEqual(response.data, {"error": "Registration period is closed"})

    def test_admin_can_cancel_approved_but_not_twice(self, mock_get):
        reg = Registration.objects.create(student_id=1, thesis_id=1, status=Registration.Status.APPROVED)
        self.assertEqual(self.client.post(f"{self.url}{reg.id}/cancel/").status_code, 200)
        response = self.client.post(f"{self.url}{reg.id}/cancel/")
        self.assertEqual(response.data, {"error": "Registration is already cancelled"})

    def test_lecturer_cannot_cancel(self, mock_get):
        reg = Registration.objects.create(student_id=1, thesis_id=1)
        self.login_as("LECTURER", user_id=TUAN)
        self.assertEqual(self.client.post(f"{self.url}{reg.id}/cancel/").status_code, 403)

    # ---- Duyệt / từ chối
    def test_reject_requires_reason(self, mock_get):
        reg = Registration.objects.create(student_id=1, thesis_id=1)
        self.login_as("LECTURER", user_id=TUAN)
        response = self.client.patch(f"{self.url}{reg.id}/", {"status": "REJECTED"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("reject_reason", response.data)
        response = self.client.patch(
            f"{self.url}{reg.id}/", {"status": "REJECTED", "reject_reason": "  Chưa đủ điều kiện  "}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["reject_reason"], "Chưa đủ điều kiện")
        self.assertEqual(response.data["processed_by"], TUAN)

    def test_approve_records_processor_and_time(self, mock_get):
        reg = Registration.objects.create(student_id=1, thesis_id=1)
        self.login_as("LECTURER", user_id=TUAN)
        response = self.client.patch(f"{self.url}{reg.id}/", {"status": "APPROVED"}, format="json")
        self.assertEqual(response.data["processed_by"], TUAN)
        self.assertIsNotNone(response.data["processed_at"])
        self.assertEqual(response.data["reject_reason"], "")

    def test_cannot_change_cancelled_or_set_cancelled_via_patch(self, mock_get):
        reg = Registration.objects.create(student_id=1, thesis_id=1, status=Registration.Status.CANCELLED)
        response = self.client.patch(f"{self.url}{reg.id}/", {"status": "APPROVED"}, format="json")
        self.assertEqual(response.data, {"error": "Cancelled registrations cannot be changed"})
        reg2 = Registration.objects.create(student_id=2, thesis_id=1)
        response = self.client.patch(f"{self.url}{reg2.id}/", {"status": "CANCELLED"}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_reopen_rejected_rechecks_student_limit(self, mock_get):
        rejected = Registration.objects.create(
            student_id=1, thesis_id=1, status=Registration.Status.REJECTED, reject_reason="x"
        )
        Registration.objects.create(student_id=1, thesis_id=2)  # đã có đăng ký khác còn hiệu lực
        response = self.client.patch(f"{self.url}{rejected.id}/", {"status": "PENDING"}, format="json")
        self.assertEqual(response.data, {"error": "Student already has an active registration"})

    def test_active_filter(self, mock_get):
        Registration.objects.create(student_id=1, thesis_id=1)
        Registration.objects.create(student_id=2, thesis_id=1, status=Registration.Status.CANCELLED)
        Registration.objects.create(student_id=3, thesis_id=1, status=Registration.Status.APPROVED)
        data = self.client.get(self.url, {"thesis_id": 1, "active": "true"}).data
        self.assertEqual(sorted(r["student_id"] for r in data), [1, 3])

    # ---- Nhận xét / tiến độ
    def test_progress_notes(self, mock_get):
        approved = Registration.objects.create(student_id=1, thesis_id=1, status=Registration.Status.APPROVED)
        pending = Registration.objects.create(student_id=2, thesis_id=1)
        other = Registration.objects.create(student_id=3, thesis_id=2, status=Registration.Status.APPROVED)

        self.login_as("LECTURER", user_id=TUAN, full_name="TS. Tuấn")
        url = f"{self.url}{approved.id}/notes/"
        response = self.client.post(url, {"content": "Đã xong phân tích yêu cầu", "progress": 30}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["author_name"], "TS. Tuấn")
        self.assertEqual(
            self.client.post(f"{self.url}{pending.id}/notes/", {"content": "x"}, format="json").data,
            {"error": "Progress notes can only be added to approved registrations"},
        )
        self.assertEqual(self.client.post(f"{self.url}{other.id}/notes/", {"content": "x"}, format="json").status_code, 404)
        self.assertEqual(
            self.client.post(url, {"content": "x", "progress": 150}, format="json").status_code, 400
        )

        self.login_as("STUDENT", user_id=10, student_id=1)
        notes = self.client.get(url).data
        self.assertEqual([n["progress"] for n in notes], [30])
        self.assertEqual(self.client.post(url, {"content": "tự chấm"}, format="json").status_code, 403)
        self.assertEqual(self.client.get(f"{self.url}{other.id}/notes/").status_code, 404)
        self.assertEqual(ProgressNote.objects.count(), 1)

    # ---- API đợt đăng ký
    def test_period_api_permissions(self, mock_get):
        self.login_as("STUDENT", user_id=10, student_id=1)
        response = self.client.get("/api/periods/current/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["is_open"])
        data = {"name": "Đợt 2", "start_at": "2027-01-01T00:00:00Z", "end_at": "2027-02-01T00:00:00Z"}
        self.assertEqual(self.client.post("/api/periods/", data, format="json").status_code, 403)

        self.login_as("ADMIN", user_id=1)
        self.assertEqual(self.client.post("/api/periods/", data, format="json").status_code, 201)
        bad = {**data, "end_at": "2026-12-01T00:00:00Z"}
        self.assertIn("end_at", self.client.post("/api/periods/", bad, format="json").data)

    def test_no_current_period(self, mock_get):
        self.period.delete()
        self.assertEqual(self.client.get("/api/periods/current/").status_code, 404)

    def test_cannot_delete_period_with_registrations(self, mock_get):
        Registration.objects.create(student_id=1, thesis_id=1, period=self.period)
        response = self.client.delete(f"/api/periods/{self.period.id}/")
        self.assertEqual(response.status_code, 409)
