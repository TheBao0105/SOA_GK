from unittest.mock import patch
from django.db import OperationalError, ProgrammingError
from django.test import SimpleTestCase
from . import tests as fixtures
from .models import Registration
from .services import external_api

REMOTE="registrations.services.external_api.requests.get"


class ApiContractTests(fixtures.RegistrationTestCase):
    def register(self):
        return self.client.post("/api/registrations/",{"student_id":1,"thesis_id":1},format="json")

    def test_bad_student_payload_returns_503_without_writes(self):
        for payload in ([],{},None,{"id":True},{"id":"1"},{"id":2}):
            with self.subTest(payload=payload),patch(REMOTE,return_value=fixtures.make_response(200,payload)):
                self.assertEqual(self.register().status_code,503)
                self.assertFalse(Registration.objects.exists())

    def test_bad_thesis_payload_returns_503_without_writes(self):
        bad=[[],{}, {"id":2,"status":"OPEN","max_students":1},
             {"id":1,"status":"UNKNOWN","max_students":1}, {"id":1,"status":"OPEN"},
             {"id":1,"status":"OPEN","max_students":"2"}, {"id":1,"status":"OPEN","max_students":True},
             {"id":1,"status":"OPEN","max_students":0}]
        for payload in bad:
            with self.subTest(payload=payload),patch(REMOTE,side_effect=[fixtures.make_response(200,{"id":1}),fixtures.make_response(200,payload)]):
                self.assertEqual(self.register().status_code,503)
                self.assertFalse(Registration.objects.exists())

    def test_nonretryable_database_error_is_not_reported_as_busy(self):
        for exc in (ProgrammingError("Invalid object name 'dangky'"),OperationalError("08001","Cannot connect")):
            with self.subTest(error=type(exc).__name__),patch(REMOTE,side_effect=fixtures.fake_get),patch("registrations.views.RegistrationLock.acquire",side_effect=exc) as lock,patch("registrations.views.time.sleep") as sleep, self.assertLogs("registrations.views",level="ERROR"):
                response=self.register()
                self.assertEqual(response.status_code,500)
                self.assertIn("check migrations",str(response.data))
                self.assertEqual(lock.call_count,1)
                sleep.assert_not_called()
                self.assertFalse(Registration.objects.exists())


class ListContractTests(SimpleTestCase):
    def test_bad_list_shapes_and_missing_fields_raise_contract_error(self):
        functions=[lambda:external_api.list_supervised_thesis_ids(2),lambda:external_api.find_student_by_code("SV001"),lambda:external_api.find_thesis_by_code("DT001")]
        for fn in functions:
            for payload in (None,{}, {"results":[]},[None],[{"id":False}]):
                with self.subTest(payload=payload),patch(REMOTE,return_value=fixtures.make_response(200,payload)):
                    with self.assertRaises(external_api.ServiceContractError):
                        fn()
        for fn in functions[1:]:
            with patch(REMOTE,return_value=fixtures.make_response(200,[{"id":1}])):
                with self.assertRaises(external_api.ServiceContractError):
                    fn()

    def test_empty_lists_are_valid(self):
        with patch(REMOTE,return_value=fixtures.make_response(200,[])):
            self.assertEqual(external_api.list_supervised_thesis_ids(2),[])
            self.assertIsNone(external_api.find_student_by_code("SV001"))

    def test_error_classifier_understands_only_transient_lock_errors(self):
        from .views import is_retryable_lock_error
        for exc in (OperationalError("40001","transaction aborted"),OperationalError("HYT00","Lock timeout (1222)"),OperationalError("deadlock (1205)")):
            self.assertTrue(is_retryable_lock_error(exc))
        for exc in (ProgrammingError("42000","Invalid object"),OperationalError("08001","Cannot connect"),OperationalError("HY000","Syntax error")):
            self.assertFalse(is_retryable_lock_error(exc))
