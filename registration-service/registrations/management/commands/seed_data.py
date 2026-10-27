from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from registrations.models import Registration, RegistrationPeriod
from registrations.services import external_api
from registrations.services.external_api import ServiceAuthError, ServiceUnavailableError

# (mã sinh viên, mã đề tài, trạng thái)
SAMPLE_REGISTRATIONS = [
    ("SV001", "DT001", Registration.Status.APPROVED),
    ("SV002", "DT001", Registration.Status.PENDING),
    ("SV003", "DT002", Registration.Status.APPROVED),
]


SERVICE_TOKEN_HELP = (
    "{reason}.\n"
    "Tạo token mới và ghi vào registration-service\\.env (PowerShell, tại thư mục SOA_GK):\n"
    "  cd identity-service\n"
    "  python manage.py issue_service_token registration-service 2>$null | "
    "ForEach-Object {{ \"SERVICE_TOKEN=$_\" }} | Add-Content ..\\registration-service\\.env\n"
    "  cd ..\\registration-service; python manage.py seed_data"
)


class Command(BaseCommand):
    help = (
        "Tạo dữ liệu mẫu cho bảng DANGKY. "
        "Cần chạy Student Service (8001) và Thesis Service (8002) trước, "
        "vì id sinh viên / đề tài được lấy qua REST API."
    )

    def handle(self, *args, **options):
        # Đợt đăng ký mẫu: mở từ hôm nay, kéo dài 60 ngày (chỉ tạo nếu chưa có đợt nào)
        period = RegistrationPeriod.objects.order_by("-start_at").first()
        if period is None:
            now = timezone.now()
            period = RegistrationPeriod.objects.create(
                name="Đợt 1 - HK1 2026-2027",
                start_at=now - timedelta(minutes=1),
                end_at=now + timedelta(days=60),
                max_active_per_student=1,
            )
            self.stdout.write(f"Created period id={period.id}: {period.name} (mở tới {period.end_at:%d/%m/%Y})")
        else:
            self.stdout.write(f"Exists  period id={period.id}: {period.name} [{'mở' if period.is_open() else 'đóng'}]")

        if not settings.SERVICE_TOKEN:
            raise CommandError(SERVICE_TOKEN_HELP.format(reason="Chưa có SERVICE_TOKEN trong registration-service/.env"))

        try:
            for student_code, thesis_code, reg_status in SAMPLE_REGISTRATIONS:
                # Không đọc student_db / thesis_db: hỏi các service qua HTTP
                student = external_api.find_student_by_code(student_code)
                thesis = external_api.find_thesis_by_code(thesis_code)
                if student is None or thesis is None:
                    self.stdout.write(
                        self.style.WARNING(
                            f"Skip {student_code} -> {thesis_code}: chưa có dữ liệu "
                            "(hãy chạy seed_data ở student-service và thesis-service)"
                        )
                    )
                    continue

                registration, created = Registration.objects.get_or_create(
                    student_id=student["id"],
                    thesis_id=thesis["id"],
                    defaults={"status": reg_status, "period": period},
                )
                action = "Created" if created else "Exists "
                self.stdout.write(
                    f"{action} id={registration.id}: {student_code} (id={student['id']}) "
                    f"-> {thesis_code} (id={thesis['id']}) [{registration.status}]"
                )
        except ServiceUnavailableError as exc:
            raise CommandError(f"{exc}. Hãy chạy Student Service và Thesis Service trước.")
        except ServiceAuthError as exc:
            raise CommandError(SERVICE_TOKEN_HELP.format(
                reason=f"{exc} (SERVICE_TOKEN hết hạn, sai, hoặc khóa JWT đã được tạo lại)"
            ))

        self.stdout.write(self.style.SUCCESS("Seed registrations done."))
