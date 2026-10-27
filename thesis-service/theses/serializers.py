from rest_framework import serializers
from django.db import transaction

from .models import Thesis, ThesisCodeSequence
from .codegen import PATTERN, create_with_code


class ThesisSerializer(serializers.ModelSerializer):
    """
    Validation:
    - thesis_code: tự sinh khi tạo nếu bỏ trống; mã cung cấp rõ ràng vẫn phải unique
    - title: bắt buộc
    - max_students > 0
    """

    class Meta:
        model = Thesis
        fields = [
            "id",
            "thesis_code",
            "title",
            "description",
            "supervisor",
            "supervisor_id",
            "max_students",
            "status",
            "created_at",
            "created_by",
            "updated_at",
        ]
        read_only_fields = ["id", "created_by", "created_at", "updated_at"]
        extra_kwargs = {"thesis_code": {"required": False, "allow_blank": True}}

    def validate_thesis_code(self, value):
        value = value.strip().upper()
        if not value and self.instance is not None:
            raise serializers.ValidationError("thesis_code cannot be blank on update.")
        if value:
            existing = Thesis.objects.filter(thesis_code=value)
            if self.instance is not None:
                existing = existing.exclude(pk=self.instance.pk)
            if existing.exists():
                raise serializers.ValidationError("Mã đã tồn tại.")
        return value

    def validate_title(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("title is required.")
        return value

    def validate_max_students(self, value):
        if value <= 0:
            raise serializers.ValidationError("max_students must be greater than 0.")
        return value


    def create(self, validated_data):
        return create_with_code(validated_data)

    def update(self, instance, validated_data):
        if "thesis_code" in validated_data:
            with transaction.atomic():
                counter = ThesisCodeSequence.objects.select_for_update().get(pk=1)
                code = validated_data["thesis_code"]
                if Thesis.objects.filter(thesis_code=code).exclude(pk=instance.pk).exists():
                    raise serializers.ValidationError({"thesis_code": "Mã đã tồn tại."})
                match = PATTERN.fullmatch(code)
                if match:
                    counter.value = max(counter.value, int(match.group(1)))
                    counter.save(update_fields=["value"])
                return super().update(instance, validated_data)
        return super().update(instance, validated_data)
