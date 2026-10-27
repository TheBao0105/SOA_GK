from unittest.mock import patch
from . import tests as fixtures
from . import views
from .models import Registration


class RegistrationRaceTests(fixtures.RegistrationTestCase):
    @patch("registrations.services.external_api.requests.get",side_effect=fixtures.fake_get)
    def test_stale_cancelled_registration_cannot_be_reactivated_twice(self,remote):
        registration=Registration.objects.create(student_id=1,thesis_id=1,status="CANCELLED")
        run_locked=views.run_locked
        def concurrent_activation(student_id,thesis_id,work):
            Registration.objects.filter(pk=registration.pk).update(status="PENDING")
            return run_locked(student_id,thesis_id,work)
        with patch("registrations.views.run_locked",side_effect=concurrent_activation):
            response=self.client.post("/api/registrations/",{"student_id":1,"thesis_id":1},format="json")
        self.assertEqual(response.status_code,400)
        self.assertEqual(response.data["error"],"Student has already registered for this thesis")
        self.assertEqual(Registration.objects.count(),1)
