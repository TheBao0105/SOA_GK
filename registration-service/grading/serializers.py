from rest_framework import serializers
from .models import Grade, GradeHistory


class GradeSerializer(serializers.ModelSerializer):
    student_id = serializers.IntegerField(source="registration.student_id", read_only=True)
    thesis_id = serializers.IntegerField(source="registration.thesis_id", read_only=True)

    class Meta:
        model = Grade
        fields = ["id", "registration", "student_id", "thesis_id", "score", "comment", "lecturer_id", "lecturer_name", "created_at", "updated_at"]
        read_only_fields = fields


class GradeInputSerializer(serializers.Serializer):
    registration = serializers.IntegerField(min_value=1)
    score = serializers.DecimalField(max_digits=4, decimal_places=2, min_value=0, max_value=10)
    comment = serializers.CharField(required=False, allow_blank=True, max_length=5000, default="")


class GradeHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = GradeHistory
        fields = ["id", "actor_id", "action", "detail", "created_at"]
