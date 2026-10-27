from unittest.mock import patch
from django.conf import settings
from django.test import Client, SimpleTestCase
from django.urls import reverse
from portal import tests as fixtures
from .roles import QUAN_TRI, GIANG_VIEN, SINH_VIEN


class LegacyAccountUrlTests(SimpleTestCase):
    def test_login_url_renders_without_redirect_loop(self):
        response=self.client.get(reverse('accounts:login'))
        self.assertEqual(response.status_code,200)
        self.assertTemplateUsed(response,'portal/login.html')

    @patch('portal.api_client.requests.request',side_effect=fixtures.fake_request)
    def test_legacy_login_gets_identity_tokens(self,remote):
        response=self.client.post('/accounts/login/',{'username':'admin','password':'test'})
        self.assertEqual(response.status_code,302)
        self.assertEqual(self.client.session['user']['role'],'ADMIN')
        self.assertEqual(self.client.session['access_token'],'access-1')
        self.assertIn('/api/auth/login/',remote.call_args.args[1])

    @patch('portal.api_client.requests.request',side_effect=fixtures.fake_request)
    def test_legacy_logout_revokes_identity_tokens(self,remote):
        self.client.post('/accounts/login/',{'username':'admin','password':'test'})
        self.assertEqual(self.client.post('/accounts/logout/').status_code,302)
        self.assertIsNone(self.client.session.get('access_token'))
        self.assertIn('/api/auth/logout/',remote.call_args.args[1])

    @patch('portal.api_client.requests.request',side_effect=fixtures.fake_request)
    def test_legacy_logout_still_requires_post_and_csrf(self,remote):
        self.client.post('/accounts/login/',{'username':'admin','password':'test'})
        self.assertEqual(self.client.get('/accounts/logout/').status_code,405)
        protected=Client(enforce_csrf_checks=True)
        protected.cookies=self.client.cookies
        self.assertEqual(protected.post('/accounts/logout/').status_code,403)

    def test_vietnamese_aliases_match_identity_roles(self):
        self.assertEqual((QUAN_TRI,GIANG_VIEN,SINH_VIEN),('ADMIN','LECTURER','STUDENT'))
        self.assertEqual(settings.MIDDLEWARE.count('django.contrib.sessions.middleware.SessionMiddleware'),1)
        self.assertNotIn('django.contrib.auth.middleware.AuthenticationMiddleware',settings.MIDDLEWARE)
