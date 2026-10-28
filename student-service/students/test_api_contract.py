from unittest.mock import MagicMock,patch
from config.testing import AuthenticatedAPITestCase
from .models import Student


class RegistrationContractTests(AuthenticatedAPITestCase):
    def setUp(self):
        super().setUp()
        self.obj=Student.objects.create(student_code="CONTRACT",full_name="Test",email="contract@test.local")
        self.url="/api/students/"+str(self.obj.pk)+"/"

    def test_invalid_registration_response_cannot_authorize_delete(self):
        for payload in ({},None,"",[None],[{}],[{"id":True}],[{"id":1,"status":"CANCELLED"}]):
            response=MagicMock(status_code=200)
            response.json.return_value=payload
            with self.subTest(payload=payload),patch("config.registration_api.requests.get",return_value=response):
                self.assertEqual(self.client.delete(self.url).status_code,503)
                self.assertTrue(type(self.obj).objects.filter(pk=self.obj.pk).exists())
