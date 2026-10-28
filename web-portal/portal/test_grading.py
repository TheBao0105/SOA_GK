from unittest.mock import patch
from django.test import Client
from . import tests as fixtures

REGISTRATION={"id":1,"student_id":1,"thesis_id":1,"status":"APPROVED"}
GRADE={"id":1,"registration":1,"student_id":1,"thesis_id":1,"score":"8.50","comment":"<script>alert(1)</script>","lecturer_id":2,"lecturer_name":"GV A"}


def remote(method,url,**kwargs):
    if method=="GET":
        if url.endswith('/api/grading/grades/1/history/'):
            return fixtures.make_response(200,[])
        if url.endswith('/api/registrations/1/'):
            return fixtures.make_response(200,REGISTRATION)
        if url.endswith('/api/registrations/'):
            return fixtures.make_response(200,[REGISTRATION])
        if url.endswith('/api/grading/grades/'):
            return fixtures.make_response(200,[GRADE])
        if url.endswith('/api/users/2/'):
            return fixtures.make_response(200,{"id":2,"username":"gv","full_name":"GV A","email":"gv@test.local","role":"LECTURER","student_id":None,"is_active":True})
        if url.endswith('/api/audit-logs/'):
            return fixtures.make_response(200,[])
        if url.endswith('/api/auth/me/'):
            return fixtures.make_response(200,{"id":1,"username":"admin","full_name":"Admin","email":"admin@example.com"})
    return fixtures.fake_request(method,url,**kwargs)


@patch('portal.api_client.requests.request',side_effect=remote)
class DirectGradePortalTests(fixtures.LoggedInTestCase):
    def role(self,role,user_id=1):
        session=self.client.session
        session['user']={**session['user'],'role':role,'id':user_id}
        session.save()
        self.client.cookies['sessionid']=session.session_key

    def test_admin_sees_simple_grade_management(self,mock):
        response=self.client.get('/cham-diem/')
        self.assertContains(response,'Quản lý điểm đề tài')
        self.assertContains(response,'8.50')
        for text in ('Đợt chấm','Tạo hồ sơ','Phân công','Công bố'):
            self.assertNotContains(response,text)

    def test_lecturer_sees_edit_link_and_prepopulated_score(self,mock):
        self.role('LECTURER',2)
        self.assertContains(self.client.get('/cham-diem/'),'/cham-diem/1/')
        self.assertContains(self.client.get('/cham-diem/1/'),'value="8.50"')

    def test_direct_score_post_sends_only_registration_score_comment(self,mock):
        self.role('LECTURER',2)
        with patch('portal.api_client.grades.create',return_value=GRADE) as save:
            response=self.client.post('/cham-diem/1/',{'score':'9.25','comment':'Tốt'})
        self.assertRedirects(response,'/cham-diem/',fetch_redirect_response=False)
        save.assert_called_once_with({'registration':1,'score':'9.25','comment':'Tốt'})

    def test_invalid_score_preserves_form_and_never_calls_save(self,mock):
        self.role('LECTURER',2)
        for score in ('11','-1','NaN','1.001',''):
            with patch('portal.api_client.grades.create') as save:
                response=self.client.post('/cham-diem/1/',{'score':score})
            self.assertEqual(response.status_code,200)
            self.assertTrue(response.context['form'].errors)
            save.assert_not_called()

    def test_student_can_read_grade_but_cannot_open_score_form(self,mock):
        self.role('STUDENT',4)
        self.assertContains(self.client.get('/cham-diem/'),'8.50')
        self.assertRedirects(self.client.get('/cham-diem/1/'),'/',fetch_redirect_response=False)
        with patch('portal.api_client.grades.create') as save:
            self.client.post('/cham-diem/1/',{'score':'10'})
        save.assert_not_called()

    def test_comments_are_escaped(self,mock):
        response=self.client.get('/cham-diem/')
        self.assertContains(response,'&lt;script&gt;alert(1)&lt;/script&gt;')
        self.assertNotContains(response,'<script>alert(1)</script>')

    def test_ungraded_registration_has_direct_score_link(self,mock):
        self.role('LECTURER',2)
        with patch('portal.api_client.grades.list',return_value=[]):
            response=self.client.get('/cham-diem/')
        self.assertContains(response,'Chưa chấm')
        self.assertContains(response,'/cham-diem/1/')

    def test_pending_registration_cannot_open_form(self,mock):
        self.role('LECTURER',2)
        with patch('portal.api_client.registrations.get',return_value={**REGISTRATION,'status':'PENDING'}), patch('portal.api_client.grades.create') as save:
            response=self.client.post('/cham-diem/1/',{'score':'10'})
        self.assertRedirects(response,'/cham-diem/',fetch_redirect_response=False)
        save.assert_not_called()

    def test_csrf_required(self,mock):
        self.role('LECTURER',2)
        client=Client(enforce_csrf_checks=True)
        client.cookies=self.client.cookies
        self.assertEqual(client.post('/cham-diem/1/',{'score':'8'}).status_code,403)

    def test_profile_and_account_edit_still_work(self,mock):
        self.assertEqual(self.client.get('/ho-so/').status_code,200)
        with patch('portal.api_client.users.update',return_value={}) as update:
            response=self.client.post('/tai-khoan/2/sua/',{'username':'gv','email':'gv@test.local','full_name':'Tên mới','role':'LECTURER','student_id':'','password':''})
        self.assertEqual(response.status_code,302)
        self.assertNotIn('password',update.call_args.args[1])

    def test_obsolete_workflow_urls_are_removed(self,mock):
        for path in ('/dot-cham-diem/','/dot-cham-diem/them/','/cham-diem/them/'):
            self.assertEqual(self.client.get(path).status_code,404)

    def test_admin_sees_detail_edit_delete_buttons(self,mock):
        response=self.client.get('/cham-diem/')
        for path in ('/cham-diem/1/chi-tiet/','/cham-diem/1/','/cham-diem/1/xoa/'):
            self.assertContains(response,path)
        detail=self.client.get('/cham-diem/1/chi-tiet/')
        self.assertContains(detail,'Chi tiết điểm đề tài')
        self.assertContains(detail,'8.50')
        self.assertNotContains(detail,'<script>alert(1)</script>')

    def test_admin_can_edit(self,mock):
        with patch('portal.api_client.grades.create',return_value=GRADE) as save:
            response=self.client.post('/cham-diem/1/',{'score':'8','comment':'Admin sửa'})
        self.assertEqual(response.status_code,302)
        save.assert_called_once()

    def test_delete_requires_post_and_csrf_and_get_only_confirms(self,mock):
        with patch('portal.api_client.grades.delete') as delete:
            confirmation=self.client.get('/cham-diem/1/xoa/')
            self.assertContains(confirmation,'Xác nhận xóa điểm')
            delete.assert_not_called()
            client=Client(enforce_csrf_checks=True)
            client.cookies=self.client.cookies
            self.assertEqual(client.post('/cham-diem/1/xoa/').status_code,403)
            delete.assert_not_called()
            response=self.client.post('/cham-diem/1/xoa/')
            self.assertRedirects(response,'/cham-diem/',fetch_redirect_response=False)
            delete.assert_called_once_with(1)

    def test_student_has_detail_only_and_cannot_delete(self,mock):
        self.role('STUDENT',4)
        response=self.client.get('/cham-diem/')
        self.assertContains(response,'/cham-diem/1/chi-tiet/')
        self.assertNotContains(response,'/cham-diem/1/xoa/')
        self.assertEqual(self.client.get('/cham-diem/1/chi-tiet/').status_code,200)
        with patch('portal.api_client.grades.delete') as delete:
            self.assertEqual(self.client.post('/cham-diem/1/xoa/').status_code,302)
            delete.assert_not_called()

    def test_ungraded_row_has_no_delete_button(self,mock):
        with patch('portal.api_client.grades.list',return_value=[]):
            response=self.client.get('/cham-diem/')
            self.assertNotContains(response,'/cham-diem/1/xoa/')
            self.assertContains(response,'Chấm điểm')
            with patch('portal.api_client.grades.delete') as delete:
                self.assertEqual(self.client.post('/cham-diem/1/xoa/').status_code,302)
                delete.assert_not_called()
