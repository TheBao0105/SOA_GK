from django.core.management.base import BaseCommand, CommandError

from registrations.models import Registration
from registrations.services import external_api
from registrations.services.external_api import ServiceUnavailableError

# (mã sinh viên, mã đề tài, trạng thái)
SAMPLE_REGISTRATIONS = [
    ("SV001", "DT001", Registration.Status.APPROVED),
    ("SV002", "DT001", Registration.Status.PENDING),
    ("SV003", "DT002", Registration.Status.APPROVED),
]


class Command(BaseCommand):
    help = (
        "Tạo dữ liệu mẫu cho bảng DANGKY. "
        "Cần chạy Student Service (8001) và Thesis Service (8002) trước, "
        "vì id sinh viên / đề tài được lấy qua REST API."
    )

    def handle(self, *args, **options):
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
                    defaults={"status": reg_status},
                )
                action = "Created" if created else "Exists "
                self.stdout.write(
                    f"{action} id={registration.id}: {student_code} (id={student['id']}) "
                    f"-> {thesis_code} (id={thesis['id']}) [{registration.status}]"
                )
        except ServiceUnavailableError as exc:
            raise CommandError(f"{exc}. Hãy chạy Student Service và Thesis Service trước.")

        self.stdout.write(self.style.SUCCESS("Seed registrations done."))
