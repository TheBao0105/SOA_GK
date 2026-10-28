from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import filters, generics, serializers, status
from rest_framework.exceptions import APIException, PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from config.permissions import ADMIN, ALL_ROLES, LECTURER, RolePermission, is_lecturer, is_student

from config.registration_api import RegistrationServiceError, count_active_registrations

from .models import Thesis
from .serializers import ThesisSerializer

# Ma trận quyền của Thesis Service
#   ADMIN    : toàn quyền, được chọn giảng viên hướng dẫn (supervisor_id)
#   LECTURER : thêm đề tài (tự động là GVHD), chỉ sửa / xóa đề tài do mình hướng dẫn
#   STUDENT  : chỉ xem; danh sách chỉ hiện đề tài đang OPEN
#   SERVICE  : chỉ xem
WRITE_ROLES = {
    "POST": (ADMIN, LECTURER),
    "PUT": (ADMIN, LECTURER),
    "PATCH": (ADMIN, LECTURER),
    "DELETE": (ADMIN, LECTURER),
}


class ThesisAccessMixin:
    permission_classes = [IsAuthenticated, RolePermission]
    read_roles = ALL_ROLES
    write_roles = WRITE_ROLES
    serializer_class = ThesisSerializer
    queryset = Thesis.objects.all()


@extend_schema_view(
    get=extend_schema(
        parameters=[
            OpenApiParameter("supervisor_id", int, description="Lọc đề tài theo giảng viên hướng dẫn"),
            OpenApiParameter("status", str, enum=["OPEN", "CLOSED"], description="Lọc theo trạng thái"),
        ]
    )
)
class ThesisListCreateView(ThesisAccessMixin, generics.ListCreateAPIView):
    filter_backends = [filters.SearchFilter]
    search_fields = [
        "thesis_code",
        "title",
        "description",
        "supervisor",
    ]

    def get_queryset(self):
        queryset = super().get_queryset()
        params = self.request.query_params
        if params.get("supervisor_id", "").isdigit():
            queryset = queryset.filter(supervisor_id=params["supervisor_id"])
        if params.get("status"):
            queryset = queryset.filter(status=params["status"].upper())
        if is_student(self.request.user):
            queryset = queryset.filter(status=Thesis.Status.OPEN)
        return queryset

    def perform_create(self, serializer):
        user = self.request.user
        if is_lecturer(user):
            # Giảng viên tạo đề tài -> chính họ là GVHD (không tạo hộ người khác được)
            serializer.save(
                supervisor_id=user.id,
                supervisor=serializer.validated_data.get("supervisor") or user.full_name,
                created_by=user.id,
            )
        else:
            serializer.save(created_by=user.id)


class ThesisDetailView(ThesisAccessMixin, generics.RetrieveUpdateDestroyAPIView):
    """
    Xem chi tiết: mọi vai trò (kể cả đề tài CLOSED, vì Registration Service cần
    biết trạng thái để báo "Thesis is closed").
    Sửa / xóa: ADMIN, hoặc LECTURER là GVHD của đề tài.
    """

    def check_object_permissions(self, request, obj):
        super().check_object_permissions(request, obj)
        if request.method not in ("GET", "HEAD", "OPTIONS") and is_lecturer(request.user):
            if obj.supervisor_id != request.user.id:
                raise PermissionDenied("You can only modify theses you supervise.")

    def perform_update(self, serializer):
        thesis = serializer.instance
        new_max = serializer.validated_data.get("max_students")
        if new_max is not None and new_max < thesis.max_students:
            # Giảm chỉ tiêu: không được thấp hơn số đăng ký đang còn hiệu lực
            active = self.active_registrations(thesis)
            if new_max < active:
                raise serializers.ValidationError(
                    {"max_students": [f"Cannot be lower than the number of active registrations ({active})."]}
                )
        if is_lecturer(self.request.user):
            # Giảng viên không được chuyển đề tài sang giảng viên khác
            serializer.save(supervisor_id=self.request.user.id)
        else:
            serializer.save()

    def destroy(self, request, *args, **kwargs):
        thesis = self.get_object()
        if self.active_registrations(thesis):
            return Response({"error": "Thesis has active registrations"}, status=status.HTTP_409_CONFLICT)
        thesis.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    def active_registrations(self, thesis):
        """Hỏi Registration Service qua REST (kèm token của người đang thao tác)."""
        try:
            return count_active_registrations(self.request.auth, thesis_id=thesis.id)
        except RegistrationServiceError as exc:
            raise RegistrationUnavailable({"error": str(exc)})


class RegistrationUnavailable(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
