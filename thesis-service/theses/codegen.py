import re
from django.db import transaction
from rest_framework import serializers
from .models import Thesis, ThesisCodeSequence

PREFIX = "DT"
PATTERN = re.compile(r"DT([0-9]+)\Z", re.IGNORECASE)
MAX_NUMBER = 10 ** 18 - 1  # prefix + 18 digits fits the existing 20-character field


@transaction.atomic
def create_with_code(validated_data):
    # The singleton is created by the migration, so no lazy-insert race is needed.
    counter = ThesisCodeSequence.objects.select_for_update().get(pk=1)
    data = dict(validated_data)
    if not data.get("thesis_code"):
        # Reconcile codes imported/seeded by older code. This small demo uses a simple scan.
        highest = counter.value
        for code in Thesis.objects.filter(thesis_code__startswith=PREFIX).values_list("thesis_code", flat=True).iterator():
            match = PATTERN.fullmatch(code)
            if match:
                highest = max(highest, int(match.group(1)))
        if highest >= MAX_NUMBER:
            raise serializers.ValidationError({"thesis_code": "Dãy mã tự động đã hết phạm vi."})
        counter.value = highest + 1
        data["thesis_code"] = f"{PREFIX}{counter.value:03d}"
    else:
        # Explicit codes remain supported for existing seed/import/API clients.
        if Thesis.objects.filter(thesis_code=data["thesis_code"]).exists():
            raise serializers.ValidationError({"thesis_code": "Mã đã tồn tại."})
        match = PATTERN.fullmatch(data["thesis_code"])
        if match:
            counter.value = max(counter.value, int(match.group(1)))
    obj = Thesis.objects.create(**data)
    counter.save(update_fields=["value"])
    return obj
