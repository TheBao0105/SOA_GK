from rest_framework import serializers
from django.db import transaction

from .models import Student, StudentCodeSequence
from .codegen import PATTERN, create_with_code


class StudentSerializer(serializers.ModelSerializer):
    """
    Chuyển Student <-> JSON và kiểm tra dữ liệu đầu vào.

    Validation (phần lớn DRF tự sinh từ model):
    - student_code: tự sinh khi tạo nếu bỏ trống; mã cung cấp rõ ràng vẫn phải unique
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
        extra_kwargs = {"student_code": {"required": False, "allow_blank": True}}

    def validate_student_code(self, value):
        value = value.strip().upper()
        if not value and self.instance is not None:
            raise serializers.ValidationError("student_code cannot be blank on update.")
        if value:
            existing = Student.objects.filter(student_code=value)
            if self.instance is not None:
                existing = existing.exclude(pk=self.instance.pk)
            if existing.exists():
                raise serializers.ValidationError("Mã đã tồn tại.")
        return value

    def validate_full_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("full_name is required.")
        return value


    def create(self, validated_data):
        return create_with_code(validated_data)

    def update(self, instance, validated_data):
        if "student_code" in validated_data:
            with transaction.atomic():
                counter = StudentCodeSequence.objects.select_for_update().get(pk=1)
                code = validated_data["student_code"]
                if Student.objects.filter(student_code=code).exclude(pk=instance.pk).exists():
                    raise serializers.ValidationError({"student_code": "Mã đã tồn tại."})
                match = PATTERN.fullmatch(code)
                if match:
                    counter.value = max(counter.value, int(match.group(1)))
                    counter.save(update_fields=["value"])
                return super().update(instance, validated_data)
        return super().update(instance, validated_data)
