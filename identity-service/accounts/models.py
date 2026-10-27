from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class User(AbstractUser):
    """
    Bảng TAIKHOAN - chỉ thuộc về Identity Service (auth_db).

    - Mật khẩu: Django tự hash (PBKDF2), không bao giờ lưu dạng thô.
    - role: vai trò dùng để phân quyền ở mọi service (được đưa vào JWT).
    - student_id: id sinh viên bên Student Service (KHÔNG phải ForeignKey,
      vì bảng sinhvien nằm ở database khác).
    """

    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Quản trị"
        LECTURER = "LECTURER", "Giảng viên"
        STUDENT = "STUDENT", "Sinh viên"

    email = models.EmailField("email", unique=True)
    full_name = models.CharField(max_length=100, blank=True)
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.STUDENT)
    student_id = models.PositiveIntegerField(
        null=True, blank=True, help_text="id của sinh viên bên Student Service"
    )
    token_version = models.PositiveIntegerField(default=0)
    failed_login_count = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)

    REQUIRED_FIELDS = ["email"]

    class Meta:
        db_table = "taikhoan"
        ordering = ["id"]

    def save(self, *args, **kwargs):
        # Tài khoản tạo bằng createsuperuser luôn là ADMIN
        if self.is_superuser:
            self.role = self.Role.ADMIN
        super().save(*args, **kwargs)

    @property
    def is_locked(self):
        return self.locked_until is not None and self.locked_until > timezone.now()

    def __str__(self):
        return f"{self.username} ({self.role})"


class RefreshToken(models.Model):
    """
    Bảng TOKEN_LAMMOI: lưu mã định danh (jti) của refresh token đã cấp.

    Chỉ lưu jti, không lưu token. Nhờ bảng này mới thu hồi được token
    khi đăng xuất, đổi mật khẩu hoặc phát hiện token bị dùng lại.
    """

    jti = models.CharField(max_length=64, unique=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="refresh_tokens")
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "token_lammoi"
        ordering = ["id"]

    @property
    def is_active(self):
        return self.revoked_at is None and self.expires_at > timezone.now()


class AuditLog(models.Model):
    """Bảng NHATKY: ghi lại sự kiện đăng nhập / quản trị tài khoản (không ghi mật khẩu, token)."""

    class Action(models.TextChoices):
        LOGIN_SUCCESS = "LOGIN_SUCCESS", "Đăng nhập thành công"
        LOGIN_FAILED = "LOGIN_FAILED", "Đăng nhập sai"
        ACCOUNT_LOCKED = "ACCOUNT_LOCKED", "Tạm khóa do đăng nhập sai"
        LOGOUT = "LOGOUT", "Đăng xuất"
        PASSWORD_CHANGED = "PASSWORD_CHANGED", "Đổi mật khẩu"
        TOKEN_REUSE = "TOKEN_REUSE", "Refresh token bị dùng lại"
        USER_CREATED = "USER_CREATED", "Tạo tài khoản"
        USER_UPDATED = "USER_UPDATED", "Cập nhật tài khoản"
        USER_DELETED = "USER_DELETED", "Xóa tài khoản"
        USER_UNLOCKED = "USER_UNLOCKED", "Mở khóa tài khoản"

    created_at = models.DateTimeField(auto_now_add=True)
    action = models.CharField(max_length=20, choices=Action.choices)
    actor_id = models.PositiveIntegerField(null=True, blank=True)
    target_id = models.PositiveIntegerField(null=True, blank=True)
    username = models.CharField(max_length=150, blank=True)
    ip_address = models.CharField(max_length=45, blank=True)
    detail = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = "nhatky"
        ordering = ["-id"]


class RevokedAccessToken(models.Model):
    """Only token identifiers, never raw bearer tokens; supports immediate logout revocation."""
    jti = models.CharField(max_length=64, primary_key=True)
    expires_at = models.DateTimeField()

    class Meta:
        db_table = "token_truycap_thuhoi"
