from django.db import IntegrityError
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import generics, status
from rest_framework.response import Response

from .models import Registration
from .serializers import ErrorSerializer, RegistrationSerializer, RegistrationUpdateSerializer
from .services import external_api
from .services.external_api import ServiceUnavailableError


def error_response(message, http_status=status.HTTP_400_BAD_REQUEST):
    return Response({"error": message}, status=http_status)


def check_registration_rules(student_id, thesis_id, exclude_registration_id=None):
    """
    Luồng SOA kiểm tra một đăng ký. Trả về thông báo lỗi, hoặc None nếu hợp lệ.
    Có thể ném ServiceUnavailableError nếu service khác không hoạt động.
    """
    # Bước 1: gọi Student Service -> GET /api/students/{id}/
    student = external_api.get_student(student_id)
    if student is None:
        return "Student does not exist"

    # Bước 2: gọi Thesis Service -> GET /api/theses/{id}/
    thesis = external_api.get_thesis(thesis_id)
    if thesis is None:
        return "Thesis does not exist"

    # Bước 3: đề tài phải đang mở
    if thesis["status"] != "OPEN":
        return "Thesis is closed"

    # Bước 4: đếm số đăng ký hiện tại của đề tài (trong registration_db),
    # không tính các đăng ký đã bị từ chối
    current = Registration.objects.filter(thesis_id=thesis_id).exclude(
        status=Registration.Status.REJECTED
    )
    if exclude_registration_id is not None:
        current = current.exclude(id=exclude_registration_id)
    if current.count() >= thesis["max_students"]:
        return "Thesis has reached maximum students"

    return None


ERROR_RESPONSES = {400: ErrorSerializer, 503: ErrorSerializer}


@extend_schema_view(
    get=extend_schema(
        summary="Danh sách đăng ký (có filter)",
        parameters=[
            OpenApiParameter("student_id", int, description="Lọc theo sinh viên"),
            OpenApiParameter("thesis_id", int, description="Lọc theo đề tài"),
            OpenApiParameter(
                "status", str, enum=["PENDING", "APPROVED", "REJECTED"],
                description="Lọc theo trạng thái",
            ),
        ],
    ),
    post=extend_schema(
        summary="Đăng ký đề tài (gọi Student Service + Thesis Service)",
        responses={201: RegistrationSerializer, **ERROR_RESPONSES},
    ),
)
class RegistrationListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/registrations/?student_id=1&thesis_id=1&status=APPROVED
    POST /api/registrations/   body: {"student_id": 1, "thesis_id": 1}
    """

    serializer_class = RegistrationSerializer

    def get_queryset(self):
        queryset = Registration.objects.all()
        params = self.request.query_params
        if params.get("student_id", "").isdigit():
            queryset = queryset.filter(student_id=params["student_id"])
        if params.get("thesis_id", "").isdigit():
            queryset = queryset.filter(thesis_id=params["thesis_id"])
        if params.get("status"):
            queryset = queryset.filter(status=params["status"].upper())
        return queryset

    def create(self, request, *args, **kwargs):
        # Kiểm tra dữ liệu đầu vào (student_id, thesis_id là số nguyên dương)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        student_id = serializer.validated_data["student_id"]
        thesis_id = serializer.validated_data["thesis_id"]

        # Kiểm tra trùng trong DB của chính service này (không cần gọi HTTP)
        if Registration.objects.filter(student_id=student_id, thesis_id=thesis_id).exists():
            return error_response("Student has already registered for this thesis")

        # Bước 1 -> 4: gọi các service khác qua HTTP/REST
        try:
            error = check_registration_rules(student_id, thesis_id)
        except ServiceUnavailableError as exc:
            return error_response(str(exc), status.HTTP_503_SERVICE_UNAVAILABLE)
        if error:
            return error_response(error)

        # Bước 5: hợp lệ -> lưu đăng ký
        try:
            serializer.save()
        except IntegrityError:  # 2 request trùng gửi cùng lúc
            return error_response("Student has already registered for this thesis")
        return Response(serializer.data, status=status.HTTP_201_CREATED)


@extend_schema_view(
    put=extend_schema(summary="Cập nhật trạng thái đăng ký", responses={200: RegistrationUpdateSerializer, **ERROR_RESPONSES}),
    patch=extend_schema(summary="Cập nhật trạng thái đăng ký", responses={200: RegistrationUpdateSerializer, **ERROR_RESPONSES}),
)
class RegistrationDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET    /api/registrations/{id}/
    PUT    /api/registrations/{id}/  body: {"status": "APPROVED"}
    PATCH  /api/registrations/{id}/  body: {"status": "REJECTED"}
    DELETE /api/registrations/{id}/
    """

    queryset = Registration.objects.all()

    def get_serializer_class(self):
        if self.request.method in ("PUT", "PATCH"):
            return RegistrationUpdateSerializer
        return RegistrationSerializer

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)

        # Đăng ký đã bị REJECTED nay được mở lại -> phải kiểm tra lại các điều kiện
        new_status = serializer.validated_data.get("status", instance.status)
        if instance.status == Registration.Status.REJECTED and new_status != instance.status:
            try:
                error = check_registration_rules(
                    instance.student_id, instance.thesis_id, exclude_registration_id=instance.id
                )
            except ServiceUnavailableError as exc:
                return error_response(str(exc), status.HTTP_503_SERVICE_UNAVAILABLE)
            if error:
                return error_response(error)

        serializer.save()
        return Response(serializer.data)
