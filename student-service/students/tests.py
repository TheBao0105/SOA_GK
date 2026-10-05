from rest_framework import status
from rest_framework.test import APITestCase

from .models import Student


class StudentAPITests(APITestCase):
    def setUp(self):
        self.student = Student.objects.create(
            student_code="SV001",
            full_name="Nguyễn Văn An",
            email="an.nguyen@student.edu.vn",
            class_name="CNTT1",
            major="Công nghệ thông tin",
        )
        self.list_url = "/api/students/"
        self.detail_url = f"/api/students/{self.student.id}/"

    def test_create_student(self):
        data = {
            "student_code": "SV002",
            "full_name": "Trần Văn Bình",
            "email": "binh.tran@student.edu.vn",
            "class_name": "CNTT1",
            "major": "Công nghệ thông tin",
        }
        response = self.client.post(self.list_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Student.objects.count(), 2)
        self.assertEqual(response.data["student_code"], "SV002")

    def test_list_students(self):
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_search_students_without_accent(self):
        response = self.client.get(self.list_url, {"search": "Nguyen"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        response = self.client.get(self.list_url, {"search": "Tran"})
        self.assertEqual(len(response.data), 0)

    def test_student_detail(self):
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["full_name"], "Nguyễn Văn An")

    def test_student_detail_not_found(self):
        response = self.client.get("/api/students/9999/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_update_student_put(self):
        data = {
            "student_code": "SV001",
            "full_name": "Nguyễn Văn An (updated)",
            "email": "an.nguyen@student.edu.vn",
            "class_name": "CNTT2",
            "major": "Công nghệ thông tin",
        }
        response = self.client.put(self.detail_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.student.refresh_from_db()
        self.assertEqual(self.student.class_name, "CNTT2")

    def test_update_student_patch(self):
        response = self.client.patch(self.detail_url, {"major": "KTPM"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.student.refresh_from_db()
        self.assertEqual(self.student.major, "KTPM")

    def test_delete_student(self):
        response = self.client.delete(self.detail_url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Student.objects.exists())

    def test_student_code_required(self):
        data = {"full_name": "No Code", "email": "nocode@student.edu.vn"}
        response = self.client.post(self.list_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("student_code", response.data)

    def test_student_code_unique(self):
        data = {"student_code": "SV001", "full_name": "Dup", "email": "dup@student.edu.vn"}
        response = self.client.post(self.list_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("student_code", response.data)

    def test_full_name_required(self):
        data = {"student_code": "SV009", "email": "sv9@student.edu.vn"}
        response = self.client.post(self.list_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("full_name", response.data)

    def test_invalid_email(self):
        data = {"student_code": "SV009", "full_name": "Bad Email", "email": "not-an-email"}
        response = self.client.post(self.list_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.data)
