from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import IntegrityError, models, transaction


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
        CANCELLED = "CANCELLED", "Cancelled"

    # Đăng ký "còn hiệu lực": chiếm chỗ của đề tài và tính vào giới hạn của sinh viên
    ACTIVE_STATUSES = (Status.PENDING, Status.APPROVED)

    student_id = models.PositiveIntegerField()
    thesis_id = models.PositiveIntegerField()
    registered_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)

    # Ai duyệt / từ chối, lúc nào, vì sao (id tài khoản bên Identity Service)
    processed_by = models.PositiveIntegerField(null=True, blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    reject_reason = models.CharField(max_length=255, blank=True)
    # Ai hủy, lúc nào
    cancelled_by = models.PositiveIntegerField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "dangky"
        ordering = ["id"]
        constraints = [
            # Một sinh viên không được đăng ký cùng một đề tài nhiều lần
            # (đăng ký lại sau khi hủy / bị từ chối sẽ dùng lại chính dòng này)
            models.UniqueConstraint(
                fields=["student_id", "thesis_id"], name="unique_student_thesis"
            )
        ]

    @property
    def is_active(self):
        return self.status in self.ACTIVE_STATUSES

    def __str__(self):
        return f"Student {self.student_id} -> Thesis {self.thesis_id} [{self.status}]"


class RegistrationLock(models.Model):
    """
    Bảng KHOA_DANGKY - dòng khóa để chống vượt chỉ tiêu khi nhiều request đến cùng lúc.

    Mỗi đề tài ("thesis:<id>") và mỗi sinh viên ("student:<id>") có một dòng.
    Trước khi đếm và lưu đăng ký, request phải khóa (SELECT ... FOR UPDATE) các
    dòng liên quan; request thứ hai phải chờ request thứ nhất commit xong mới đếm.
    Trên SQL Server, mssql-django dịch select_for_update() thành WITH (UPDLOCK, ROWLOCK).

    Hai bước tách riêng để tránh deadlock trên SQL Server:
      1. ensure()  - tạo sẵn dòng khóa, mỗi dòng tự commit ngay (gọi NGOÀI transaction)
      2. acquire() - trong transaction, khóa từng dòng theo khóa chính (id) và theo thứ tự cố định
    Nếu tạo dòng khóa ngay trong transaction, các request song song giữ khóa trên dòng mới
    chưa commit của nhau và SQL Server phải hủy bớt request (lỗi deadlock 1205 -> HTTP 500).
    """

    key = models.CharField(max_length=50, unique=True)

    class Meta:
        db_table = "khoa_dangky"

    @classmethod
    def ensure(cls, *keys):
        """Tạo các dòng khóa còn thiếu. Gọi TRƯỚC transaction.atomic() để mỗi dòng được commit ngay."""
        existing = set(cls.objects.filter(key__in=keys).values_list("key", flat=True))
        for key in set(keys) - existing:
            try:
                with transaction.atomic():
                    cls.objects.create(key=key)
            except IntegrityError:
                pass  # request khác vừa tạo dòng này - không sao

    @classmethod
    def acquire(cls, *keys):
        """Khóa các key theo thứ tự cố định. Phải gọi trong transaction.atomic(), sau ensure()."""
        keys = sorted(set(keys))
        ids = dict(cls.objects.filter(key__in=keys).values_list("key", "id"))
        missing = [key for key in keys if key not in ids]
        for key in missing:  # phòng trường hợp quên gọi ensure()
            ids[key] = cls.objects.get_or_create(key=key)[0].id
        # Khóa theo khóa chính -> SQL Server tìm thẳng đúng dòng (seek), không quét qua dòng của request khác
        return [cls.objects.select_for_update().get(pk=ids[key]) for key in keys]


class ProgressNote(models.Model):
    """Bảng TIENDO - nhận xét / tiến độ hướng dẫn của giảng viên cho một đăng ký đã duyệt."""

    registration = models.ForeignKey(Registration, on_delete=models.CASCADE, related_name="notes")
    author_id = models.PositiveIntegerField()
    author_name = models.CharField(max_length=100, blank=True)
    author_role = models.CharField(max_length=10)
    content = models.TextField()
    progress = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Phần trăm hoàn thành (0-100)",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "tiendo"
        ordering = ["-created_at", "-id"]
