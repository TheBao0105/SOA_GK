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


class Command(BaseCommand):
    help = "Tạo dữ liệu mẫu cho bảng DETAI (chạy nhiều lần không bị trùng)"

    def handle(self, *args, **options):
        for data in SAMPLE_THESES:
            thesis, created = Thesis.objects.update_or_create(
                thesis_code=data["thesis_code"], defaults=data
            )
            action = "Created" if created else "Exists "
            self.stdout.write(f"{action} id={thesis.id}: {thesis} [{thesis.status}]")
        self.stdout.write(self.style.SUCCESS("Seed theses done."))
