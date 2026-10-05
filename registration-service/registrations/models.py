from django.db import models


class Registration(models.Model):
    """
    Bảng DANGKY - chỉ thuộc về Registration Service (registration_db).

    QUAN TRỌNG (SOA): student_id và thesis_id chỉ là số nguyên bình thường,
    KHÔNG phải ForeignKey, vì Student và Thesis nằm ở service/database khác.
    Việc kiểm tra tồn tại được thực hiện bằng cách gọi REST API.
    """

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    student_id = models.PositiveIntegerField()
    thesis_id = models.PositiveIntegerField()
    registered_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)

    class Meta:
        db_table = "dangky"
        ordering = ["id"]
        constraints = [
            # Một sinh viên không được đăng ký cùng một đề tài nhiều lần
            models.UniqueConstraint(
                fields=["student_id", "thesis_id"], name="unique_student_thesis"
            )
        ]

    def __str__(self):
        return f"Student {self.student_id} -> Thesis {self.thesis_id} [{self.status}]"
