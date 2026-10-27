from unittest.mock import MagicMock, patch
import requests
from django.test import override_settings
from config.testing import AuthenticatedAPITestCase


@override_settings(JWT_CHECK_ACCOUNT_STATE=True)
class AccountStateTests(AuthenticatedAPITestCase):
    url = '/api/registrations/'

    @patch("config.jwt_auth.requests.get")
    def test_current_account_accepted(self, remote):
        remote.return_value=MagicMock(status_code=200)
        remote.return_value.json.return_value={"id":1,"role":"ADMIN","student_id":None,"is_active":True}
        self.assertEqual(self.client.get(self.url).status_code,200)
        self.assertIn("Bearer ",remote.call_args.kwargs["headers"]["Authorization"])
        self.assertGreater(remote.call_args.kwargs["timeout"],0)

    @patch("config.jwt_auth.requests.get")
    def test_revoked_token_or_changed_role_rejected(self, remote):
        remote.return_value=MagicMock(status_code=401)
        self.assertEqual(self.client.get(self.url).status_code,401)
        remote.return_value=MagicMock(status_code=200)
        remote.return_value.json.return_value={"id":1,"role":"STUDENT","student_id":1,"is_active":True}
        self.assertEqual(self.client.get(self.url).status_code,401)

    @patch("config.jwt_auth.requests.get",side_effect=requests.Timeout)
    def test_identity_timeout_fails_closed(self, remote):
        self.assertEqual(self.client.get(self.url).status_code,503)

    @patch("config.jwt_auth.requests.get")
    def test_malformed_identity_response_fails_closed(self, remote):
        remote.return_value=MagicMock(status_code=200)
        remote.return_value.json.side_effect=ValueError
        self.assertEqual(self.client.get(self.url).status_code,503)
