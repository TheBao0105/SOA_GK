from rest_framework import filters, generics

from .models import Student
from .serializers import StudentSerializer


class StudentListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/students/            -> danh sách sinh viên
    GET  /api/students/?search=... -> tìm kiếm sinh viên
    POST /api/students/            -> tạo sinh viên
    """

    queryset = Student.objects.all()
    serializer_class = StudentSerializer
    filter_backends = [filters.SearchFilter]

    search_fields = [
        "student_code",
        "full_name",
        "email",
        "class_name",
        "major",
    ]


class StudentDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET    /api/students/{id}/ -> chi tiết sinh viên
    PUT    /api/students/{id}/ -> cập nhật toàn bộ
    PATCH  /api/students/{id}/ -> cập nhật một phần
    DELETE /api/students/{id}/ -> xóa sinh viên
    """

    queryset = Student.objects.all()
    serializer_class = StudentSerializer
