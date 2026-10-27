from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch
import requests
from django.utils import timezone
from config.testing import AuthenticatedAPITestCase
from registrations.models import Registration
from .models import Assessment, GradeEvent, GradingAssignment, GradingPeriod

CRITERIA = [{"code": "work", "name": "Chức năng", "weight": "40"}, {"code": "design", "name": "Kỹ thuật", "weight": "30"}, {"code": "report", "name": "Báo cáo", "weight": "20"}, {"code": "defense", "name": "Bảo vệ", "weight": "10"}]
BASE = "/api/grading/"


class GradingTests(AuthenticatedAPITestCase):
    def setUp(self):
        super().setUp()
        now = timezone.now()
        self.period = GradingPeriod.objects.create(name="Đợt test", start_at=now-timedelta(days=1), end_at=now+timedelta(days=1), criteria=CRITERIA)
        self.reg = Registration.objects.create(student_id=1, thesis_id=1, status="APPROVED")
        self.assessment = Assessment.objects.create(registration=self.reg, period=self.period, created_by=1)
        self.url = f"{BASE}assessments/{self.assessment.pk}/"
        self.mark = GradingAssignment.objects.create(assessment=self.assessment, lecturer_id=2, lecturer_name="GV 2")

    def score(self, value="8", submit=True):
        return self.client.post(self.url+"scores/", {"scores": {c["code"]: value for c in CRITERIA}, "comment": "Nhận xét", "submit": submit}, format="json")

    def submitted(self):
        self.login_as("LECTURER", user_id=2)
        self.assertEqual(self.score().status_code, 200)
        self.login_as("ADMIN")

    def test_authentication_required(self):
        self.client.credentials()
        self.assertEqual(self.client.get(BASE+"assessments/").status_code, 401)
        self.assertEqual(self.client.post(BASE+"periods/", {}, format="json").status_code, 401)

    def test_weighted_score_uses_decimal(self):
        self.login_as("LECTURER", user_id=2)
        r = self.client.post(self.url+"scores/", {"scores": {"work": "8", "design": "7", "report": "9", "defense": "10"}, "submit": True}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Decimal(r.data["final_score"]), Decimal("8.10"))
        self.assertEqual(r.data["status"], "GRADED")

    def test_multiple_examiners_average_and_all_must_submit(self):
        GradingAssignment.objects.create(assessment=self.assessment, lecturer_id=3, lecturer_name="GV 3")
        self.submitted()
        self.assertEqual(self.client.post(self.url+"publish/").status_code, 400)
        self.login_as("LECTURER", user_id=3)
        r = self.score("9")
        self.assertEqual(Decimal(r.data["final_score"]), Decimal("8.50"))

    def test_draft_cannot_publish(self):
        self.login_as("LECTURER", user_id=2)
        r = self.score(submit=False)
        self.assertEqual(r.data["status"], "IN_PROGRESS")
        self.assertIsNone(r.data["final_score"])
        self.login_as("ADMIN")
        self.assertEqual(self.client.post(self.url+"publish/").status_code, 400)

    def test_unassigned_lecturer_cannot_read_grade_or_history(self):
        self.login_as("LECTURER", user_id=9)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.score().status_code, 404)
        self.assertEqual(self.client.get(self.url+"history/").status_code, 404)
        self.assertEqual(self.client.get(BASE+"assessments/").data, [])

    def test_admin_cannot_impersonate_examiner(self):
        self.assertEqual(self.score().status_code, 403)

    def test_student_sees_only_own_published_result(self):
        self.login_as("STUDENT", user_id=4, student_id=1)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.client.get(BASE+"assessments/").data, [])
        self.submitted()
        self.assertEqual(self.client.post(self.url+"publish/").status_code, 200)
        self.login_as("STUDENT", user_id=4, student_id=1)
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertEqual(self.client.get(self.url+"history/").status_code, 403)
        self.login_as("STUDENT", user_id=5, student_id=2)
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_student_cannot_grade_assign_publish_or_create(self):
        self.login_as("STUDENT", user_id=4, student_id=1)
        for suffix in ("scores/", "assign/", "publish/", "reopen/"):
            self.assertEqual(self.client.post(self.url+suffix, {}, format="json").status_code, 403)
        self.assertEqual(self.client.post(BASE+"assessments/", {}).status_code, 403)

    def test_lecturer_cannot_publish_reopen_assign_or_create(self):
        self.login_as("LECTURER", user_id=2)
        for suffix in ("assign/", "publish/", "reopen/"):
            self.assertEqual(self.client.post(self.url+suffix, {}, format="json").status_code, 403)
        self.assertEqual(self.client.post(BASE+"assessments/", {}).status_code, 403)

    def test_scores_out_of_range_nan_unknown_and_missing_rejected(self):
        self.login_as("LECTURER", user_id=2)
        for value in ("-1", "10.01", "NaN", "Infinity", "1.001"):
            self.assertEqual(self.score(value).status_code, 400)
        for scores in ({"work": "5"}, {"unknown": "5"}):
            self.assertEqual(self.client.post(self.url+"scores/", {"scores": scores, "submit": True}, format="json").status_code, 400)
        self.assertEqual(GradeEvent.objects.count(), 0)

    def test_submitted_score_is_locked_until_admin_reopens(self):
        self.submitted()
        self.login_as("LECTURER", user_id=2)
        self.assertEqual(self.score("9").status_code, 400)
        self.login_as("ADMIN")
        self.assertEqual(self.client.post(self.url+"reopen/", {"reason": ""}).status_code, 400)
        self.assertEqual(self.client.post(self.url+"reopen/", {"reason": "Sửa theo biên bản"}).status_code, 200)
        self.login_as("LECTURER", user_id=2)
        self.assertEqual(self.score("9").status_code, 200)
        event = GradeEvent.objects.filter(action="SUBMITTED").first()
        self.assertEqual(event.detail["before"]["scores"]["work"], "8.00")
        self.assertEqual(event.detail["after"]["scores"]["work"], "9.00")

    def test_published_score_locked_and_reopen_hides_result(self):
        self.submitted()
        self.client.post(self.url+"publish/")
        self.login_as("LECTURER", user_id=2)
        self.assertEqual(self.score().status_code, 400)
        self.login_as("ADMIN")
        self.client.post(self.url+"reopen/", {"reason": "Phúc khảo"})
        self.assessment.refresh_from_db()
        self.assertIsNone(self.assessment.published_at)
        self.assertIsNone(self.assessment.final_score)
        self.login_as("STUDENT", user_id=4, student_id=1)
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_closed_or_disabled_period_blocks_grading(self):
        self.login_as("LECTURER", user_id=2)
        self.period.is_active=False
        self.period.save()
        self.assertEqual(self.score().status_code, 400)
        self.period.is_active=True
        self.period.end_at=timezone.now()-timedelta(seconds=1)
        self.period.save()
        self.assertEqual(self.score().status_code, 400)

    def test_criteria_validated_and_frozen(self):
        url=f"{BASE}periods/{self.period.pk}/"
        for criteria in ([], [{"code":"x","name":"X","weight":99}], [{"code":"x","name":"X","weight":"NaN"}], [{"code":"x","name":"X","weight":50}]*2):
            self.assertEqual(self.client.patch(url, {"criteria":criteria}, format="json").status_code, 400)
        self.assertEqual(self.client.patch(url, {"criteria":[{"code":"new","name":"Mới","weight":100}]}, format="json").status_code, 400)
        self.assertEqual(self.client.patch(url, {"is_active":False}, format="json").status_code, 200)

    def test_period_creation_and_date_validation(self):
        now=timezone.now()
        body={"name":"Mới","start_at":now.isoformat(),"end_at":(now+timedelta(days=1)).isoformat(),"criteria":CRITERIA}
        self.assertEqual(self.client.post(BASE+"periods/", body, format="json").status_code, 201)
        body["end_at"]=now.isoformat()
        self.assertEqual(self.client.post(BASE+"periods/", body, format="json").status_code, 400)
        self.login_as("LECTURER",user_id=2)
        self.assertEqual(self.client.post(BASE+"periods/", body, format="json").status_code, 403)

    def test_create_requires_approved_and_unique_registration(self):
        body={"period":self.period.pk,"registration":self.reg.pk}
        self.assertEqual(self.client.post(BASE+"assessments/",body).status_code,400)
        self.reg=Registration.objects.create(student_id=2,thesis_id=1,status="PENDING")
        body["registration"]=self.reg.pk
        self.assertEqual(self.client.post(BASE+"assessments/",body).status_code,400)
        self.reg.status="APPROVED"
        self.reg.save()
        self.assertEqual(self.client.post(BASE+"assessments/",body).status_code,201)

    @patch("grading.views._get_json")
    def test_assignment_validates_identity_and_forwards_token(self, remote):
        remote.return_value={"id":3,"role":"LECTURER","is_active":True,"full_name":"GV 3"}
        r=self.client.post(self.url+"assign/",{"lecturer_ids":[3]},format="json")
        self.assertEqual(r.status_code,200)
        self.assertTrue(remote.call_args.args[2])
        self.assertEqual(list(self.assessment.assignments.values_list("lecturer_id",flat=True)),[3])
        remote.return_value={"id":4,"role":"STUDENT","is_active":True}
        self.assertEqual(self.client.post(self.url+"assign/",{"lecturer_ids":[4]},format="json").status_code,400)
        remote.return_value={"id":4,"role":"LECTURER","is_active":False}
        self.assertEqual(self.client.post(self.url+"assign/",{"lecturer_ids":[4]},format="json").status_code,400)

    @patch("registrations.services.external_api.requests.get",side_effect=requests.Timeout)
    def test_identity_timeout_preserves_assignments(self, remote):
        self.assertEqual(self.client.post(self.url+"assign/",{"lecturer_ids":[3]},format="json").status_code,503)
        self.assertTrue(self.assessment.assignments.filter(lecturer_id=2).exists())

    def test_registration_with_grading_cannot_cancel_delete_or_reject(self):
        url=f"/api/registrations/{self.reg.pk}/"
        self.assertEqual(self.client.post(url+"cancel/").status_code,409)
        self.assertEqual(self.client.delete(url).status_code,409)
        self.assertEqual(self.client.patch(url,{"status":"REJECTED","reject_reason":"X"}).status_code,400)
        self.reg.refresh_from_db()
        self.assertEqual(self.reg.status,"APPROVED")

    def test_service_token_denied_and_history_immutable(self):
        self.login_as("SERVICE")
        self.assertEqual(self.client.get(BASE+"assessments/").status_code,403)
        self.login_as("ADMIN")
        self.assertEqual(self.client.delete(self.url).status_code,403)
        self.assertEqual(self.client.patch(self.url,{"final_score":"10"}).status_code,403)

    def test_full_publish_workflow_records_actor_and_history(self):
        self.submitted()
        r=self.client.post(self.url+"publish/")
        self.assertEqual(r.status_code,200)
        self.assertEqual(r.data["published_by"],1)
        self.assertIsNotNone(r.data["published_at"])
        events=self.client.get(self.url+"history/").data
        self.assertEqual(events[0]["action"],"PUBLISHED")
        self.assertEqual(events[0]["detail"]["final_score"],"8.00")


    def test_equivalent_weight_format_does_not_block_period_date_edit(self):
        criteria=[{**c,"weight":c["weight"]+".00"} for c in CRITERIA]
        response=self.client.patch(f"{BASE}periods/{self.period.pk}/",{"criteria":criteria,"end_at":(timezone.now()+timedelta(days=2)).isoformat()},format="json")
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.data["criteria"][0]["weight"],"40")


    @patch("grading.views._get_json")
    def test_invalid_examiner_response_cannot_change_assignments(self,remote):
        for payload in ({},[],{"id":99,"role":"LECTURER","is_active":True},{"id":3,"role":"LECTURER","is_active":"yes"}):
            remote.return_value=payload
            with self.subTest(payload=payload):
                self.assertEqual(self.client.post(self.url+"assign/",{"lecturer_ids":[3]},format="json").status_code,503)
                self.assertTrue(self.assessment.assignments.filter(lecturer_id=2).exists())
