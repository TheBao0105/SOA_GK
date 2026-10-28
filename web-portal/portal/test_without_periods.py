from unittest.mock import patch
from .tests import RoleTestCase, role_fake


@patch("portal.api_client.requests.request", side_effect=role_fake)
class RegistrationWithoutSchedulePortalTests(RoleTestCase):
    role, user_id, student_id = "STUDENT", 10, 1

    def test_dashboard_and_registration_pages_never_call_schedule_api(self, remote):
        for path in ("/", "/dang-ky/", "/dang-ky/them/", "/dang-ky/1/"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertNotContains(response, "Đợt đăng ký")
            self.assertNotContains(response, "chưa có đợt")
        self.assertFalse(any('/api/periods/' in call.args[1] for call in remote.call_args_list))

    def test_pending_student_registration_has_cancel_button_without_schedule(self, remote):
        response = self.client.get("/dang-ky/")
        self.assertContains(response, "/dang-ky/1/huy/")

    def test_obsolete_portal_urls_return_404(self, remote):
        for path in ("/dot-dang-ky/", "/dot-dang-ky/them/", "/dot-dang-ky/1/sua/"):
            self.assertEqual(self.client.get(path).status_code, 404)
        remote.assert_not_called()
