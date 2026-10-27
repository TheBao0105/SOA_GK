from django.conf import settings
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from config.permissions import ADMIN, LECTURER, STUDENT, RolePermission
from registrations.models import Registration
from registrations.services.external_api import _get_json, validate_account, ServiceAuthError, ServiceUnavailableError
from registrations.views import UpstreamRejected, UpstreamUnavailable
from .models import Assessment, GradeEvent, GradingAssignment, GradingPeriod
from .serializers import (AssessmentCreateSerializer, AssessmentSerializer, AssignSerializer,
                          GradeEventSerializer, GradingPeriodSerializer, ReopenSerializer, ScoreSerializer)


def record(assessment, request, action_name, detail=None):
    GradeEvent.objects.create(assessment=assessment, actor_id=request.user.id, action=action_name, detail=detail or {})


class GradingPeriodViewSet(viewsets.ModelViewSet):
    queryset = GradingPeriod.objects.all()
    serializer_class = GradingPeriodSerializer
    permission_classes = [IsAuthenticated, RolePermission]
    read_roles = (ADMIN, LECTURER)
    write_roles = {"POST": (ADMIN,), "PATCH": (ADMIN,), "PUT": (ADMIN,)}
    http_method_names = ["get", "post", "patch", "put", "head", "options"]

    def update(self, request, *args, **kwargs):
        # Lock the same period row as assessment creation to freeze the rubric atomically.
        with transaction.atomic():
            period = get_object_or_404(GradingPeriod.objects.select_for_update(), pk=kwargs["pk"])
            data = self.get_serializer(period, data=request.data, partial=kwargs.get("partial", False))
            data.is_valid(raise_exception=True)
            data.save()
        return Response(data.data)


class AssessmentViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = AssessmentSerializer
    queryset = Assessment.objects.all()
    permission_classes = [IsAuthenticated, RolePermission]
    read_roles = (ADMIN, LECTURER, STUDENT)
    write_roles = {"POST": (ADMIN, LECTURER)}

    def get_queryset(self):
        qs = Assessment.objects.select_related("registration", "period").prefetch_related("assignments")
        if getattr(self, "swagger_fake_view", False):
            return qs.none()
        user = self.request.user
        if user.role == STUDENT:
            qs = qs.filter(registration__student_id=user.student_id, status=Assessment.Status.PUBLISHED)
        elif user.role == LECTURER:
            qs = qs.filter(assignments__lecturer_id=user.id).distinct()
        elif user.role != ADMIN:
            return qs.none()
        for key in ("period", "registration"):
            value = self.request.query_params.get(key)
            if value:
                if not value.isdigit():
                    raise serializers.ValidationError({key: "ID không hợp lệ."})
                qs = qs.filter(**{key + "_id": value})
        return qs

    def require_admin(self):
        if self.request.user.role != ADMIN:
            raise PermissionDenied("Chỉ Admin được thực hiện thao tác này.")

    def locked(self):
        obj = self.get_object()
        # Consistent ordering: period, assessment. Recheck lecturer scope after waiting.
        GradingPeriod.objects.select_for_update().get(pk=obj.period_id)
        obj = Assessment.objects.select_for_update().get(pk=obj.pk)
        if self.request.user.role == LECTURER and not obj.assignments.filter(lecturer_id=self.request.user.id).exists():
            raise PermissionDenied()
        return obj

    @extend_schema(request=AssessmentCreateSerializer, responses={201: AssessmentSerializer})
    def create(self, request):
        self.require_admin()
        data = AssessmentCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                period = get_object_or_404(GradingPeriod.objects.select_for_update(), pk=data.validated_data["period"])
                registration = get_object_or_404(Registration.objects.select_for_update(), pk=data.validated_data["registration"])
                if registration.status != Registration.Status.APPROVED:
                    raise serializers.ValidationError("Chỉ chấm đăng ký đã được duyệt.")
                obj = Assessment.objects.create(period=period, registration=registration, created_by=request.user.id)
                record(obj, request, "CREATED")
        except IntegrityError:
            raise serializers.ValidationError("Đăng ký đã có hồ sơ chấm trong đợt này.")
        return Response(self.get_serializer(obj).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=AssignSerializer)
    @action(detail=True, methods=["post"])
    def assign(self, request, pk=None):
        self.require_admin()
        self.get_object()
        data = AssignSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        lecturers = {}
        # HTTP validation precedes database locks; never access auth_db directly.
        for lecturer_id in data.validated_data["lecturer_ids"]:
            try:
                user = _get_json("Identity Service", f"{settings.IDENTITY_SERVICE_URL}/api/users/{lecturer_id}/", request.auth)
                if user is not None:
                    validate_account(user, lecturer_id)
            except ServiceUnavailableError as exc:
                raise UpstreamUnavailable({"error": str(exc)})
            except ServiceAuthError as exc:
                raise UpstreamRejected({"error": str(exc)})
            if not isinstance(user, dict) or user.get("role") != LECTURER or not user.get("is_active"):
                raise serializers.ValidationError({"lecturer_ids": f"Tài khoản {lecturer_id} không phải giảng viên đang hoạt động."})
            lecturers[lecturer_id] = user.get("full_name") or user.get("username") or str(lecturer_id)
        with transaction.atomic():
            obj = self.locked()
            if obj.status == Assessment.Status.PUBLISHED or obj.assignments.filter(submitted_at__isnull=False).exists():
                raise serializers.ValidationError("Đã nộp/công bố điểm; Admin phải mở lại trước khi đổi phân công.")
            old = list(obj.assignments.values("lecturer_id", "scores", "comment"))
            obj.assignments.exclude(lecturer_id__in=lecturers).delete()
            for uid, name in lecturers.items():
                GradingAssignment.objects.update_or_create(assessment=obj, lecturer_id=uid, defaults={"lecturer_name": name})
            obj.recalculate()
            record(obj, request, "ASSIGNED", {"before": old, "lecturer_ids": list(lecturers)})
        return Response(self.get_serializer(obj).data)

    @extend_schema(request=ScoreSerializer)
    @action(detail=True, methods=["post"])
    def scores(self, request, pk=None):
        if request.user.role != LECTURER:
            raise PermissionDenied("Chỉ giảng viên được phân công mới được chấm.")
        data = ScoreSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        with transaction.atomic():
            obj = self.locked()
            if obj.status == Assessment.Status.PUBLISHED or not obj.period.is_open():
                raise serializers.ValidationError("Đã công bố hoặc đợt chấm đã đóng.")
            mark = get_object_or_404(GradingAssignment, assessment=obj, lecturer_id=request.user.id)
            if mark.submitted_at:
                raise serializers.ValidationError("Đã nộp điểm; cần Admin mở lại để sửa.")
            values = data.validated_data
            required = {c["code"] for c in obj.period.criteria}
            given = set(values["scores"])
            if given - required or (values["submit"] and given != required):
                raise serializers.ValidationError({"scores": "Mã tiêu chí không hợp lệ hoặc chưa chấm đủ tiêu chí."})
            before = {"scores": mark.scores, "comment": mark.comment}
            mark.scores = {k: str(v) for k, v in values["scores"].items()}
            mark.comment = values["comment"]
            mark.submitted_at = timezone.now() if values["submit"] else None
            mark.save()
            obj.recalculate()
            record(obj, request, "SUBMITTED" if values["submit"] else "SCORE_SAVED", {
                "lecturer_id": request.user.id, "before": before,
                "after": {"scores": mark.scores, "comment": mark.comment}})
        return Response(self.get_serializer(obj).data)

    @extend_schema(request=None)
    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        self.require_admin()
        with transaction.atomic():
            obj = self.locked()
            if obj.status == Assessment.Status.PUBLISHED:
                raise serializers.ValidationError("Kết quả đã được công bố.")
            obj.recalculate()
            if obj.status != Assessment.Status.GRADED:
                raise serializers.ValidationError("Tất cả giảng viên được phân công phải nộp điểm trước khi công bố.")
            obj.status = Assessment.Status.PUBLISHED
            obj.published_by, obj.published_at = request.user.id, timezone.now()
            obj.save(update_fields=["status", "published_by", "published_at"])
            record(obj, request, "PUBLISHED", {"final_score": str(obj.final_score)})
        return Response(self.get_serializer(obj).data)

    @extend_schema(request=ReopenSerializer)
    @action(detail=True, methods=["post"])
    def reopen(self, request, pk=None):
        self.require_admin()
        data = ReopenSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        with transaction.atomic():
            obj = self.locked()
            before = {"status": obj.status, "final_score": str(obj.final_score),
                      "assignments": list(obj.assignments.values("lecturer_id", "scores", "comment"))}
            obj.assignments.update(submitted_at=None)
            obj.published_by = obj.published_at = None
            obj.save(update_fields=["published_by", "published_at"])
            obj.recalculate()
            record(obj, request, "REOPENED", {"reason": data.validated_data["reason"], "before": before})
        return Response(self.get_serializer(obj).data)

    @extend_schema(responses=GradeEventSerializer(many=True))
    @action(detail=True, methods=["get"])
    def history(self, request, pk=None):
        if request.user.role not in (ADMIN, LECTURER):
            raise PermissionDenied()
        obj = self.get_object()
        return Response(GradeEventSerializer(obj.events.all(), many=True).data)
