"""
Test Web Portal. Các service được giả lập bằng cách mock requests.request / requests.post,
nên không cần chạy service nào khi chạy test.
"""
import copy
from unittest.mock import MagicMock, patch

import requests
from django.test import SimpleTestCase

STUDENTS = [{"id": 1, "student_code": "SV001", "full_name": "Nguyễn Văn An",
             "email": "an@x.vn", "class_name": "CNTT1", "major": "CNTT"}]
THESES = [{"id": 1, "thesis_code": "DT001", "title": "Hệ thống quản lý thư viện",
           "description": "", "supervisor": "TS. A", "max_students": 2, "status": "OPEN"}]
NOTES = [{"id": 1, "registration": 1, "author_id": 2, "author_name": "TS. Tuấn", "author_role": "LECTURER",
          "content": "Đã xong chương 1", "progress": 30, "created_at": "2026-10-10T09:00:00+07:00"}]
REGISTRATIONS = [{"id": 1, "student_id": 1, "thesis_id": 1,
                  "registered_at": "2026-10-04T10:00:00+07:00", "status": "PENDING"}]


LOGIN_OK = {
    "access": "access-1", "refresh": "refresh-1", "token_type": "Bearer", "expires_in": 900,
    "user": {"id": 1, "username": "admin", "full_name": "Quản trị", "role": "ADMIN", "student_id": None},
}


def make_response(status_code, data=None):
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = copy.deepcopy(data)  # mỗi lần gọi là một JSON mới, như HTTP thật
    response.content = b"x" if data is not None else b""
    response.reason = "Error"
    return response


def fake_request(method, url, timeout=None, **kwargs):
    if "/api/auth/login/" in url:
        return make_response(200, LOGIN_OK)
    if "/api/auth/logout/" in url:
        return make_response(200, {"detail": "Logged out."})
    if method == "GET":
        if "/notes/" in url:
            return make_response(200, NOTES)
        if "/api/registrations/1/" in url:
            return make_response(200, REGISTRATIONS[0])
        if "/api/students/1/" in url:
            return make_response(200, STUDENTS[0])
        if "/api/students/" in url:
            return make_response(200, STUDENTS)
        if "/api/theses/" in url:
            return make_response(200, THESES)
        if "/api/registrations/" in url:
            return make_response(200, REGISTRATIONS)
    if method == "POST" and "/api/registrations/" in url:
        return make_response(400, {"error": "Thesis is closed"})
    if method == "POST" and "/api/students/" in url:
        return make_response(201, {"id": 2, **kwargs["json"]})
    raise AssertionError(f"Unexpected {method} {url}")


class LoggedInTestCase(SimpleTestCase):
    """Đăng nhập (Identity Service được mock) trước mỗi test."""

    def setUp(self):
        with patch("portal.api_client.requests.request", side_effect=fake_request):
            response = self.client.post("/dang-nhap/", {"username": "admin", "password": "x"})
        self.assertEqual(response.status_code, 302)


@patch("portal.api_client.requests.request", side_effect=fake_request)
class PortalPageTests(LoggedInTestCase):
    def test_dashboard(self, mock_request):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total_students"], 1)
        self.assertEqual(response.context["open_theses"], 1)
        self.assertContains(response, "Đề tài gần đây")
        self.assertContains(response, "Quản trị")  # tên người đăng nhập trên thanh menu

    def test_student_list(self, mock_request):
        response = self.client.get("/sinh-vien/")
        self.assertContains(response, "Nguyễn Văn An")

    def test_registration_list_shows_names_from_other_services(self, mock_request):
        response = self.client.get("/dang-ky/")
        self.assertContains(response, "SV001 - Nguyễn Văn An")
        self.assertContains(response, "DT001 - Hệ thống quản lý thư viện")
        self.assertContains(response, "Chờ duyệt")

    def test_create_student_redirects(self, mock_request):
        data = {"student_code": "SV002", "full_name": "Trần Văn Bình", "email": "binh@x.vn"}
        response = self.client.post("/sinh-vien/them/", data)
        self.assertRedirects(response, "/sinh-vien/", fetch_redirect_response=False)

    def test_registration_error_from_api_is_shown(self, mock_request):
        response = self.client.post("/dang-ky/them/", {"student_id": 1, "thesis_id": 1})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Đề tài đã đóng, không thể đăng ký.")

    def test_access_token_is_sent_to_services(self, mock_request):
        self.client.get("/sinh-vien/")
        _, kwargs = mock_request.call_args
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer access-1")


class ServiceDownTests(LoggedInTestCase):
    @patch("portal.api_client.requests.request", side_effect=requests.ConnectionError())
    def test_dashboard_still_renders_when_services_down(self, mock_request):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Student Service không hoạt động")


class LoginTests(SimpleTestCase):
    def test_pages_require_login(self):
        response = self.client.get("/sinh-vien/")
        self.assertRedirects(response, "/dang-nhap/?next=%2Fsinh-vien%2F", fetch_redirect_response=False)

    def test_login_page_is_public(self):
        response = self.client.get("/dang-nhap/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Đăng nhập")

    def test_wrong_password(self):
        with patch("portal.api_client.requests.request",
                   return_value=make_response(401, {"detail": "x", "code": "invalid_credentials"})):
            response = self.client.post("/dang-nhap/", {"username": "admin", "password": "sai"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sai tên đăng nhập hoặc mật khẩu.")
        self.assertIsNone(self.client.session.get("access_token"))

    def test_locked_account(self):
        with patch("portal.api_client.requests.request",
                   return_value=make_response(403, {"detail": "x", "code": "account_locked"})):
            response = self.client.post("/dang-nhap/", {"username": "admin", "password": "sai"})
        self.assertContains(response, "Tài khoản tạm bị khóa")

    def test_identity_service_down(self):
        with patch("portal.api_client.requests.request", side_effect=requests.ConnectionError()):
            response = self.client.post("/dang-nhap/", {"username": "admin", "password": "x"})
        self.assertContains(response, "Identity Service không hoạt động")

    def test_login_redirects_to_next_but_not_to_other_site(self):
        with patch("portal.api_client.requests.request", side_effect=fake_request):
            response = self.client.post("/dang-nhap/?next=/de-tai/", {"username": "a", "password": "x"})
            self.assertRedirects(response, "/de-tai/", fetch_redirect_response=False)
            self.client.session.flush()
            response = self.client.post(
                "/dang-nhap/", {"username": "a", "password": "x", "next": "https://evil.example.com/"}
            )
            self.assertRedirects(response, "/", fetch_redirect_response=False)

    def test_session_does_not_store_password(self):
        with patch("portal.api_client.requests.request", side_effect=fake_request):
            self.client.post("/dang-nhap/", {"username": "admin", "password": "MatKhauBiMat"})
        self.assertNotIn("MatKhauBiMat", str(dict(self.client.session)))
        self.assertEqual(self.client.session["user"]["role"], "ADMIN")


class TokenRefreshTests(LoggedInTestCase):
    def test_expired_access_token_is_refreshed_automatically(self):
        calls = []

        def service(method, url, timeout=None, headers=None, **kwargs):
            calls.append(headers.get("Authorization"))
            if headers.get("Authorization") == "Bearer access-1":
                return make_response(401, {"detail": "Token has expired.", "code": "token_expired"})
            return make_response(200, STUDENTS)

        refreshed = make_response(200, {"access": "access-2", "refresh": "refresh-2",
                                        "token_type": "Bearer", "expires_in": 900})
        with patch("portal.api_client.requests.request", side_effect=service), \
                patch("portal.api_client.requests.post", return_value=refreshed) as mock_post:
            response = self.client.get("/sinh-vien/")
        self.assertContains(response, "Nguyễn Văn An")
        self.assertEqual(calls, ["Bearer access-1", "Bearer access-2"])
        self.assertEqual(mock_post.call_args.kwargs["json"], {"refresh": "refresh-1"})
        self.assertEqual(self.client.session["access_token"], "access-2")

    def test_refresh_service_failure_preserves_session_and_can_recover(self):
        for http_status in (429, 500, 502, 503):
            with self.subTest(status=http_status), \
                    patch("portal.api_client.requests.request", return_value=make_response(401, {})), \
                    patch("portal.api_client.requests.post", return_value=make_response(http_status, {})):
                response = self.client.get("/sinh-vien/")
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "Identity Service")
            self.assertEqual(self.client.session["access_token"], "access-1")
            self.assertEqual(self.client.session["refresh_token"], "refresh-1")
        with patch("portal.api_client.requests.request", side_effect=fake_request):
            self.assertContains(self.client.get("/sinh-vien/"), "Nguyễn Văn An")

    def test_refresh_fails_redirects_to_login(self):
        with patch("portal.api_client.requests.request",
                   return_value=make_response(401, {"detail": "x", "code": "token_expired"})), \
                patch("portal.api_client.requests.post",
                      return_value=make_response(401, {"detail": "x", "code": "token_revoked"})):
            response = self.client.get("/sinh-vien/")
        self.assertRedirects(response, "/dang-nhap/?next=%2Fsinh-vien%2F", fetch_redirect_response=False)
        self.assertIsNone(self.client.session.get("access_token"))

    def test_forbidden_shows_message(self):
        with patch("portal.api_client.requests.request",
                   return_value=make_response(403, {"detail": "You do not have permission."})):
            response = self.client.post("/sinh-vien/1/xoa/")
        self.assertRedirects(response, "/", fetch_redirect_response=False)


class LogoutAndPasswordTests(LoggedInTestCase):
    def test_logout_revokes_refresh_token_and_clears_session(self):
        with patch("portal.api_client.requests.request", side_effect=fake_request) as mock_request:
            response = self.client.post("/dang-xuat/")
        self.assertRedirects(response, "/dang-nhap/", fetch_redirect_response=False)
        method, url = mock_request.call_args.args
        self.assertIn("/api/auth/logout/", url)
        self.assertEqual(mock_request.call_args.kwargs["json"], {"refresh": "refresh-1"})
        self.assertIsNone(self.client.session.get("access_token"))
        self.assertEqual(self.client.get("/").status_code, 302)

    def test_logout_requires_post(self):
        self.assertEqual(self.client.get("/dang-xuat/").status_code, 405)

    def test_change_password_success_updates_tokens(self):
        new_pair = {"access": "access-9", "refresh": "refresh-9", "token_type": "Bearer", "expires_in": 900}
        with patch("portal.api_client.requests.request", return_value=make_response(200, new_pair)):
            response = self.client.post("/doi-mat-khau/", {
                "old_password": "cu", "new_password": "Moi-Pass!2026", "confirm_password": "Moi-Pass!2026",
            })
        self.assertRedirects(response, "/", fetch_redirect_response=False)
        self.assertEqual(self.client.session["access_token"], "access-9")

    def test_change_password_confirm_mismatch(self):
        response = self.client.post("/doi-mat-khau/", {
            "old_password": "cu", "new_password": "Moi-Pass!2026", "confirm_password": "khac",
        })
        self.assertContains(response, "Mật khẩu nhập lại không khớp.")

    def test_change_password_wrong_old_password(self):
        with patch("portal.api_client.requests.request",
                   return_value=make_response(400, {"old_password": ["Old password is incorrect."]})):
            response = self.client.post("/doi-mat-khau/", {
                "old_password": "sai", "new_password": "Moi-Pass!2026", "confirm_password": "Moi-Pass!2026",
            })
        self.assertContains(response, "Mật khẩu hiện tại không đúng.")


# ---------------------------------------------------------------- Theo vai trò (Giai đoạn 2)
def login_response(role, user_id, student_id=None):
    return {**LOGIN_OK, "user": {"id": user_id, "username": role.lower(), "full_name": f"Người {role}",
                                 "role": role, "student_id": student_id}}


class RoleTestCase(SimpleTestCase):
    role, user_id, student_id = "ADMIN", 1, None

    def setUp(self):
        with patch("portal.api_client.requests.request",
                   return_value=make_response(200, login_response(self.role, self.user_id, self.student_id))):
            self.client.post("/dang-nhap/", {"username": "x", "password": "x"})


THESES_ROLE = [
    {"id": 1, "thesis_code": "DT001", "title": "Đề tài GV 2", "description": "", "supervisor": "GV2",
     "supervisor_id": 2, "max_students": 2, "status": "OPEN"},
    {"id": 2, "thesis_code": "DT002", "title": "Đề tài GV 3", "description": "", "supervisor": "GV3",
     "supervisor_id": 3, "max_students": 2, "status": "OPEN"},
]


def role_fake(method, url, timeout=None, **kwargs):
    if method == "GET" and "/api/theses/" in url:
        return make_response(200, THESES_ROLE)
    if method == "GET" and "/api/users/" in url:
        return make_response(200, [{"id": 2, "username": "gv.tuan", "full_name": "TS. Tuấn", "role": "LECTURER",
                                    "student_id": None, "is_active": True, "locked_until": None}])
    return fake_request(method, url, timeout=timeout, **kwargs)


@patch("portal.api_client.requests.request", side_effect=role_fake)
class StudentRoleTests(RoleTestCase):
    role, user_id, student_id = "STUDENT", 10, 1

    def test_menu_for_student(self, mock_request):
        response = self.client.get("/")
        self.assertContains(response, "Đăng ký của tôi")
        self.assertNotContains(response, "Tài khoản</a>")

    def test_student_cannot_open_admin_pages(self, mock_request):
        for url in ("/sinh-vien/them/", "/de-tai/them/", "/tai-khoan/"):
            response = self.client.get(url)
            self.assertRedirects(response, "/", fetch_redirect_response=False)
        mock_request.assert_not_called()

    def test_thesis_list_shows_register_button_not_edit(self, mock_request):
        response = self.client.get("/de-tai/")
        self.assertContains(response, "/dang-ky/them/?thesis_id=1")
        self.assertNotContains(response, "/de-tai/1/sua/")

    def test_student_registers_for_self_only(self, mock_request):
        response = self.client.get("/dang-ky/them/?thesis_id=1")
        self.assertNotContains(response, 'name="student_id"')
        mock_request.reset_mock()
        mock_request.side_effect = lambda m, u, timeout=None, **kw: (
            make_response(201, {"id": 5, **kw["json"]}) if m == "POST" else role_fake(m, u, timeout, **kw)
        )
        response = self.client.post("/dang-ky/them/", {"thesis_id": 1, "student_id": 99})
        self.assertRedirects(response, "/dang-ky/", fetch_redirect_response=False)
        post_call = [c for c in mock_request.call_args_list if c.args[0] == "POST"][0]
        self.assertEqual(post_call.kwargs["json"], {"thesis_id": 1, "student_id": 1})

    def test_student_cannot_approve(self, mock_request):
        response = self.client.post("/dang-ky/1/trang-thai/", {"status": "APPROVED"})
        self.assertRedirects(response, "/", fetch_redirect_response=False)
        mock_request.assert_not_called()

    def test_cancel_button_for_pending(self, mock_request):
        response = self.client.get("/dang-ky/")
        self.assertContains(response, "Hủy đăng ký")
        self.assertNotContains(response, ">Duyệt<")


class StudentWithoutLinkTests(RoleTestCase):
    role, user_id, student_id = "STUDENT", 11, None

    def test_unlinked_student_cannot_register(self):
        response = self.client.get("/dang-ky/them/")
        self.assertRedirects(response, "/dang-ky/", fetch_redirect_response=False)


@patch("portal.api_client.requests.request", side_effect=role_fake)
class LecturerRoleTests(RoleTestCase):
    role, user_id = "LECTURER", 2

    def test_edit_button_only_on_own_thesis(self, mock_request):
        response = self.client.get("/de-tai/")
        self.assertContains(response, "/de-tai/1/sua/")
        self.assertNotContains(response, "/de-tai/2/sua/")

    def test_cannot_open_edit_form_of_other_lecturer(self, mock_request):
        mock_request.side_effect = lambda m, u, timeout=None, **kw: make_response(200, THESES_ROLE[1])
        response = self.client.get("/de-tai/2/sua/")
        self.assertRedirects(response, "/de-tai/", fetch_redirect_response=False)

    def test_lecturer_form_has_no_supervisor_choice(self, mock_request):
        response = self.client.get("/de-tai/them/")
        self.assertNotContains(response, 'name="supervisor_id"')

    def test_lecturer_sees_approve_buttons_but_cannot_register(self, mock_request):
        response = self.client.get("/dang-ky/")
        self.assertContains(response, "Duyệt")
        self.assertNotContains(response, "Hủy đăng ký")
        self.assertRedirects(self.client.get("/dang-ky/them/"), "/", fetch_redirect_response=False)

    def test_backend_403_is_shown_as_message(self, mock_request):
        mock_request.side_effect = None
        mock_request.return_value = make_response(403, {"detail": "You can only modify theses you supervise."})
        response = self.client.post("/de-tai/2/xoa/")
        self.assertRedirects(response, "/", fetch_redirect_response=False)


@patch("portal.api_client.requests.request", side_effect=role_fake)
class AdminAccountTests(RoleTestCase):
    def test_admin_thesis_form_lists_lecturers(self, mock_request):
        response = self.client.get("/de-tai/them/")
        self.assertContains(response, 'name="supervisor_id"')
        self.assertContains(response, "TS. Tuấn (gv.tuan)")

    def test_account_list(self, mock_request):
        response = self.client.get("/tai-khoan/")
        self.assertContains(response, "gv.tuan")
        self.assertContains(response, "Khóa tài khoản")

    def test_create_student_account_requires_student_link(self, mock_request):
        response = self.client.post("/tai-khoan/them/", {
            "username": "sv009", "email": "sv009@x.vn", "role": "STUDENT", "password": "Mua-Thu!2026x",
        })
        self.assertContains(response, "Tài khoản sinh viên cần gắn với một sinh viên.")

    def test_create_account_calls_identity(self, mock_request):
        mock_request.side_effect = lambda m, u, timeout=None, **kw: (
            make_response(201, {"id": 9}) if m == "POST" else role_fake(m, u, timeout, **kw)
        )
        response = self.client.post("/tai-khoan/them/", {
            "username": "gv02", "email": "gv02@x.vn", "role": "LECTURER", "password": "Mua-Thu!2026x",
        })
        self.assertRedirects(response, "/tai-khoan/", fetch_redirect_response=False)
        post_call = [c for c in mock_request.call_args_list if c.args[0] == "POST"][0]
        self.assertIn("/api/users/", post_call.args[1])
        self.assertIsNone(post_call.kwargs["json"]["student_id"])

    def test_deactivate_account(self, mock_request):
        mock_request.side_effect = None
        mock_request.return_value = make_response(200, {"id": 2, "is_active": False})
        response = self.client.post("/tai-khoan/2/trang-thai/", {"is_active": "false"})
        self.assertRedirects(response, "/tai-khoan/", fetch_redirect_response=False)
        self.assertEqual(mock_request.call_args.kwargs["json"], {"is_active": False})


# ---------------------------------------------------------------- Quy trình đăng ký (Giai đoạn 3)


def with_registrations(items):
    def fake(method, url, timeout=None, **kwargs):
        if method == "GET" and url.endswith("/api/registrations/"):
            return make_response(200, items)
        return role_fake(method, url, timeout=timeout, **kwargs)
    return fake


def delete_conflict(error):
    """DELETE trả 409, các request khác như bình thường (để follow redirect được)."""
    def fake(method, url, timeout=None, **kwargs):
        if method == "DELETE":
            return make_response(409, error)
        return role_fake(method, url, timeout=timeout, **kwargs)
    return fake


def reg(pk, status, **extra):
    return {"id": pk, "student_id": 1, "thesis_id": 1, "registered_at": "2026-10-04T10:00:00+07:00",
            "status": status, "reject_reason": "", **extra}


@patch("portal.api_client.requests.request", side_effect=role_fake)
class StudentWorkflowTests(RoleTestCase):
    role, user_id, student_id = "STUDENT", 10, 1


    def test_cancel_calls_cancel_endpoint(self, mock_request):
        mock_request.side_effect = None
        mock_request.return_value = make_response(200, reg(1, "CANCELLED"))
        response = self.client.post("/dang-ky/1/huy/")
        self.assertRedirects(response, "/dang-ky/", fetch_redirect_response=False)
        method, url = mock_request.call_args.args[:2]
        self.assertEqual(method, "POST")
        self.assertTrue(url.endswith("/api/registrations/1/cancel/"))

    def test_student_cannot_hard_delete(self, mock_request):
        response = self.client.post("/dang-ky/1/xoa/")
        self.assertRedirects(response, "/", fetch_redirect_response=False)
        mock_request.assert_not_called()


    def test_no_cancel_button_for_approved(self, mock_request):
        mock_request.side_effect = with_registrations([reg(1, "APPROVED")])
        response = self.client.get("/dang-ky/")
        self.assertNotContains(response, "/dang-ky/1/huy/")

    def test_cancelled_label_and_reject_reason(self, mock_request):
        mock_request.side_effect = with_registrations(
            [reg(1, "CANCELLED"), reg(2, "REJECTED", thesis_id=2, reject_reason="Trùng hướng")]
        )
        response = self.client.get("/dang-ky/")
        self.assertContains(response, "Đã hủy")
        self.assertContains(response, "Lý do: Trùng hướng")

    def test_limit_error_is_translated(self, mock_request):
        mock_request.side_effect = lambda m, u, timeout=None, **kw: (
            make_response(400, {"error": "Student already has an active registration"})
            if m == "POST" else role_fake(m, u, timeout, **kw)
        )
        response = self.client.post("/dang-ky/them/", {"thesis_id": 1})
        self.assertContains(response, "Sinh viên đã có đăng ký đang chờ duyệt hoặc đã được duyệt.")

    def test_detail_page_shows_notes_without_form(self, mock_request):
        response = self.client.get("/dang-ky/1/")
        self.assertContains(response, "Đã xong chương 1")
        self.assertNotContains(response, 'name="content"')


@patch("portal.api_client.requests.request", side_effect=role_fake)
class LecturerWorkflowTests(RoleTestCase):
    role, user_id = "LECTURER", 2

    def test_reject_requires_reason(self, mock_request):
        response = self.client.post("/dang-ky/1/trang-thai/", {"status": "REJECTED", "reject_reason": "  "})
        self.assertRedirects(response, "/dang-ky/", fetch_redirect_response=False)
        mock_request.assert_not_called()

    def test_reject_sends_reason(self, mock_request):
        mock_request.side_effect = None
        mock_request.return_value = make_response(200, reg(1, "REJECTED"))
        self.client.post("/dang-ky/1/trang-thai/", {"status": "REJECTED", "reject_reason": "Chưa đủ điều kiện"})
        self.assertEqual(mock_request.call_args.kwargs["json"],
                         {"status": "REJECTED", "reject_reason": "Chưa đủ điều kiện"})

    def test_reject_form_has_reason_input(self, mock_request):
        response = self.client.get("/dang-ky/")
        self.assertContains(response, 'name="reject_reason"')
        self.assertNotContains(response, "/dang-ky/1/huy/")

    def test_no_actions_on_cancelled(self, mock_request):
        mock_request.side_effect = with_registrations([reg(1, "CANCELLED")])
        response = self.client.get("/dang-ky/")
        self.assertNotContains(response, ">Duyệt<")
        self.assertNotContains(response, 'name="reject_reason"')

    def test_add_note_on_approved(self, mock_request):
        def fake(m, u, timeout=None, **kw):
            if m == "GET" and u.endswith("/api/registrations/1/"):
                return make_response(200, reg(1, "APPROVED"))
            if m == "POST":
                return make_response(201, {"id": 2})
            return role_fake(m, u, timeout, **kw)
        mock_request.side_effect = fake
        response = self.client.get("/dang-ky/1/")
        self.assertContains(response, 'name="content"')
        response = self.client.post("/dang-ky/1/", {"content": "Tốt", "progress": 50})
        self.assertRedirects(response, "/dang-ky/1/", fetch_redirect_response=False)
        post_call = [c for c in mock_request.call_args_list if c.args[0] == "POST"][0]
        self.assertTrue(post_call.args[1].endswith("/api/registrations/1/notes/"))
        self.assertEqual(post_call.kwargs["json"], {"content": "Tốt", "progress": 50})

    def test_no_note_form_when_pending(self, mock_request):
        response = self.client.get("/dang-ky/1/")
        self.assertNotContains(response, 'name="content"')
        self.assertContains(response, "Chỉ ghi nhận xét / tiến độ khi đăng ký đã được duyệt.")

    def test_lower_max_students_error_translated(self, mock_request):
        def fake(m, u, timeout=None, **kw):
            if m == "GET" and u.endswith("/api/theses/1/"):
                return make_response(200, THESES_ROLE[0])
            if m == "PATCH":
                return make_response(400, {"max_students": [
                    "Cannot be lower than the number of active registrations (2)."]})
            return role_fake(m, u, timeout, **kw)
        mock_request.side_effect = fake
        response = self.client.post("/de-tai/1/sua/", {
            "thesis_code": "DT001", "title": "X", "max_students": 1, "status": "OPEN"})
        self.assertContains(response, "Không được thấp hơn số đăng ký còn hiệu lực (2).")


@patch("portal.api_client.requests.request", side_effect=role_fake)
class AdminWorkflowTests(RoleTestCase):
    def test_admin_can_cancel_approved_and_delete(self, mock_request):
        mock_request.side_effect = with_registrations([reg(1, "APPROVED")])
        response = self.client.get("/dang-ky/")
        self.assertContains(response, "/dang-ky/1/huy/")
        self.assertContains(response, "/dang-ky/1/xoa/")

    def test_delete_student_with_active_registrations(self, mock_request):
        mock_request.side_effect = delete_conflict({"error": "Student has active registrations"})
        response = self.client.post("/sinh-vien/1/xoa/", follow=True)
        self.assertContains(response, "Sinh viên đang có đăng ký còn hiệu lực")

    def test_delete_thesis_with_active_registrations(self, mock_request):
        mock_request.side_effect = None
        mock_request.return_value = make_response(409, {"error": "Thesis has active registrations"})
        response = self.client.post("/de-tai/1/xoa/")
        self.assertRedirects(response, "/de-tai/", fetch_redirect_response=False)


class ActiveCountTests(SimpleTestCase):
    def test_cancelled_and_rejected_are_not_counted(self):
        from portal.views import count_active_registrations
        items = [reg(1, "PENDING"), reg(2, "APPROVED"), reg(3, "REJECTED"), reg(4, "CANCELLED")]
        self.assertEqual(count_active_registrations(items), {1: 2})
