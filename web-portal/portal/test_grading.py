from unittest.mock import patch
from django.test import Client
from . import tests as fixtures
from .grading_forms import DEFAULT_CRITERIA

PERIOD={"id":1,"name":"Đợt chấm","start_at":"2026-01-01T00:00:00+07:00","end_at":"2027-01-01T00:00:00+07:00","is_active":True,"is_open":True,"criteria":DEFAULT_CRITERIA}
ASSESSMENT={"id":1,"registration":1,"student_id":1,"thesis_id":1,"period":1,"period_name":"Đợt chấm","criteria":DEFAULT_CRITERIA,"status":"UNGRADED","final_score":None,"published_at":None,"assignments":[{"id":1,"lecturer_id":2,"lecturer_name":"GV A","scores":{},"comment":"<script>alert(1)</script>","submitted_at":None,"total":None}]}


def remote(method,url,**kwargs):
    if method=="GET":
        if url.endswith("/api/grading/assessments/1/history/"):
            return fixtures.make_response(200,[])
        if url.endswith("/api/grading/assessments/1/"):
            return fixtures.make_response(200,ASSESSMENT)
        if url.endswith("/api/grading/assessments/"):
            return fixtures.make_response(200,[ASSESSMENT])
        if url.endswith("/api/grading/periods/1/"):
            return fixtures.make_response(200,PERIOD)
        if url.endswith("/api/grading/periods/"):
            return fixtures.make_response(200,[PERIOD])
        if url.endswith("/api/users/2/"):
            return fixtures.make_response(200,{"id":2,"username":"gv","full_name":"GV A","email":"gv@test.local","role":"LECTURER","student_id":None,"is_active":True})
        if url.endswith("/api/users/"):
            return fixtures.make_response(200,[{"id":2,"username":"gv","full_name":"GV A","is_active":True}])
        if url.endswith("/api/audit-logs/"):
            return fixtures.make_response(200,[{"created_at":"2026-10-27","action":"LOGIN_SUCCESS","username":"admin","actor_id":1,"detail":""}])
        if url.endswith("/api/auth/me/"):
            return fixtures.make_response(200,{"id":1,"username":"admin","full_name":"Admin","email":"admin@example.com"})
    return fixtures.fake_request(method,url,**kwargs)


@patch("portal.api_client.requests.request",side_effect=remote)
class GradingPortalTests(fixtures.LoggedInTestCase):
    def role(self,role,user_id=1):
        session=self.client.session
        user=dict(session['user'])
        user.update(role=role,id=user_id)
        session['user']=user
        session.save()
        self.client.cookies['sessionid']=session.session_key

    def test_admin_pages_render(self,mock):
        for url in ('/cham-diem/','/cham-diem/them/','/cham-diem/1/','/dot-cham-diem/','/dot-cham-diem/them/','/dot-cham-diem/1/sua/','/ho-so/','/nhat-ky/','/tai-khoan/2/sua/'):
            response=self.client.get(url)
            self.assertEqual(response.status_code,200,url)
            self.assertContains(response,'csrfmiddlewaretoken')

    def test_student_cannot_open_admin_pages_or_mutate_grades(self,mock):
        self.role('STUDENT',4)
        for url in ('/cham-diem/them/','/dot-cham-diem/them/','/nhat-ky/'):
            self.assertEqual(self.client.get(url).status_code,302)
        count=mock.call_count
        self.assertEqual(self.client.post('/cham-diem/1/',{'action':'publish'}).status_code,302)
        self.assertFalse(any(call.args[0]=='POST' for call in mock.call_args_list[count:]))

    def test_lecturer_score_form_sends_decimal_strings(self,mock):
        self.role('LECTURER',2)
        with patch('portal.api_client.grading_action',return_value={}) as action:
            data={'action':'scores','submit':'true','comment':'Tốt',**{'score_'+c['code']:'8.25' for c in DEFAULT_CRITERIA}}
            self.assertEqual(self.client.post('/cham-diem/1/',data).status_code,302)
            action.assert_called_once()
            self.assertEqual(action.call_args.args[2]['scores']['completion'],'8.25')
            self.assertTrue(action.call_args.args[2]['submit'])

    def test_lecturer_cannot_publish(self,mock):
        self.role('LECTURER',2)
        with patch('portal.api_client.grading_action') as action:
            self.client.post('/cham-diem/1/',{'action':'publish'})
            action.assert_not_called()

    def test_score_validation_preserves_form(self,mock):
        self.role('LECTURER',2)
        response=self.client.post('/cham-diem/1/',{'action':'scores','score_completion':'11'})
        self.assertEqual(response.status_code,200)
        self.assertTrue(response.context['score_form'].errors)

    def test_comments_are_escaped(self,mock):
        response=self.client.get('/cham-diem/1/')
        self.assertContains(response,'&lt;script&gt;alert(1)&lt;/script&gt;')
        self.assertNotContains(response,'<script>alert(1)</script>')

    def test_profile_updates_session_name(self,mock):
        with patch('portal.api_client.my_profile',side_effect=[{'email':'admin@example.com','full_name':'Admin'}, {'id':1,'username':'admin','full_name':'Tên mới','email':'new@example.com'}]):
            self.assertEqual(self.client.post('/ho-so/',{'full_name':'Tên mới','email':'new@example.com'}).status_code,302)
            self.assertEqual(self.client.session['user']['full_name'],'Tên mới')

    def test_csrf_required_for_grade_changes(self,mock):
        client=Client(enforce_csrf_checks=True)
        client.cookies=self.client.cookies
        self.assertEqual(client.post('/cham-diem/1/',{'action':'publish'}).status_code,403)


    def test_account_edit_omits_empty_password(self,mock):
        with patch('portal.api_client.users.update',return_value={}) as update:
            response=self.client.post('/tai-khoan/2/sua/',{'username':'gv','email':'gv@test.local','full_name':'Tên mới','role':'LECTURER','student_id':'','password':''})
            self.assertEqual(response.status_code,302)
            self.assertNotIn('password',update.call_args.args[1])
