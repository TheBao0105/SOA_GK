import random
import logging
import re
import time

from django.db import DatabaseError, IntegrityError, OperationalError, transaction
from django.db.models import ProtectedError
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import generics, status
from rest_framework.exceptions import APIException
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from config.permissions import (
    ADMIN, ALL_ROLES, LECTURER, STUDENT, RolePermission, is_lecturer, is_student,
)

from .models import ProgressNote, Registration, RegistrationLock
from .serializers import (
    ErrorSerializer,
    ProgressNoteSerializer,
    RegistrationSerializer,
    RegistrationUpdateSerializer,
)
from .services import external_api
from .services.external_api import ServiceAuthError, ServiceUnavailableError


def error_response(message, http_status=status.HTTP_400_BAD_REQUEST):
    return Response({"error": message}, status=http_status)


class UpstreamUnavailable(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE


class UpstreamRejected(APIException):
    status_code = status.HTTP_502_BAD_GATEWAY


class BusinessRuleError(Exception):
    """Vi phạm quy tắc nghiệp vụ -> 400 {"error": "..."}"""


class RegistrationBusy(APIException):
    """SQL Server vẫn báo xung đột khóa (deadlock) sau khi đã thử lại -> 503 thay vì 500."""

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = {"error": "Registration Service is busy, please try again"}


# ---------------------------------------------------------------- Phân quyền
# Ma trận quyền của Registration Service
#   ADMIN    : xem / tạo / duyệt / hủy / xóa mọi đăng ký
#   LECTURER : chỉ xem và duyệt / từ chối đăng ký thuộc đề tài mình hướng dẫn
#              (danh sách đề tài lấy từ Thesis Service theo supervisor_id),
#              ghi nhận xét / tiến độ cho đăng ký đã duyệt
#   STUDENT  : chỉ đăng ký cho CHÍNH MÌNH, chỉ xem đăng ký của mình,
#              chỉ hủy khi đăng ký còn PENDING
#   SERVICE  : chỉ xem
REGISTRATION_WRITE_ROLES = {
    "POST": (ADMIN, STUDENT),
    "PUT": (ADMIN, LECTURER),
    "PATCH": (ADMIN, LECTURER),
    "DELETE": (ADMIN,),
}


def scoped_registrations(request):
    """Các đăng ký mà người gọi được phép thấy (kiểm tra quyền trên từng đối tượng)."""
    queryset = Registration.objects.all()
    user = request.user
    if is_student(user):
        if user.student_id is None:
            return queryset.none()
        return queryset.filter(student_id=user.student_id)
    if is_lecturer(user):
        try:
            thesis_ids = external_api.list_supervised_thesis_ids(user.id, request.auth)
        except ServiceUnavailableError as exc:
            raise UpstreamUnavailable({"error": str(exc)})
        except ServiceAuthError as exc:
            raise UpstreamRejected({"error": str(exc)})
        return queryset.filter(thesis_id__in=thesis_ids)
    return queryset


# ---------------------------------------------------------------- Quy tắc nghiệp vụ
# Hàm kiểm tra các điều kiện cần gọi sang service khác (Bước 1 - 3)
#
# student_id: mã sinh viên cần đăng ký đề tài
# thesis_id: mã đề tài mà sinh viên muốn đăng ký
# token: access token của người dùng, được chuyển tiếp khi gọi service khác
#
# Hàm trả về (thông báo lỗi hoặc None, dữ liệu đề tài lấy từ Thesis Service)
#
# Các lời gọi HTTP được thực hiện TRƯỚC khi mở transaction / khóa dữ liệu,
# để không giữ khóa trong lúc chờ mạng.
#
# Hàm có thể phát sinh ServiceUnavailableError nếu service
# cần gọi không hoạt động, hoặc ServiceAuthError nếu service đó từ chối token
def check_remote_rules(student_id, thesis_id, token=None):

    # BƯỚC 1: Gọi Student Service để kiểm tra sinh viên
    # Gửi yêu cầu GET /api/students/{id}/ thông qua external_api
    # Ví dụ: student_id = 1 thì gọi API lấy sinh viên có ID 1
    student = external_api.get_student(student_id, token)

    # Nếu không tìm thấy sinh viên, trả về thông báo lỗi
    # Dừng kiểm tra và không tiếp tục các bước phía dưới
    if student is None:
        return "Student does not exist", None

    # BƯỚC 2: Gọi Thesis Service để kiểm tra đề tài
    # Gửi yêu cầu GET /api/theses/{id}/ thông qua external_api
    # Ví dụ: thesis_id = 1 thì gọi API lấy đề tài có ID 1
    thesis = external_api.get_thesis(thesis_id, token)

    # Nếu không tìm thấy đề tài, trả về thông báo lỗi
    if thesis is None:
        return "Thesis does not exist", None

    # BƯỚC 3: Kiểm tra trạng thái của đề tài
    # Chỉ cho phép đăng ký khi đề tài có trạng thái OPEN
    # thesis["status"] lấy giá trị trạng thái từ dữ liệu API trả về
    if thesis["status"] != "OPEN":
        return "Thesis is closed", thesis

    return None, thesis


# Hàm kiểm tra các điều kiện trên dữ liệu của chính Registration Service (Bước 4)
#
# BẮT BUỘC gọi bên trong transaction.atomic() SAU KHI đã khóa
# RegistrationLock của đề tài và sinh viên, để hai request đến cùng lúc
# không cùng "thấy còn chỗ" rồi cùng lưu (vượt chỉ tiêu).
def check_local_limits(student_id, thesis, exclude_registration_id=None):

    # Chỉ đếm các đăng ký còn hiệu lực (PENDING, APPROVED);
    # đăng ký bị từ chối hoặc đã hủy không chiếm chỗ
    active = Registration.objects.filter(status__in=Registration.ACTIVE_STATUSES)

    # Nếu đang cập nhật / đăng ký lại một dòng đã tồn tại,
    # loại trừ chính dòng đó khỏi kết quả đếm
    if exclude_registration_id is not None:
        active = active.exclude(id=exclude_registration_id)

    # BƯỚC 4a: Đề tài còn chỗ không?
    # So sánh số đăng ký hiện tại với số lượng sinh viên tối đa mà đề tài cho phép
    if active.filter(thesis_id=thesis["id"]).count() >= thesis["max_students"]:
        return "Thesis has reached maximum students"

    # BƯỚC 4b: Sinh viên đã có đủ số đăng ký còn hiệu lực chưa?
    # Mỗi sinh viên chỉ có một đăng ký còn hiệu lực.
    if active.filter(student_id=student_id).count() >= 1:
        return "Student already has an active registration"

    # BƯỚC 5: Tất cả điều kiện đều hợp lệ
    return None


logger = logging.getLogger(__name__)
LOCK_RETRIES = 3


class RegistrationDatabaseError(APIException):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_detail = {"error": "Registration database error; check migrations and server logs"}
    default_code = "registration_database_error"


def is_retryable_lock_error(exc):
    """Chỉ thử lại khi SQL Server báo deadlock/hết thời gian chờ khóa, không thử lại mọi lỗi database."""
    if not isinstance(exc, OperationalError):
        return False
    current = exc
    seen = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        for arg in current.args:
            value = str(arg).strip()
            if value in {"40001", "1205", "1222"}:
                return True
            if re.search(r"\((1205|1222)\)|\bdeadlock(?:ed)?\b", value, re.IGNORECASE):
                return True
        current = current.__cause__
    return False


def run_locked(student_id, thesis_id, work):
    """
    Chạy work() trong MỘT transaction, sau khi khóa đề tài và sinh viên.

    - Dòng khóa được tạo sẵn (tự commit) trước khi mở transaction.
    - Nếu SQL Server vẫn chọn request này làm "nạn nhân" deadlock thì thử lại
      tối đa LOCK_RETRIES lần; vẫn không được thì trả 503. Lỗi DB khác trả 500 có log, không retry.
    BusinessRuleError và IntegrityError được ném ra ngoài cho view xử lý.
    """
    keys = (f"thesis:{thesis_id}", f"student:{student_id}")
    for attempt in range(1, LOCK_RETRIES + 1):
        try:
            RegistrationLock.ensure(*keys)
            with transaction.atomic():
                RegistrationLock.acquire(*keys)
                return work()
        except IntegrityError:
            raise
        except DatabaseError as exc:
            if not is_retryable_lock_error(exc):
                logger.exception("Non-retryable registration database failure")
                raise RegistrationDatabaseError() from exc
            if attempt == LOCK_RETRIES:
                raise RegistrationBusy() from exc
            time.sleep(random.uniform(0.05, 0.2) * attempt)


def run_remote_rules(student_id, thesis_id, token):
    """Gọi Bước 1-3; đổi lỗi kết nối thành response 503 / 502."""
    try:
        return check_remote_rules(student_id, thesis_id, token)
    except ServiceUnavailableError as exc:
        # Nếu service cần gọi không khả dụng, trả về lỗi HTTP 503 Service Unavailable
        raise UpstreamUnavailable({"error": str(exc)})
    except ServiceAuthError as exc:
        # Service kia từ chối token -> lỗi ở phía service được gọi: 502 Bad Gateway
        raise UpstreamRejected({"error": str(exc)})


ERROR_RESPONSES = {400: ErrorSerializer, 403: ErrorSerializer, 500: ErrorSerializer, 502: ErrorSerializer, 503: ErrorSerializer}
STATUS_ENUM = [s.value for s in Registration.Status]


@extend_schema_view(
    get=extend_schema(
        summary="Danh sách đăng ký (có filter, giới hạn theo người gọi)",
        parameters=[
            OpenApiParameter("student_id", int, description="Lọc theo sinh viên"),
            OpenApiParameter("thesis_id", int, description="Lọc theo đề tài"),
            OpenApiParameter("status", str, enum=STATUS_ENUM, description="Lọc theo trạng thái"),
            OpenApiParameter("active", bool, description="true: chỉ đăng ký còn hiệu lực (PENDING, APPROVED)"),
        ],
    ),
    post=extend_schema(
        summary="Đăng ký đề tài (gọi Student Service + Thesis Service)",
        responses={201: RegistrationSerializer, **ERROR_RESPONSES},
    ),
)
class RegistrationListCreateView(generics.ListCreateAPIView):
    """
    Danh sách đăng ký và tạo đăng ký mới.

    GET  /api/registrations/?student_id=1&thesis_id=1&status=APPROVED&active=true
    POST /api/registrations/   body: {"student_id": 1, "thesis_id": 1}
    """

    # Chỉ định serializer dùng để chuyển đổi dữ liệu và kiểm tra đầu vào
    serializer_class = RegistrationSerializer

    # Phân quyền theo vai trò (xem bảng REGISTRATION_WRITE_ROLES ở trên)
    permission_classes = [IsAuthenticated, RolePermission]
    read_roles = ALL_ROLES
    write_roles = REGISTRATION_WRITE_ROLES

    # Hàm xác định danh sách đăng ký cần trả về khi client gửi GET
    # (chỉ trong phạm vi được phép của người gọi)
    def get_queryset(self):
        queryset = scoped_registrations(self.request)
        params = self.request.query_params
        if params.get("student_id", "").isdigit():
            queryset = queryset.filter(student_id=params["student_id"])
        if params.get("thesis_id", "").isdigit():
            queryset = queryset.filter(thesis_id=params["thesis_id"])
        if params.get("status"):
            queryset = queryset.filter(status=params["status"].upper())
        if params.get("active", "").lower() in ("1", "true"):
            queryset = queryset.filter(status__in=Registration.ACTIVE_STATUSES)
        return queryset

    # Phương thức này được gọi khi client gửi yêu cầu POST
    def create(self, request, *args, **kwargs):
        # Tạo serializer từ dữ liệu client gửi lên trong request.data
        # Ví dụ JSON: {"student_id": 1, "thesis_id": 1}
        serializer = self.get_serializer(data=request.data)

        # Kiểm tra dữ liệu theo các quy tắc đã định nghĩa trong serializer
        # Nếu không hợp lệ, DRF tự trả về lỗi validation
        serializer.is_valid(raise_exception=True)

        # Lấy mã sinh viên sau khi dữ liệu đã được xác thực
        student_id = serializer.validated_data["student_id"]

        # Lấy mã đề tài sau khi dữ liệu đã được xác thực
        thesis_id = serializer.validated_data["thesis_id"]

        # Sinh viên chỉ được đăng ký cho chính mình (student_id lấy từ token)
        if is_student(request.user):
            if request.user.student_id is None:
                return error_response(
                    "Your account is not linked to a student record",
                    status.HTTP_403_FORBIDDEN,
                )
            if student_id != request.user.student_id:
                return error_response(
                    "Students can only register for themselves",
                    status.HTTP_403_FORBIDDEN,
                )


        # Kiểm tra trong cơ sở dữ liệu của Registration Service
        # xem sinh viên đã đăng ký đề tài này hay chưa.
        # Đăng ký cũ đã bị hủy / từ chối thì được đăng ký lại (dùng lại dòng cũ).
        existing = Registration.objects.filter(student_id=student_id, thesis_id=thesis_id).first()
        if existing is not None and existing.is_active:

            # Nếu đã đăng ký, trả về thông báo lỗi
            # Không tiếp tục xử lý tạo bản ghi
            return error_response(
                "Student has already registered for this thesis"
            )

        # kiểm tra nghiệp vụ bằng cách gọi các service khác
        # qua HTTP/REST, chẳng hạn Student Service và Thesis Service
        # (chuyển tiếp access token của người dùng)
        error, thesis = run_remote_rules(student_id, thesis_id, request.auth)

        # Nếu kiểm tra nghiệp vụ phát hiện lỗi,
        # trả về thông báo lỗi và không lưu đăng ký
        if error:
            return error_response(error)

        # Bước 4 + 5: khóa đề tài và sinh viên, đếm lại, rồi mới lưu.
        # Mọi thứ trong khối này nằm trong MỘT transaction của registration_db.
        def save_registration():
            if existing is not None:
                current = Registration.objects.select_for_update().get(pk=existing.pk)
                if current.is_active:
                    raise BusinessRuleError("Student has already registered for this thesis")
            error = check_local_limits(
                student_id, thesis,
                exclude_registration_id=existing.id if existing else None,
            )
            if error:
                raise BusinessRuleError(error)

            if existing is not None:
                # Đăng ký lại đề tài đã hủy / bị từ chối trước đó
                registration = Registration.objects.select_for_update().get(pk=existing.pk)
                registration.status = Registration.Status.PENDING
                registration.registered_at = timezone.now()
                registration.processed_by = None
                registration.processed_at = None
                registration.reject_reason = ""
                registration.cancelled_by = None
                registration.cancelled_at = None
                registration.save()
                return registration
            return Registration.objects.create(
                student_id=student_id, thesis_id=thesis_id
            )

        try:
            registration = run_locked(student_id, thesis_id, save_registration)

        except BusinessRuleError as exc:
            return error_response(str(exc))

        # Xử lý trường hợp hai yêu cầu cùng lúc tạo đăng ký trùng nhau
        # và cơ sở dữ liệu từ chối một trong các yêu cầu
        except IntegrityError:

            # Trả về lỗi nếu đăng ký bị trùng
            return error_response(
                "Student has already registered for this thesis"
            )

        # Nếu lưu thành công, trả dữ liệu đăng ký về cho client
        # trạng thái HTTP 201 Created nghĩa là tài nguyên mới đã được tạo
        return Response(
            RegistrationSerializer(registration).data,
            status=status.HTTP_201_CREATED
        )


@extend_schema_view(
    put=extend_schema(summary="Duyệt / từ chối đăng ký", responses={200: RegistrationUpdateSerializer, **ERROR_RESPONSES}),
    patch=extend_schema(summary="Duyệt / từ chối đăng ký", responses={200: RegistrationUpdateSerializer, **ERROR_RESPONSES}),
    delete=extend_schema(summary="Xóa hẳn đăng ký (chỉ ADMIN; sinh viên dùng /cancel/)"),
)
class RegistrationDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET    /api/registrations/{id}/
    PUT    /api/registrations/{id}/  body: {"status": "APPROVED"}                         (ADMIN, GVHD)
    PATCH  /api/registrations/{id}/  body: {"status": "REJECTED", "reject_reason": "..."} (ADMIN, GVHD)
    DELETE /api/registrations/{id}/                                                         (ADMIN)

    Đăng ký ngoài phạm vi của người gọi trả về 404.
    """

    permission_classes = [IsAuthenticated, RolePermission]
    read_roles = ALL_ROLES
    write_roles = REGISTRATION_WRITE_ROLES

    def get_queryset(self):
        return scoped_registrations(self.request)

    def get_serializer_class(self):
        if self.request.method in ("PUT", "PATCH"):
            return RegistrationUpdateSerializer
        return RegistrationSerializer

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        if instance.status == Registration.Status.CANCELLED:
            return error_response("Cancelled registrations cannot be changed")

        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        new_status = serializer.validated_data.get("status", instance.status)
        reopening = instance.status == Registration.Status.REJECTED and new_status != instance.status

        thesis = None
        if reopening:
            # Đăng ký đã bị REJECTED nay được mở lại -> phải kiểm tra lại các điều kiện
            error, thesis = run_remote_rules(instance.student_id, instance.thesis_id, request.auth)
            if error:
                return error_response(error)

        extra = {}
        if new_status != instance.status:
            if new_status in (Registration.Status.APPROVED, Registration.Status.REJECTED):
                # Ghi nhận người duyệt và thời điểm xử lý
                extra = {"processed_by": request.user.id, "processed_at": timezone.now()}
            else:
                extra = {"processed_by": None, "processed_at": None}

        def save_status():
            current = Registration.objects.select_for_update().get(pk=instance.pk)
            if current.status != instance.status:
                raise BusinessRuleError("Registration changed; please reload and try again")
            if new_status != Registration.Status.APPROVED and (current.grades.exists() or current.grade_history.exists()):
                raise BusinessRuleError("Registration has grading records and must remain approved")
            if reopening:
                error = check_local_limits(
                    instance.student_id, thesis, exclude_registration_id=instance.id
                )
                if error:
                    raise BusinessRuleError(error)
            serializer.save(**extra)

        try:
            if reopening:
                run_locked(instance.student_id, instance.thesis_id, save_status)
            else:
                with transaction.atomic():
                    save_status()
        except BusinessRuleError as exc:
            return error_response(str(exc))

        return Response(serializer.data)

    def destroy(self, request, *args, **kwargs):
        # Xóa hẳn chỉ dành cho ADMIN (dọn dữ liệu sai). Sinh viên dùng POST /cancel/.
        with transaction.atomic():
            obj = self.get_object()
            obj = Registration.objects.select_for_update().get(pk=obj.pk)
            if (obj.grades.exists() or obj.grade_history.exists()):
                return error_response("Registration has grading records", status.HTTP_409_CONFLICT)
            obj.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class RegistrationCancelView(generics.GenericAPIView):
    """
    POST /api/registrations/{id}/cancel/

    - Sinh viên: chỉ hủy đăng ký của mình khi còn PENDING.
    - Admin: hủy được đăng ký PENDING hoặc APPROVED.
    Đăng ký không bị xóa mà chuyển sang CANCELLED (giữ lịch sử, trả lại chỗ cho đề tài).
    """

    serializer_class = RegistrationSerializer
    permission_classes = [IsAuthenticated, RolePermission]
    read_roles = ()
    write_roles = {"POST": (ADMIN, STUDENT)}

    def get_queryset(self):
        return scoped_registrations(self.request)

    @extend_schema(summary="Hủy đăng ký", request=None, responses={200: RegistrationSerializer, **ERROR_RESPONSES})
    def post(self, request, pk):
        with transaction.atomic():
            registration = self.get_object()
            registration = Registration.objects.select_for_update().get(pk=registration.pk)
            if (registration.grades.exists() or registration.grade_history.exists()):
                return error_response("Registration has grading records", status.HTTP_409_CONFLICT)
            if registration.status == Registration.Status.CANCELLED:
                return error_response("Registration is already cancelled")
            if is_student(request.user):
                if registration.status != Registration.Status.PENDING:
                    return error_response("Only pending registrations can be cancelled")
            elif not registration.is_active:
                return error_response("Only pending or approved registrations can be cancelled")

            registration.status = Registration.Status.CANCELLED
            registration.cancelled_by = request.user.id
            registration.cancelled_at = timezone.now()
            registration.save(update_fields=["status", "cancelled_by", "cancelled_at"])
        return Response(RegistrationSerializer(registration).data)


class ProgressNoteListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/registrations/{id}/notes/   nhận xét / tiến độ (người xem được đăng ký đều đọc được)
    POST /api/registrations/{id}/notes/   {"content": "...", "progress": 40}   (ADMIN, GVHD của đề tài)
    Chỉ ghi được cho đăng ký đã APPROVED.
    """

    serializer_class = ProgressNoteSerializer
    permission_classes = [IsAuthenticated, RolePermission]
    read_roles = ALL_ROLES
    write_roles = {"POST": (ADMIN, LECTURER)}

    def get_registration(self):
        return generics.get_object_or_404(scoped_registrations(self.request), pk=self.kwargs["pk"])

    def get_queryset(self):
        return ProgressNote.objects.filter(registration=self.get_registration())

    def create(self, request, *args, **kwargs):
        registration = self.get_registration()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            registration = generics.get_object_or_404(
                Registration.objects.select_for_update(), pk=registration.pk
            )
            if registration.status != Registration.Status.APPROVED:
                return error_response("Progress notes can only be added to approved registrations")
            serializer.save(
                registration=registration,
                author_id=request.user.id,
                author_name=request.user.full_name,
                author_role=request.user.role,
            )
        return Response(serializer.data, status=status.HTTP_201_CREATED)
