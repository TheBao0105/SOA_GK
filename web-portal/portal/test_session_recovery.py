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

    def test_backend_forbidden_on_dashboard_is_terminal_not_redirect_to_itself(self):
        with patch('portal.api_client.requests.request',side_effect=fixtures.fake_request):
            self.client.post('/dang-nhap/',{'username':'admin','password':'x'})
        with patch('portal.api_client.requests.request',return_value=fixtures.make_response(403,{'detail':'Denied'})):
            response=self.client.get('/',follow=True)
        self.assertEqual(response.status_code,403)
        self.assertEqual(response.redirect_chain,[])
