from django.core.management.base import BaseCommand

from students.models import Student

SAMPLE_STUDENTS = [
    {
        "student_code": "SV001",
        "full_name": "Nguyễn Văn An",
        "email": "an.nguyen@student.edu.vn",
        "class_name": "CNTT1",
        "major": "Công nghệ thông tin",
    },
    {
        "student_code": "SV002",
        "full_name": "Trần Văn Bình",
        "email": "binh.tran@student.edu.vn",
        "class_name": "CNTT1",
        "major": "Công nghệ thông tin",
    },
    {
        "student_code": "SV003",
        "full_name": "Lê Văn Cường",
        "email": "cuong.le@student.edu.vn",
        "class_name": "KTPM2",
        "major": "Kỹ thuật phần mềm",
    },
]


class Command(BaseCommand):
    help = "Tạo dữ liệu mẫu cho bảng SINHVIEN (chạy nhiều lần không bị trùng)"

    def handle(self, *args, **options):
        for data in SAMPLE_STUDENTS:
            student, created = Student.objects.update_or_create(
                student_code=data["student_code"], defaults=data
            )
            action = "Created" if created else "Exists "
            self.stdout.write(f"{action} id={student.id}: {student}")
        self.stdout.write(self.style.SUCCESS("Seed students done."))
