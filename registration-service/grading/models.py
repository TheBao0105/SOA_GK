from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models


class Grade(models.Model):
    registration = models.ForeignKey("registrations.Registration", on_delete=models.PROTECT, related_name="grades")
    score = models.DecimalField(max_digits=4, decimal_places=2, validators=[MinValueValidator(0), MaxValueValidator(10)])
    comment = models.TextField(blank=True)
    lecturer_id = models.PositiveIntegerField(null=True)
    lecturer_name = models.CharField(max_length=150, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "diem_detai"
        ordering = ["id"]
        constraints = [models.UniqueConstraint(fields=["registration"], name="unique_registration_grade")]


class GradeHistory(models.Model):
    registration = models.ForeignKey("registrations.Registration", on_delete=models.PROTECT, related_name="grade_history")
    grade = models.ForeignKey(Grade, null=True, on_delete=models.PROTECT, related_name="history")
    actor_id = models.PositiveIntegerField(null=True)
    action = models.CharField(max_length=30)
    detail = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "lichsu_diem"
        ordering = ["-id"]
