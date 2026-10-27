from rest_framework import serializers

from .models import ProgressNote, Registration, RegistrationPeriod


class RegistrationSerializer(serializers.ModelSerializer):
    """
    Dùng cho GET và POST.

    Khi tạo mới, client chỉ gửi student_id và thesis_id.
    status mặc định là PENDING (giảng viên duyệt sau bằng PUT/PATCH).
    """

    class Meta:
        model = Registration
        fields = [
            "id", "student_id", "thesis_id", "period", "registered_at", "status",
            "processed_by", "processed_at", "reject_reason", "cancelled_by", "cancelled_at",
        ]
        read_only_fields = [
            "id", "period", "registered_at", "status",
            "processed_by", "processed_at", "reject_reason", "cancelled_by", "cancelled_at",
        ]
        # Tắt validator "unique together" tự động của DRF để view tự trả về
        # thông báo lỗi dạng {"error": "..."} cho thống nhất.
        validators = []


class RegistrationUpdateSerializer(serializers.ModelSerializer):
    """
    Dùng cho PUT / PATCH: chỉ được đổi status (PENDING / APPROVED / REJECTED).
    Từ chối (REJECTED) bắt buộc kèm lý do. Hủy dùng POST /cancel/.
    Muốn đổi sinh viên hoặc đề tài thì hủy đăng ký cũ và tạo đăng ký mới.
    """

    status = serializers.ChoiceField(
        choices=[Registration.Status.PENDING, Registration.Status.APPROVED, Registration.Status.REJECTED]
    )
    reject_reason = serializers.CharField(required=False, allow_blank=True, max_length=255)

    class Meta:
        model = Registration
        fields = RegistrationSerializer.Meta.fields
        read_only_fields = [
            "id", "student_id", "thesis_id", "period", "registered_at",
            "processed_by", "processed_at", "cancelled_by", "cancelled_at",
        ]

    def validate(self, attrs):
        new_status = attrs.get("status", self.instance.status if self.instance else None)
        if new_status == Registration.Status.REJECTED:
            reason = (attrs.get("reject_reason") or "").strip()
            if not reason:
                raise serializers.ValidationError({"reject_reason": ["A reason is required when rejecting."]})
            attrs["reject_reason"] = reason
        else:
            attrs["reject_reason"] = ""
        return attrs


class RegistrationPeriodSerializer(serializers.ModelSerializer):
    is_open = serializers.SerializerMethodField()

    class Meta:
        model = RegistrationPeriod
        fields = ["id", "name", "start_at", "end_at", "is_active", "max_active_per_student", "is_open", "created_at"]
        read_only_fields = ["id", "is_open", "created_at"]

    def get_is_open(self, obj) -> bool:
        return obj.is_open()

    def validate(self, attrs):
        start = attrs.get("start_at", getattr(self.instance, "start_at", None))
        end = attrs.get("end_at", getattr(self.instance, "end_at", None))
        if start and end and end <= start:
            raise serializers.ValidationError({"end_at": ["end_at must be after start_at."]})
        return attrs


class ProgressNoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProgressNote
        fields = ["id", "registration", "author_id", "author_name", "author_role", "content", "progress", "created_at"]
        read_only_fields = ["id", "registration", "author_id", "author_name", "author_role", "created_at"]

    def validate_content(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("content is required.")
        return value


class ErrorSerializer(serializers.Serializer):
    """Định dạng lỗi chung: {"error": "..."} (dùng cho Swagger)."""

    error = serializers.CharField()
