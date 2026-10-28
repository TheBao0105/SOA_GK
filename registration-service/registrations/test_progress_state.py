from unittest.mock import patch
from config.testing import AuthenticatedAPITestCase
from .models import Registration, ProgressNote
from .views import ProgressNoteListCreateView


class ProgressStateTests(AuthenticatedAPITestCase):
    def test_status_changed_after_scope_check_cannot_receive_progress(self):
        registration = Registration.objects.create(student_id=1, thesis_id=1, status="APPROVED")

        def status_changed(view):
            stale = Registration.objects.get(pk=registration.pk)
            Registration.objects.filter(pk=registration.pk).update(status="CANCELLED")
            return stale

        with patch.object(ProgressNoteListCreateView, "get_registration", status_changed):
            response = self.client.post(f"/api/registrations/{registration.pk}/notes/",
                                        {"content":"Đã hoàn thành", "progress":100}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(ProgressNote.objects.exists())
