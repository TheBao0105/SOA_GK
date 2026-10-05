from django.db import models


class Student(models.Model):
    """Bảng SINHVIEN - chỉ thuộc về Student Service (student_db)."""

    student_code = models.CharField(max_length=20, unique=True)
    full_name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    class_name = models.CharField(max_length=50, blank=True)
    major = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "sinhvien"
        ordering = ["id"]

    def __str__(self):
        return f"{self.student_code} - {self.full_name}"
