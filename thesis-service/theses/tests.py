from rest_framework import status
from rest_framework.test import APITestCase

from .models import Thesis


class ThesisAPITests(APITestCase):
    def setUp(self):
        self.thesis = Thesis.objects.create(
            thesis_code="DT001",
            title="Hệ thống quản lý thư viện",
            description="Ứng dụng web quản lý sách",
            supervisor="TS. Phạm Minh Tuấn",
            max_students=2,
        )
        self.list_url = "/api/theses/"
        self.detail_url = f"/api/theses/{self.thesis.id}/"

    def test_create_thesis(self):
        data = {
            "thesis_code": "DT002",
            "title": "Hệ thống đặt sân thể thao",
            "supervisor": "ThS. Hoàng Thu Hà",
            "max_students": 1,
        }
        response = self.client.post(self.list_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], "OPEN")  # mặc định OPEN
        self.assertEqual(Thesis.objects.count(), 2)

    def test_list_theses(self):
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_search_theses(self):
        # Tim theo tu khoa co trong description
        response = self.client.get(self.list_url, {"search": "web"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

        # Tim theo ma de tai
        response = self.client.get(self.list_url, {"search": "DT001"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

        # Tu khoa khong ton tai
        response = self.client.get(self.list_url, {"search": "blockchain"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 0)

    def test_thesis_detail(self):
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["thesis_code"], "DT001")

    def test_thesis_detail_not_found(self):
        response = self.client.get("/api/theses/9999/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_update_thesis_put(self):
        data = {
            "thesis_code": "DT001",
            "title": "Hệ thống quản lý thư viện số",
            "description": "",
            "supervisor": "TS. Phạm Minh Tuấn",
            "max_students": 3,
            "status": "OPEN",
        }
        response = self.client.put(self.detail_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.thesis.refresh_from_db()
        self.assertEqual(self.thesis.max_students, 3)

    def test_update_thesis_patch_close(self):
        response = self.client.patch(
            self.detail_url, {"status": "CLOSED"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.thesis.refresh_from_db()
        self.assertEqual(self.thesis.status, "CLOSED")

    def test_delete_thesis(self):
        response = self.client.delete(self.detail_url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Thesis.objects.exists())

    def test_thesis_code_unique(self):
        data = {"thesis_code": "DT001", "title": "Trùng mã", "max_students": 1}
        response = self.client.post(self.list_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("thesis_code", response.data)

    def test_title_required(self):
        data = {"thesis_code": "DT009", "max_students": 1}
        response = self.client.post(self.list_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("title", response.data)

    def test_max_students_must_be_positive(self):
        data = {"thesis_code": "DT009", "title": "Đề tài X", "max_students": 0}
        response = self.client.post(self.list_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("max_students", response.data)
