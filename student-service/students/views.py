from rest_framework import filters, generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from config.permissions import ADMIN, ALL_ROLES, RolePermission, is_student
from config.registration_api import RegistrationServiceError, count_active_registrations

from .models import Student
from .serializers import StudentSerializer

# Ma trận quyền của Student Service
#   ADMIN    : xem + thêm + sửa + xóa mọi sinh viên
#   LECTURER : chỉ xem (cần tên sinh viên khi duyệt đăng ký)
#   STUDENT  : chỉ xem hồ sơ của CHÍNH MÌNH (student_id trong token)
#   SERVICE  : chỉ xem (Registration Service gọi sang khi không có người dùng)
WRITE_ROLES = {"POST": (ADMIN,), "PUT": (ADMIN,), "PATCH": (ADMIN,), "DELETE": (ADMIN,)}


class StudentAccessMixin:
    permission_classes = [IsAuthenticated, RolePermission]
    read_roles = ALL_ROLES
    write_roles = WRITE_ROLES
    serializer_class = StudentSerializer

    def get_queryset(self):
        queryset = Student.objects.all()
        user = self.request.user
        if is_student(user):
            # Sinh viên chỉ thấy bản ghi của mình; bản ghi khác trả 404 (không lộ là có tồn tại)
            if user.student_id is None:
                return queryset.none()
            queryset = queryset.filter(id=user.student_id)
        return queryset


class StudentListCreateView(StudentAccessMixin, generics.ListCreateAPIView):
    """
    GET  /api/students/            -> danh sách sinh viên
    GET  /api/students/?search=... -> tìm kiếm sinh viên
    POST /api/students/            -> tạo sinh viên (ADMIN)
    """

    filter_backends = [filters.SearchFilter]

    search_fields = [
        "student_code",
        "full_name",
        "email",
        "class_name",
        "major",
    ]


class StudentDetailView(StudentAccessMixin, generics.RetrieveUpdateDestroyAPIView):
    """
    GET    /api/students/{id}/ -> chi tiết sinh viên
    PUT    /api/students/{id}/ -> cập nhật toàn bộ (ADMIN)
    PATCH  /api/students/{id}/ -> cập nhật một phần (ADMIN)
    DELETE /api/students/{id}/ -> xóa sinh viên (ADMIN)
                                  chỉ khi không còn đăng ký hiệu lực bên Registration Service
    """

    def destroy(self, request, *args, **kwargs):
        student = self.get_object()
        # Hỏi Registration Service qua REST: còn đăng ký PENDING / APPROVED thì không cho xóa
        try:
            active = count_active_registrations(request.auth, student_id=student.id)
        except RegistrationServiceError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        if active:
            return Response(
                {"error": "Student has active registrations"}, status=status.HTTP_409_CONFLICT
            )
        student.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
