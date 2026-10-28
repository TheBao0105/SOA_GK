from unittest.mock import patch
from config.testing import AuthenticatedAPITestCase
from .models import Registration
from .tests import fake_get_rbac


@patch("registrations.services.external_api.requests.get", side_effect=fake_get_rbac)
class RegistrationWithoutScheduleTests(AuthenticatedAPITestCase):
    def test_create_then_student_cancel_without_any_schedule(self, remote):
        self.login_as("STUDENT", user_id=10, student_id=1)
        response = self.client.post("/api/registrations/", {"student_id": 1, "thesis_id": 1}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertNotIn("period", response.data)
        pk = response.data["id"]
        self.assertEqual(self.client.post(f"/api/registrations/{pk}/cancel/").status_code, 200)
        self.assertEqual(self.client.post("/api/registrations/", {"student_id": 1, "thesis_id": 2}, format="json").status_code, 201)
        self.assertEqual(Registration.objects.filter(status="PENDING").count(), 1)

    def test_removed_api_and_schema(self, remote):
        for path in ("/api/periods/", "/api/periods/current/", "/api/periods/1/"):
            self.assertEqual(self.client.get(path).status_code, 404)
        response = self.client.get("/api/schema/?format=json")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("/api/periods/", response.content.decode())
        self.assertIn("/api/grading/grades/", response.content.decode())
