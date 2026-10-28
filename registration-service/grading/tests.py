from unittest.mock import patch
import requests
from config.testing import AuthenticatedAPITestCase
from registrations.models import Registration
from .models import Grade, GradeHistory

BASE = "/api/grading/grades/"


def theses(url, headers=None, timeout=None):
    from registrations.tests import make_response
    return make_response(200, [{"id":1}])


@patch("registrations.services.external_api.requests.get", side_effect=theses)
class DirectGradeTests(AuthenticatedAPITestCase):
    def setUp(self):
        super().setUp()
        self.reg = Registration.objects.create(student_id=1, thesis_id=1, status="APPROVED")
        self.other = Registration.objects.create(student_id=2, thesis_id=2, status="APPROVED")

    def score(self, value="8.5", registration=None, comment="Tốt"):
        return self.client.post(BASE, {"registration":registration or self.reg.pk,"score":value,"comment":comment},format="json")

    def lecturer(self):
        self.login_as("LECTURER", user_id=2, full_name="GV hướng dẫn")

    def test_lecturer_enters_score_directly_and_student_sees_it_immediately(self, remote):
        self.lecturer()
        response = self.score()
        self.assertEqual(response.status_code,201)
        self.assertEqual(response.data["score"],"8.50")
        self.assertEqual(response.data["lecturer_id"],2)
        self.login_as("STUDENT",user_id=5,student_id=1)
        rows=self.client.get(BASE).data
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]["score"],"8.50")

    def test_score_update_reuses_record_and_records_before_after(self, remote):
        self.lecturer()
        first=self.score("0")
        second=self.score("10",comment="Sửa lại")
        self.assertEqual(second.status_code,200)
        self.assertEqual(first.data["id"],second.data["id"])
        self.assertEqual(Grade.objects.count(),1)
        self.assertEqual(GradeHistory.objects.count(),2)
        event=GradeHistory.objects.first()
        self.assertEqual(event.detail["before"]["score"],"0.00")
        self.assertEqual(event.detail["after"]["score"],"10.00")

    def test_invalid_scores_do_not_write(self, remote):
        self.lecturer()
        for value in ("-1","10.01","NaN","Infinity","1.001","",None,True):
            with self.subTest(value=value):
                self.assertEqual(self.score(value).status_code,400)
        self.assertEqual(Grade.objects.count(),0)
        self.assertEqual(GradeHistory.objects.count(),0)

    def test_other_lecturer_thesis_cannot_be_graded(self, remote):
        self.lecturer()
        self.assertEqual(self.score(registration=self.other.pk).status_code,404)
        self.assertEqual(Grade.objects.count(),0)
        self.assertIn("supervisor_id=2",remote.call_args.args[0])
        self.assertIn("Authorization",remote.call_args.kwargs["headers"])

    def test_only_approved_registration_can_be_graded(self, remote):
        self.lecturer()
        for state in ("PENDING","REJECTED","CANCELLED"):
            self.reg.status=state
            self.reg.save()
            self.assertEqual(self.score().status_code,400)
        self.assertEqual(Grade.objects.count(),0)

    def test_student_service_cannot_write(self, remote):
        for role in ("STUDENT","SERVICE"):
            self.login_as(role,student_id=1 if role=="STUDENT" else None)
            self.assertEqual(self.score().status_code,403)
        self.assertEqual(Grade.objects.count(),0)

    def test_read_scope_and_history_permissions(self, remote):
        self.lecturer()
        grade=self.score().data
        other=Grade.objects.create(registration=self.other,score="9",lecturer_id=3)
        self.assertEqual([g["id"] for g in self.client.get(BASE).data],[grade["id"]])
        self.assertEqual(self.client.get(f"{BASE}{other.pk}/").status_code,404)
        self.assertEqual(self.client.get(f"{BASE}{grade['id']}/history/").status_code,200)
        self.login_as("STUDENT",user_id=6,student_id=2)
        self.assertEqual([g["id"] for g in self.client.get(BASE).data],[other.pk])
        self.assertEqual(self.client.get(f"{BASE}{grade['id']}/").status_code,404)
        self.assertEqual(self.client.get(f"{BASE}{other.pk}/history/").status_code,403)
        self.login_as("ADMIN")
        self.assertEqual(len(self.client.get(BASE).data),2)

    def test_authentication_required(self, remote):
        self.client.credentials()
        self.assertEqual(self.client.get(BASE).status_code,401)
        self.assertEqual(self.score().status_code,401)
        remote.assert_not_called()

    def test_service_token_cannot_read_grades(self, remote):
        self.login_as("SERVICE")
        self.assertEqual(self.client.get(BASE).status_code,403)

    def test_upstream_outage_fails_closed_without_writing(self, remote):
        self.lecturer()
        remote.side_effect=requests.Timeout
        self.assertEqual(self.score().status_code,503)
        self.assertEqual(Grade.objects.count(),0)

    def test_grade_protects_registration_against_delete_cancel_and_reject(self, remote):
        self.lecturer()
        self.score()
        self.login_as("ADMIN")
        url=f"/api/registrations/{self.reg.pk}/"
        self.assertEqual(self.client.delete(url).status_code,409)
        self.assertEqual(self.client.post(url+"cancel/").status_code,409)
        self.assertEqual(self.client.patch(url,{"status":"REJECTED","reject_reason":"X"}).status_code,400)

    def test_old_workflow_is_removed(self, remote):
        for path in ("/api/grading/periods/","/api/grading/assessments/"):
            self.assertEqual(self.client.get(path).status_code,404)
        self.assertEqual(self.client.get('/api/schema/?format=json').status_code,200)

    def test_cannot_patch_grade_to_bypass_validated_save_flow(self, remote):
        self.lecturer()
        grade=self.score().data
        url=f"{BASE}{grade['id']}/"
        self.assertEqual(self.client.patch(url,{"score":"10"}).status_code,403)

    def test_admin_can_create_edit_delete_and_regrade_with_history(self, remote):
        first=self.score()
        self.assertEqual(first.status_code,201)
        pk=first.data['id']
        self.assertEqual(self.score('9').status_code,200)
        self.assertEqual(self.client.delete(f'{BASE}{pk}/').status_code,204)
        self.assertEqual(Grade.objects.count(),0)
        self.assertEqual(GradeHistory.objects.filter(action='DELETED').count(),1)
        self.assertEqual(GradeHistory.objects.filter(grade__isnull=False).count(),0)
        self.assertEqual(GradeHistory.objects.filter(action='DELETED').get().detail['before']['score'],'9.00')
        saved=self.score('7.5')
        self.assertEqual(saved.status_code,201)
        history=self.client.get(f"{BASE}{saved.data['id']}/history/").data
        self.assertEqual(len(history),4)
        self.assertTrue(any(e['action']=='DELETED' for e in history))

    def test_lecturer_can_delete_own_grade_but_not_another_thesis_grade(self, remote):
        self.lecturer()
        own=self.score().data['id']
        other=Grade.objects.create(registration=self.other,score='9',lecturer_id=3)
        self.assertEqual(self.client.delete(f'{BASE}{other.pk}/').status_code,404)
        self.assertEqual(self.client.delete(f'{BASE}{own}/').status_code,204)
        self.assertTrue(Grade.objects.filter(pk=other.pk).exists())
        self.assertEqual(self.client.delete(f'{BASE}{own}/').status_code,404)

    def test_student_cannot_delete_even_own_grade(self, remote):
        own=self.score().data['id']
        self.login_as('STUDENT',user_id=5,student_id=1)
        self.assertEqual(self.client.delete(f'{BASE}{own}/').status_code,403)
        self.assertTrue(Grade.objects.filter(pk=own).exists())
