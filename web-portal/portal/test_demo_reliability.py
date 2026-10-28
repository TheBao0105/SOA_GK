from unittest.mock import MagicMock,patch
import requests
from django.test import SimpleTestCase
from . import api_client as api


class DemoReliabilityTests(SimpleTestCase):
    def test_api_status_requires_200_and_rejects_redirects(self):
        for code in (200,204,301,302,401,404,500,503):
            with self.subTest(code=code),patch("portal.api_client.requests.get",return_value=MagicMock(status_code=code)) as get:
                self.assertEqual(api.is_online("http://localhost:8001"),code==200)
                self.assertFalse(get.call_args.kwargs["allow_redirects"])
                self.assertEqual(get.call_args.kwargs["timeout"],2)

    def test_timeout_is_not_online(self):
        with patch("portal.api_client.requests.get",side_effect=requests.Timeout):
            self.assertFalse(api.is_online("http://localhost:8001"))

    def test_success_with_invalid_json_is_controlled_service_error(self):
        for payload in (None,"text",3,True):
            response=MagicMock(status_code=200,content=b"x")
            response.json.return_value=payload
            with self.subTest(payload=payload),patch("portal.api_client.requests.request",return_value=response):
                with self.assertRaises(api.ServiceUnavailable):
                    api.call("Test","GET","http://localhost/",auth=False)

    def test_resource_list_and_detail_validate_identity(self):
        for payload in ({},[None],[{"id":False}]):
            with patch.object(api.students,"_request",return_value=payload):
                with self.assertRaises(api.ServiceUnavailable):
                    api.students.list()
        with patch.object(api.students,"_request",return_value={"id":99}):
            with self.assertRaises(api.ServiceUnavailable):
                api.students.get(1)

    def test_bad_refresh_response_does_not_overwrite_session(self):
        session={api.SESSION_REFRESH:"old",api.SESSION_ACCESS:"existing"}
        response=MagicMock(status_code=200,content=b"x")
        response.json.return_value={"access":"new"}
        with patch("portal.api_client.requests.post",return_value=response):
            with self.assertRaises(api.ServiceUnavailable):
                api._refresh_tokens(session)
        self.assertEqual(session[api.SESSION_ACCESS],"existing")


    def test_login_payload_requires_token_pair_and_valid_user(self):
        for payload in ([],{}, {"access":"a","refresh":"r"}, {"access":"a","refresh":"r","user":{"id":True,"username":"x","role":"ADMIN"}}):
            with self.subTest(payload=payload),patch("portal.api_client.call",return_value=payload):
                with self.assertRaises(api.ServiceUnavailable):
                    api.login("admin","not-logged")

    def test_bad_error_payload_still_becomes_service_unavailable(self):
        response=MagicMock(status_code=503,content=b"x")
        response.json.return_value=["unexpected"]
        with patch("portal.api_client.requests.request",return_value=response):
            with self.assertRaises(api.ServiceUnavailable):
                api.call("Test","GET","http://localhost/",auth=False)
