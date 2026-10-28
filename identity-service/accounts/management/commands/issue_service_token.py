from datetime import timedelta

from django.core.management.base import BaseCommand

from accounts import tokens


class Command(BaseCommand):
    help = (
        "Cấp token kỹ thuật (role=SERVICE) cho một service gọi service khác khi không có "
        "người dùng đăng nhập, ví dụ lệnh seed_data của Registration Service."
    )

    def add_arguments(self, parser):
        parser.add_argument("service_name", help="Tên service, ví dụ: registration-service")
        parser.add_argument("--days", type=int, default=30, help="Số ngày hiệu lực (mặc định 30)")

    def handle(self, *args, **options):
        token = tokens.create_service_token(options["service_name"], timedelta(days=options["days"]))
        self.stdout.write(token)
        self.stderr.write(
            self.style.WARNING(
                f"Dán vào SERVICE_TOKEN trong .env của {options['service_name']}. "
                f"Token có hiệu lực {options['days']} ngày - giữ bí mật như mật khẩu."
            )
        )
