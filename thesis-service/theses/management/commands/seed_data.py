from django.core.management.base import BaseCommand

from theses.models import Thesis

SAMPLE_THESES = [
    {
        "thesis_code": "DT001",
        "title": "Hệ thống quản lý thư viện",
        "description": "Xây dựng ứng dụng web quản lý sách, độc giả và mượn trả.",
        "supervisor": "TS. Phạm Minh Tuấn",
        "max_students": 3,
        "status": Thesis.Status.OPEN,
    },
    {
        "thesis_code": "DT002",
        "title": "Hệ thống đặt sân thể thao",
        "description": "Ứng dụng web cho phép đặt sân bóng, cầu lông trực tuyến.",
        "supervisor": "ThS. Hoàng Thu Hà",
        "max_students": 1,
        "status": Thesis.Status.OPEN,
    },
    {
        "thesis_code": "DT003",
        "title": "Hệ thống quản lý đồ án tốt nghiệp",
        "description": "Hệ thống theo kiến trúc SOA quản lý đăng ký đề tài.",
        "supervisor": "TS. Phạm Minh Tuấn",
        "max_students": 3,
        "status": Thesis.Status.CLOSED,
    },
]


# Giảng viên hướng dẫn -> id tài khoản bên Identity Service.
# Với auth_db tạo bằng "seed_users": admin=1, gv.tuan=2, gv.ha=3.
DEFAULT_SUPERVISOR_IDS = {"TS. Phạm Minh Tuấn": 2, "ThS. Hoàng Thu Hà": 3}


class Command(BaseCommand):
    help = "Tạo dữ liệu mẫu cho bảng DETAI (chạy nhiều lần không bị trùng)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--supervisor", action="append", default=[], metavar="TEN=ID",
            help='Gán GVHD, ví dụ: --supervisor "TS. Phạm Minh Tuấn=2" (id tài khoản ở Identity Service)',
        )

    def handle(self, *args, **options):
        supervisor_ids = dict(DEFAULT_SUPERVISOR_IDS)
        for item in options["supervisor"]:
            name, _, user_id = item.rpartition("=")
            supervisor_ids[name.strip()] = int(user_id)

        for data in SAMPLE_THESES:
            data = {**data, "supervisor_id": supervisor_ids.get(data["supervisor"])}
            thesis, created = Thesis.objects.update_or_create(
                thesis_code=data["thesis_code"], defaults=data
            )
            action = "Created" if created else "Exists "
            self.stdout.write(
                f"{action} id={thesis.id}: {thesis} [{thesis.status}] supervisor_id={thesis.supervisor_id}"
            )
        self.stdout.write(self.style.SUCCESS("Seed theses done."))
