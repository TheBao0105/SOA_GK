from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = (
        "Tạo cặp khóa RSA để ký JWT. Khóa BÍ MẬT chỉ Identity Service giữ; "
        "khóa CÔNG KHAI được Student/Thesis/Registration Service đọc để xác minh token."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--force", action="store_true",
            help="Ghi đè khóa cũ (mọi token đã cấp sẽ mất hiệu lực, phải khởi động lại các service)",
        )

    def handle(self, *args, **options):
        private_path = Path(settings.JWT_PRIVATE_KEY_PATH)
        public_path = Path(settings.JWT_PUBLIC_KEY_PATH)

        if private_path.exists() and not options["force"]:
            raise CommandError(
                f"Đã có khóa tại {private_path}. Dùng --force nếu thật sự muốn tạo khóa mới."
            )

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        private_pem = key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        public_pem = key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )

        private_path.parent.mkdir(parents=True, exist_ok=True)
        public_path.parent.mkdir(parents=True, exist_ok=True)
        private_path.write_bytes(private_pem)
        public_path.write_bytes(public_pem)

        self.stdout.write(self.style.SUCCESS(f"Khóa bí mật : {private_path}  (KHÔNG chia sẻ, KHÔNG commit)"))
        self.stdout.write(self.style.SUCCESS(f"Khóa công khai: {public_path}"))
        if options["force"]:
            self.stdout.write(self.style.WARNING("Hãy khởi động lại tất cả service để dùng khóa mới."))
