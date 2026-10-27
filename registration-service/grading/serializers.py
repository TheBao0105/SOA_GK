import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from rest_framework import serializers
from .models import Assessment, GradeEvent, GradingAssignment, GradingPeriod


class GradingPeriodSerializer(serializers.ModelSerializer):
    is_open = serializers.SerializerMethodField()

    class Meta:
        model = GradingPeriod
        fields = ["id", "name", "start_at", "end_at", "is_active", "criteria", "is_open", "created_at"]
        read_only_fields = ["id", "created_at"]

    def get_is_open(self, obj) -> bool:
        return obj.is_open()

    def validate_criteria(self, value):
        if not isinstance(value, list) or not 1 <= len(value) <= 30:
            raise serializers.ValidationError("Cần từ 1 đến 30 tiêu chí.")
        result, codes, total = [], set(), Decimal(0)
        for item in value:
            if not isinstance(item, dict):
                raise serializers.ValidationError("Tiêu chí phải có code, name, weight.")
            code, name = str(item.get("code", "")), str(item.get("name", "")).strip()
            try:
                weight = Decimal(str(item["weight"]))
                valid = weight.is_finite() and 0 < weight <= 100 and weight.as_tuple().exponent >= -2
            except (KeyError, InvalidOperation, ValueError):
                valid = False
            if not re.fullmatch(r"[a-z][a-z0-9_]{0,29}", code) or code in codes or not name or len(name) > 150:
                raise serializers.ValidationError("Mã tiêu chí phải duy nhất, dùng chữ thường/số/gạch dưới; tên tối đa 150 ký tự.")
            if not valid:
                raise serializers.ValidationError("Trọng số phải lớn hơn 0, tối đa 100 và có tối đa 2 số thập phân.")
            total += weight
            codes.add(code)
            result.append({"code": code, "name": name, "weight": format(weight.normalize(), "f")})
        if total != 100:
            raise serializers.ValidationError("Tổng trọng số phải bằng 100%.")
        return result

    def validate(self, attrs):
        start = attrs.get("start_at", getattr(self.instance, "start_at", None))
        end = attrs.get("end_at", getattr(self.instance, "end_at", None))
        if start and end and end <= start:
            raise serializers.ValidationError({"end_at": "Kết thúc phải sau bắt đầu."})
        if self.instance and "criteria" in attrs and self.instance.assessments.exists() and attrs["criteria"] != self.validate_criteria(self.instance.criteria):
            raise serializers.ValidationError({"criteria": "Đã có hồ sơ chấm; hãy tạo đợt mới để đổi tiêu chí."})
        return attrs


class AssignmentSerializer(serializers.ModelSerializer):
    total = serializers.SerializerMethodField()

    class Meta:
        model = GradingAssignment
        fields = ["id", "lecturer_id", "lecturer_name", "scores", "comment", "submitted_at", "updated_at", "total"]

    def get_total(self, obj) -> str | None:
        return str(obj.total(obj.assessment.period.criteria).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)) if obj.submitted_at else None


class AssessmentSerializer(serializers.ModelSerializer):
    student_id = serializers.IntegerField(source="registration.student_id", read_only=True)
    thesis_id = serializers.IntegerField(source="registration.thesis_id", read_only=True)
    period_name = serializers.CharField(source="period.name", read_only=True)
    criteria = serializers.JSONField(source="period.criteria", read_only=True)
    assignments = AssignmentSerializer(many=True, read_only=True)

    class Meta:
        model = Assessment
        fields = ["id", "registration", "student_id", "thesis_id", "period", "period_name", "criteria", "status", "final_score", "published_by", "published_at", "created_by", "created_at", "assignments"]
        read_only_fields = fields


class AssessmentCreateSerializer(serializers.Serializer):
    registration = serializers.IntegerField(min_value=1)
    period = serializers.IntegerField(min_value=1)


class AssignSerializer(serializers.Serializer):
    lecturer_ids = serializers.ListField(child=serializers.IntegerField(min_value=1), min_length=1, max_length=20)

    def validate_lecturer_ids(self, value):
        if len(value) != len(set(value)):
            raise serializers.ValidationError("Giảng viên không được trùng nhau.")
        return value


class ScoreSerializer(serializers.Serializer):
    scores = serializers.DictField(child=serializers.DecimalField(max_digits=4, decimal_places=2, min_value=0, max_value=10))
    comment = serializers.CharField(required=False, allow_blank=True, max_length=5000, default="")
    submit = serializers.BooleanField(default=False)


class ReopenSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=500, allow_blank=False)


class GradeEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = GradeEvent
        fields = ["id", "actor_id", "action", "detail", "created_at"]
