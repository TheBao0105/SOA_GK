from django.core.management.base import BaseCommand

from accounts.models import User

# Tài khoản mẫu cho demo. student_id khớp dữ liệu mẫu của Student Service
# (SV001 -> id 1, SV002 -> id 2, SV003 -> id 3). Đổi mật khẩu sau khi demo!
SAMPLE_USERS = [
    {"username": "admin", "email": "admin@qnu.edu.vn", "full_name": "Quản trị hệ thống",
     "role": User.Role.ADMIN, "student_id": None, "password": "Admin@2026"},
    {"username": "gv.tuan", "email": "tuan.pham@qnu.edu.vn", "full_name": "TS. Phạm Minh Tuấn",
     "role": User.Role.LECTURER, "student_id": None, "password": "GiangVien@2026"},
    {"username": "gv.ha", "email": "ha.hoang@qnu.edu.vn", "full_name": "ThS. Hoàng Thu Hà",
     "role": User.Role.LECTURER, "student_id": None, "password": "GiangVien@2026"},
    {"username": "sv001", "email": "an.nguyen@student.edu.vn", "full_name": "Nguyễn Văn An",
     "role": User.Role.STUDENT, "student_id": 1, "password": "SinhVien@2026"},
    {"username": "sv002", "email": "binh.tran@student.edu.vn", "full_name": "Trần Văn Bình",
     "role": User.Role.STUDENT, "student_id": 2, "password": "SinhVien@2026"},
    {"username": "sv003", "email": "cuong.le@student.edu.vn", "full_name": "Lê Văn Cường",
     "role": User.Role.STUDENT, "student_id": 3, "password": "SinhVien@2026"},
]


class Command(BaseCommand):
    help = "Tạo tài khoản mẫu (chạy nhiều lần không bị trùng, không đổi mật khẩu đã có)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset-passwords", action="store_true",
            help="Đặt lại mật khẩu mẫu cho các tài khoản đã tồn tại",
        )

    def handle(self, *args, **options):
        for data in SAMPLE_USERS:
            data = dict(data)
            password = data.pop("password")
            user, created = User.objects.get_or_create(username=data["username"], defaults=data)
            if created or options["reset_passwords"]:
                user.set_password(password)
                user.is_staff = user.role == User.Role.ADMIN  # cho phép vào /admin/ của identity-service
                user.save()
            action = "Created" if created else "Exists "
            self.stdout.write(f"{action} {user.username:<8} role={user.role:<8} student_id={user.student_id}")

        self.stdout.write(self.style.SUCCESS("Seed users done."))
        self.stdout.write(
            "Mật khẩu mẫu: admin=Admin@2026, giảng viên=GiangVien@2026, sinh viên=SinhVien@2026 "
            "(chỉ dùng để demo)."
        )
