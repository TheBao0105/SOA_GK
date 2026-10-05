from django.core.validators import MinValueValidator
from django.db import models


class Thesis(models.Model):
    """Bảng DETAI - chỉ thuộc về Thesis Service (thesis_db)."""

    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        CLOSED = "CLOSED", "Closed"

    thesis_code = models.CharField(max_length=20, unique=True)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    supervisor = models.CharField(max_length=100, blank=True)
    max_students = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "detai"
        ordering = ["id"]

    def __str__(self):
        return f"{self.thesis_code} - {self.title}"
