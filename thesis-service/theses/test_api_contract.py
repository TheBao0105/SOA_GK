from unittest.mock import MagicMock,patch
from config.testing import AuthenticatedAPITestCase
from .models import Thesis


class RegistrationContractTests(AuthenticatedAPITestCase):
    def setUp(self):
        super().setUp()
        self.obj=Thesis.objects.create(thesis_code="CONTRACT",title="Test",max_students=3)
        self.url="/api/theses/"+str(self.obj.pk)+"/"

    def test_invalid_registration_response_cannot_authorize_delete(self):
        for payload in ({},None,"",[None],[{}],[{"id":True}],[{"id":1,"status":"CANCELLED"}]):
            response=MagicMock(status_code=200)
            response.json.return_value=payload
            with self.subTest(payload=payload),patch("config.registration_api.requests.get",return_value=response):
                self.assertEqual(self.client.delete(self.url).status_code,503)
                self.assertTrue(type(self.obj).objects.filter(pk=self.obj.pk).exists())

    def test_invalid_registration_response_cannot_authorize_lower_capacity(self):
        response=MagicMock(status_code=200)
        response.json.return_value={}
        with patch("config.registration_api.requests.get",return_value=response):
            self.assertEqual(self.client.patch(self.url,{"max_students":1}).status_code,503)
        self.obj.refresh_from_db()
        self.assertEqual(self.obj.max_students,3)
