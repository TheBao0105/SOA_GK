from django.db import transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from config.permissions import ADMIN, LECTURER, STUDENT, RolePermission
from registrations.models import Registration
from registrations.views import scoped_registrations
from .models import Grade, GradeHistory
from .serializers import GradeSerializer, GradeInputSerializer, GradeHistorySerializer


class GradeViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = Grade.objects.all()
    serializer_class = GradeSerializer
    permission_classes = [IsAuthenticated, RolePermission]
    read_roles = (ADMIN, LECTURER, STUDENT)
    write_roles = {"POST": (ADMIN, LECTURER), "DELETE": (ADMIN, LECTURER)}

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Grade.objects.none()
        # Phạm vi của giảng viên lấy từ Thesis Service qua REST; không truy vấn xuyên database.
        return Grade.objects.select_related("registration").filter(registration__in=scoped_registrations(self.request))

    @extend_schema(request=GradeInputSerializer, responses={200: GradeSerializer, 201: GradeSerializer})
    def create(self, request):
        """Nhập hoặc sửa trực tiếp điểm 0–10 cho đăng ký đã duyệt thuộc đề tài hướng dẫn."""
        data = GradeInputSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        # Kiểm tra quyền sở hữu qua HTTP xong rồi mới khóa dữ liệu trong database.
        registration = get_object_or_404(scoped_registrations(request), pk=values["registration"])
        with transaction.atomic():
            registration = Registration.objects.select_for_update().get(pk=registration.pk)
            if registration.status != Registration.Status.APPROVED:
                raise serializers.ValidationError({"registration": "Chỉ chấm đăng ký đã được duyệt."})
            grade = Grade.objects.filter(registration=registration).first()
            created = grade is None
            before = None if created else {"score": str(grade.score), "comment": grade.comment, "lecturer_id": grade.lecturer_id}
            if created:
                grade = Grade(registration=registration)
            grade.score, grade.comment = values["score"], values["comment"]
            grade.lecturer_id, grade.lecturer_name = request.user.id, request.user.full_name
            grade.save()
            GradeHistory.objects.create(registration=registration, grade=grade, actor_id=request.user.id,
                action="CREATED" if created else "UPDATED",
                detail={"before": before, "after": {"score": str(grade.score), "comment": grade.comment, "lecturer_id": grade.lecturer_id}})
        return Response(self.get_serializer(grade).data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    @extend_schema(responses={204: None})
    def destroy(self, request, pk=None):
        # Cùng thứ tự khóa với lúc lưu điểm: khóa đăng ký trước, rồi đến điểm.
        visible = self.get_object()
        with transaction.atomic():
            registration = Registration.objects.select_for_update().get(pk=visible.registration_id)
            grade = get_object_or_404(Grade, pk=visible.pk)
            before = {"grade_id":grade.pk, "score":str(grade.score), "comment":grade.comment,
                      "lecturer_id":grade.lecturer_id, "lecturer_name":grade.lecturer_name}
            # Giữ lại lịch sử điểm khi xóa điểm hiện tại.
            GradeHistory.objects.filter(grade=grade).update(grade=None)
            GradeHistory.objects.create(registration=registration, actor_id=request.user.id,
                action="DELETED", detail={"before":before, "after":None})
            grade.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(responses=GradeHistorySerializer(many=True))
    @action(detail=True, methods=["get"])
    def history(self, request, pk=None):
        if request.user.role not in (ADMIN, LECTURER):
            raise PermissionDenied()
        grade = self.get_object()
        return Response(GradeHistorySerializer(GradeHistory.objects.filter(registration=grade.registration), many=True).data)
