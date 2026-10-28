from unittest.mock import patch
from django.conf import settings
from django.test import SimpleTestCase
from . import tests as fixtures


class SessionRecoveryTests(SimpleTestCase):
    def set_session(self,**data):
        session=self.client.session
        session.update(data)
        session.save()
        self.client.cookies[settings.SESSION_COOKIE_NAME]=session.session_key

    def test_legacy_role_cookie_returns_to_login_without_a_loop(self):
        self.set_session(access_token='old-access',refresh_token='old-refresh',user={'id':1,'username':'admin','role':'QUAN_TRI'})
        with patch('portal.api_client.requests.request') as remote:
            response=self.client.get('/',follow=True)
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.request['PATH_INFO'],'/dang-nhap/')
        self.assertIsNone(self.client.session.get('access_token'))
        remote.assert_not_called()

    def test_partial_or_malformed_session_is_cleared_on_both_login_urls(self):
        for path in ('/dang-nhap/','/accounts/login/'):
            for user in (None,{},'legacy-user',{'id':1,'username':'admin','role':'UNKNOWN'}):
                with self.subTest(path=path,user=user):
                    self.client.cookies.clear()
                    self.set_session(access_token='old-access',user=user)
                    response=self.client.get(path,follow=True)
                    self.assertEqual(response.status_code,200)
                    self.assertTemplateUsed(response,'portal/login.html')
                    self.assertIsNone(self.client.session.get('access_token'))

    def test_bad_session_shapes_do_not_reach_backend(self):
        for token,user in ((True,{'id':1,'username':'a','role':'ADMIN'}),('x',{'id':True,'username':'a','role':'ADMIN'}),('x',{'id':1,'role':'ADMIN'})):
            self.client.cookies.clear()
            self.set_session(access_token=token,user=user)
            with patch('portal.api_client.requests.request') as remote:
                response=self.client.get('/',follow=True)
            self.assertEqual(response.status_code,200)
            remote.assert_not_called()

    def test_valid_session_still_opens_dashboard(self):
        with patch('portal.api_client.requests.request',side_effect=fixtures.fake_request):
            self.client.post('/dang-nhap/',{'username':'admin','password':'x'})
            self.assertEqual(self.client.get('/').status_code,200)
            self.assertEqual(self.client.session['user']['role'],'ADMIN')

    def test_backend_forbidden_keeps_session_and_dashboard_available(self):
        with patch('portal.api_client.requests.request',side_effect=fixtures.fake_request):
            self.client.post('/dang-nhap/',{'username':'admin','password':'x'})
        with patch('portal.api_client.requests.request',return_value=fixtures.make_response(403,{'detail':'Denied'})), self.assertLogs('portal.views',level='WARNING') as logs:
            for _ in range(2):
                response=self.client.get('/',follow=True)
                self.assertEqual(response.status_code,200)
                self.assertTemplateUsed(response,'portal/dashboard.html')
                self.assertEqual(response.redirect_chain,[])
                self.assertIsNotNone(self.client.session.get('access_token'))
                self.assertIsNone(response.context['total_students'])
                self.assertIsNone(response.context['total_theses'])
                self.assertIsNone(response.context['total_registrations'])
                self.assertContains(response,'Student Service')
                self.assertNotContains(response,'Phiên đăng nhập không được chấp nhận')
        self.assertTrue(any('Student Service' in line for line in logs.output))

    def test_individual_dashboard_denials_do_not_hide_other_sections(self):
        for service, counter in (('8001','total_students'),('8002','total_theses'),('8003','total_registrations')):
            with self.subTest(service=service):
                with patch('portal.api_client.requests.request',side_effect=fixtures.fake_request):
                    self.client.post('/dang-nhap/',{'username':'admin','password':'x'})
                def remote(method,url,**kwargs):
                    if ':'+service in url:
                        return fixtures.make_response(403,{'detail':'Denied'})
                    return fixtures.fake_request(method,url,**kwargs)
                with patch('portal.api_client.requests.request',side_effect=remote):
                    response=self.client.get('/')
                self.assertEqual(response.status_code,200)
                self.assertIsNone(response.context[counter])
                self.assertIsNotNone(self.client.session.get('access_token'))
                other='total_theses' if service=='8001' else 'total_students'
                self.assertIsNotNone(response.context[other])


    def test_first_visit_always_shows_login_without_backend_calls(self):
        self.client.cookies.clear()
        with patch('portal.api_client.requests.request') as remote:
            response=self.client.get('/',follow=True)
        self.assertEqual(response.status_code,200)
        self.assertTemplateUsed(response,'portal/login.html')
        remote.assert_not_called()

    def test_reopening_after_session_recovery_stays_on_login(self):
        self.set_session(access_token='old',user={'id':1,'username':'admin','role':'QUAN_TRI'})
        with patch('portal.api_client.requests.request') as remote:
            first=self.client.get('/',follow=True)
            second=self.client.get('/',follow=True)
        self.assertEqual(first.status_code,200)
        self.assertEqual(second.status_code,200)
        self.assertTemplateUsed(second,'portal/login.html')
        remote.assert_not_called()
