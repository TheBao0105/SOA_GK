import re
from django.db import transaction
from rest_framework import serializers
from .models import Student, StudentCodeSequence

PREFIX = "SV"
PATTERN = re.compile(r"SV([0-9]+)\Z", re.IGNORECASE)
MAX_NUMBER = 10 ** 18 - 1  # tiền tố + 18 chữ số vừa với cột dài 20 ký tự hiện có


@transaction.atomic
def create_with_code(validated_data):
    # Dòng bộ đếm duy nhất đã được migration tạo sẵn, nên không có tranh chấp khi chèn dòng lần đầu.
    counter = StudentCodeSequence.objects.select_for_update().get(pk=1)
    data = dict(validated_data)
    if not data.get("student_code"):
        # Đối chiếu với các mã đã nhập tay/seed từ phiên bản cũ. Dữ liệu demo nhỏ nên quét đơn giản là đủ.
        highest = counter.value
        for code in Student.objects.filter(student_code__startswith=PREFIX).values_list("student_code", flat=True).iterator():
            match = PATTERN.fullmatch(code)
            if match:
                highest = max(highest, int(match.group(1)))
        if highest >= MAX_NUMBER:
            raise serializers.ValidationError({"student_code": "Dãy mã tự động đã hết phạm vi."})
        counter.value = highest + 1
        data["student_code"] = f"{PREFIX}{counter.value:03d}"
    else:
        # Vẫn cho phép truyền mã cụ thể để tương thích seed/import/API client cũ.
        if Student.objects.filter(student_code=data["student_code"]).exists():
            raise serializers.ValidationError({"student_code": "Mã đã tồn tại."})
        match = PATTERN.fullmatch(data["student_code"])
        if match:
            counter.value = max(counter.value, int(match.group(1)))
    obj = Student.objects.create(**data)
    counter.save(update_fields=["value"])
    return obj
