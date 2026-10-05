from rest_framework import serializers

from .models import Thesis


class ThesisSerializer(serializers.ModelSerializer):
    """
    Validation:
    - thesis_code: unique (DRF tự sinh từ unique=True trong model)
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
            "max_students",
            "status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_thesis_code(self, value):
        value = value.strip().upper()
        if not value:
            raise serializers.ValidationError("thesis_code is required.")
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
