from rest_framework import filters, generics

from .models import Student
from .serializers import StudentSerializer


class StudentListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/students/            -> danh sách sinh viên
    GET  /api/students/?search=... -> tìm kiếm (mã SV, họ tên, email, lớp, ngành)
    POST /api/students/            -> tạo sinh viên
    """

    queryset = Student.objects.all()
    serializer_class = StudentSerializer
    filter_backends = [filters.SearchFilter]
    # "__unaccent": tìm "Nguyen" vẫn ra "Nguyễn" (hàm unaccent của PostgreSQL)
    search_fields = [
        "student_code",
        "full_name",
        "full_name__unaccent",
        "email",
        "class_name",
        "major",
        "major__unaccent",
    ]


class StudentDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET    /api/students/{id}/ -> chi tiết (Registration Service gọi API này)
    PUT    /api/students/{id}/ -> cập nhật toàn bộ
    PATCH  /api/students/{id}/ -> cập nhật một phần
    DELETE /api/students/{id}/ -> xóa
    """

    queryset = Student.objects.all()
    serializer_class = StudentSerializer
