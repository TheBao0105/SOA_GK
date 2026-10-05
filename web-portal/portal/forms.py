from django import forms


class BootstrapForm(forms.Form):
    """Tự gắn class Bootstrap cho mọi ô nhập."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            css = "form-select" if isinstance(field.widget, forms.Select) else "form-control"
            field.widget.attrs["class"] = css

    def add_api_errors(self, data):
        """Hiển thị lỗi do API trả về ({"field": ["..."]} hoặc {"error": "..."})."""
        for key, value in data.items():
            messages = value if isinstance(value, list) else [value]
            field = key if key in self.fields else None
            for message in messages:
                self.add_error(field, translate_error(str(message)))


class StudentForm(BootstrapForm):
    student_code = forms.CharField(label="Mã sinh viên", max_length=20)
    full_name = forms.CharField(label="Họ tên", max_length=100)
    email = forms.EmailField(label="Email")
    class_name = forms.CharField(label="Lớp", max_length=50, required=False)
    major = forms.CharField(label="Ngành", max_length=100, required=False)


class ThesisForm(BootstrapForm):
    thesis_code = forms.CharField(label="Mã đề tài", max_length=20)
    title = forms.CharField(label="Tên đề tài", max_length=255)
    description = forms.CharField(
        label="Mô tả", required=False, widget=forms.Textarea(attrs={"rows": 3})
    )
    supervisor = forms.CharField(label="Giảng viên hướng dẫn", max_length=100, required=False)
    max_students = forms.IntegerField(label="Số sinh viên tối đa", min_value=1, initial=1)
    status = forms.ChoiceField(
        label="Trạng thái", choices=[("OPEN", "Đang mở"), ("CLOSED", "Đã đóng")]
    )


class RegistrationForm(BootstrapForm):
    student_id = forms.TypedChoiceField(label="Sinh viên", coerce=int)
    thesis_id = forms.TypedChoiceField(label="Đề tài", coerce=int)

    def __init__(self, *args, students=(), theses=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["student_id"].choices = [("", "-- Chọn sinh viên --")] + [
            (s["id"], f"{s['student_code']} - {s['full_name']}") for s in students
        ]
        self.fields["thesis_id"].choices = [("", "-- Chọn đề tài --")] + [
            (
                t["id"],
                f"{t['thesis_code']} - {t['title']}"
                + (" (đã đóng)" if t["status"] == "CLOSED" else ""),
            )
            for t in theses
        ]


# Dịch các thông báo lỗi tiếng Anh của API sang tiếng Việt để hiển thị
ERROR_MESSAGES = {
    "Student does not exist": "Sinh viên không tồn tại.",
    "Thesis does not exist": "Đề tài không tồn tại.",
    "Thesis is closed": "Đề tài đã đóng, không thể đăng ký.",
    "Thesis has reached maximum students": "Đề tài đã đủ số sinh viên tối đa.",
    "Student has already registered for this thesis": "Sinh viên đã đăng ký đề tài này rồi.",
    "Student Service unavailable": "Student Service không hoạt động.",
    "Thesis Service unavailable": "Thesis Service không hoạt động.",
    "student with this student code already exists.": "Mã sinh viên đã tồn tại.",
    "student with this email already exists.": "Email đã được sử dụng.",
    "thesis with this thesis code already exists.": "Mã đề tài đã tồn tại.",
    "Enter a valid email address.": "Email không hợp lệ.",
}


def translate_error(message):
    return ERROR_MESSAGES.get(message, message)
