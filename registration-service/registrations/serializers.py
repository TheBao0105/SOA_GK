from rest_framework import serializers

from .models import Registration


class RegistrationSerializer(serializers.ModelSerializer):
    """
    Dùng cho GET và POST.

    Khi tạo mới, client chỉ gửi student_id và thesis_id.
    status mặc định là PENDING (giảng viên duyệt sau bằng PUT/PATCH).
    """

    class Meta:
        model = Registration
        fields = ["id", "student_id", "thesis_id", "registered_at", "status"]
        read_only_fields = ["id", "registered_at", "status"]
        # Tắt validator "unique together" tự động của DRF để view tự trả về
        # thông báo lỗi dạng {"error": "..."} cho thống nhất.
        validators = []


class RegistrationUpdateSerializer(serializers.ModelSerializer):
    """
    Dùng cho PUT / PATCH: chỉ được đổi status (PENDING / APPROVED / REJECTED).
    Muốn đổi sinh viên hoặc đề tài thì xóa đăng ký cũ và tạo đăng ký mới.
    """

    class Meta:
        model = Registration
        fields = ["id", "student_id", "thesis_id", "registered_at", "status"]
        read_only_fields = ["id", "student_id", "thesis_id", "registered_at"]


class ErrorSerializer(serializers.Serializer):
    """Định dạng lỗi chung: {"error": "..."} (dùng cho Swagger)."""

    error = serializers.CharField()
