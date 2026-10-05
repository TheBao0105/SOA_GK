from rest_framework import serializers

from .models import Student


class StudentSerializer(serializers.ModelSerializer):
    """
    Chuyển Student <-> JSON và kiểm tra dữ liệu đầu vào.

    Validation (phần lớn DRF tự sinh từ model):
    - student_code: bắt buộc, unique
    - full_name: bắt buộc
    - email: đúng định dạng email
    """

    class Meta:
        model = Student
        fields = [
            "id",
            "student_code",
            "full_name",
            "email",
            "class_name",
            "major",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_student_code(self, value):
        value = value.strip().upper()
        if not value:
            raise serializers.ValidationError("student_code is required.")
        return value

    def validate_full_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("full_name is required.")
        return value
