from unittest.mock import patch
from . import tests as fixtures


def responses(method,url,timeout=None,**kwargs):
    if method=="GET" and url.endswith("/api/theses/1/"):
        return fixtures.make_response(200,fixtures.THESES_ROLE[0])
    if method in ("POST","PATCH") and ("/api/students/" in url or "/api/theses/" in url):
        key="student_code" if "/api/students/" in url else "thesis_code"
        return fixtures.make_response(201 if method=="POST" else 200,{"id":1,key:"SV005" if key=="student_code" else "DT005",**kwargs['json']})
    return fixtures.role_fake(method,url,timeout=timeout,**kwargs)


@patch("portal.api_client.requests.request",side_effect=responses)
class AutomaticCodePortalTests(fixtures.RoleTestCase):
    def test_create_pages_show_auto_message_without_code_inputs(self,remote):
        for path,key in (("/sinh-vien/them/","student_code"),("/de-tai/them/","thesis_code")):
            response=self.client.get(path)
            self.assertEqual(response.status_code,200)
            self.assertNotContains(response,'name="'+key+'"')
            self.assertContains(response,"được tạo tự động sau khi lưu")

    def test_student_create_does_not_send_a_manual_code(self,remote):
        response=self.client.post('/sinh-vien/them/',{'full_name':'Tự động','email':'auto@test.local','student_code':'FORGED'})
        self.assertEqual(response.status_code,302)
        post=[c for c in remote.call_args_list if c.args[0]=='POST'][-1]
        self.assertNotIn('student_code',post.kwargs['json'])

    def test_thesis_create_does_not_send_a_manual_code(self,remote):
        response=self.client.post('/de-tai/them/',{'title':'Đề tài tự động','max_students':1,'status':'OPEN','supervisor_id':'','thesis_code':'FORGED'})
        self.assertEqual(response.status_code,302)
        post=[c for c in remote.call_args_list if c.args[0]=='POST'][-1]
        self.assertNotIn('thesis_code',post.kwargs['json'])

    def test_edit_pages_show_current_code_without_an_input(self,remote):
        for path,code,key in (('/sinh-vien/1/sua/','SV001','student_code'),('/de-tai/1/sua/','DT001','thesis_code')):
            response=self.client.get(path)
            self.assertEqual(response.status_code,200)
            self.assertContains(response,code)
            self.assertNotContains(response,'name="'+key+'"')
