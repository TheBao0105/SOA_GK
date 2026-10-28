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
    full_name = forms.CharField(label="Họ tên", max_length=100)
    email = forms.EmailField(label="Email")
    class_name = forms.CharField(label="Lớp", max_length=50, required=False)
    major = forms.CharField(label="Ngành", max_length=100, required=False)


class ThesisForm(BootstrapForm):
    title = forms.CharField(label="Tên đề tài", max_length=255)
    description = forms.CharField(
        label="Mô tả", required=False, widget=forms.Textarea(attrs={"rows": 3})
    )
    max_students = forms.IntegerField(label="Số sinh viên tối đa", min_value=1, initial=1)
    status = forms.ChoiceField(
        label="Trạng thái", choices=[("OPEN", "Đang mở"), ("CLOSED", "Đã đóng")]
    )

    def __init__(self, *args, lecturers=None, **kwargs):
        """lecturers: danh sách tài khoản giảng viên (chỉ ADMIN mới được chọn GVHD)."""
        super().__init__(*args, **kwargs)
        self.lecturers = {u["id"]: u for u in (lecturers or [])}
        self.can_select_supervisor = lecturers is not None
        if lecturers is not None:
            self.fields["supervisor_id"] = forms.TypedChoiceField(
                label="Giảng viên hướng dẫn",
                coerce=int,
                required=False,
                empty_value=None,
                choices=[("", "-- Chưa phân công --")]
                + [(u["id"], f"{u['full_name'] or u['username']} ({u['username']})") for u in lecturers],
                widget=forms.Select(attrs={"class": "form-select"}),
            )

    def clean(self):
        data = super().clean()
        lecturer = self.lecturers.get(data.get("supervisor_id"))
        if self.can_select_supervisor:
            data["supervisor"] = (lecturer["full_name"] or lecturer["username"]) if lecturer else ""
        return data


class RegistrationForm(BootstrapForm):
    student_id = forms.TypedChoiceField(label="Sinh viên", coerce=int)
    thesis_id = forms.TypedChoiceField(label="Đề tài", coerce=int)

    def __init__(self, *args, students=(), theses=(), fixed_student_id=None, **kwargs):
        """fixed_student_id: sinh viên tự đăng ký -> không được chọn sinh viên khác."""
        super().__init__(*args, **kwargs)
        self.fixed_student_id = fixed_student_id
        if fixed_student_id is not None:
            del self.fields["student_id"]
        else:
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

    def clean(self):
        data = super().clean()
        if self.fixed_student_id is not None:
            data["student_id"] = self.fixed_student_id
        return data


class RejectForm(BootstrapForm):
    reject_reason = forms.CharField(label="Lý do từ chối", max_length=255)


class ProgressNoteForm(BootstrapForm):
    content = forms.CharField(label="Nhận xét / tiến độ", widget=forms.Textarea(attrs={"rows": 3}))
    progress = forms.IntegerField(label="Hoàn thành (%)", min_value=0, max_value=100, required=False)


ROLE_CHOICES = [("STUDENT", "Sinh viên"), ("LECTURER", "Giảng viên"), ("ADMIN", "Quản trị")]


class AccountForm(BootstrapForm):
    """Admin tạo tài khoản ở Identity Service."""

    username = forms.CharField(label="Tên đăng nhập", max_length=150)
    email = forms.EmailField(label="Email")
    full_name = forms.CharField(label="Họ tên", max_length=100, required=False)
    role = forms.ChoiceField(label="Vai trò", choices=ROLE_CHOICES)
    student_id = forms.TypedChoiceField(
        label="Gắn với sinh viên (chỉ cho vai trò Sinh viên)", coerce=int, required=False, empty_value=None
    )
    password = forms.CharField(
        label="Mật khẩu ban đầu", strip=False, widget=forms.PasswordInput,
        help_text="Ít nhất 8 ký tự, không quá giống tên đăng nhập, không phải toàn số.",
    )

    def __init__(self, *args, students=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["student_id"].choices = [("", "-- Không --")] + [
            (s["id"], f"{s['student_code']} - {s['full_name']}") for s in students
        ]

    def clean(self):
        data = super().clean()
        if data.get("role") == "STUDENT" and not data.get("student_id"):
            self.add_error("student_id", "Tài khoản sinh viên cần gắn với một sinh viên.")
        if data.get("role") != "STUDENT":
            data["student_id"] = None
        return data


class LoginForm(BootstrapForm):
    username = forms.CharField(label="Tên đăng nhập hoặc email", max_length=150)
    password = forms.CharField(label="Mật khẩu", strip=False, widget=forms.PasswordInput)


class ChangePasswordForm(BootstrapForm):
    old_password = forms.CharField(label="Mật khẩu hiện tại", strip=False, widget=forms.PasswordInput)
    new_password = forms.CharField(
        label="Mật khẩu mới", strip=False, widget=forms.PasswordInput,
        help_text="Ít nhất 8 ký tự, không quá giống tên đăng nhập, không phải toàn số.",
    )
    confirm_password = forms.CharField(label="Nhập lại mật khẩu mới", strip=False, widget=forms.PasswordInput)

    def clean(self):
        data = super().clean()
        if data.get("new_password") and data.get("new_password") != data.get("confirm_password"):
            self.add_error("confirm_password", "Mật khẩu nhập lại không khớp.")
        return data


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
    "Identity Service không hoạt động": "Identity Service không hoạt động, chưa thể đăng nhập.",
    "Old password is incorrect.": "Mật khẩu hiện tại không đúng.",
    "New password must be different from the old password.": "Mật khẩu mới phải khác mật khẩu cũ.",
    "This password is too short. It must contain at least 8 characters.": "Mật khẩu quá ngắn (tối thiểu 8 ký tự).",
    "This password is too common.": "Mật khẩu quá phổ biến, dễ đoán.",
    "This password is entirely numeric.": "Mật khẩu không được chỉ gồm chữ số.",
    "Student Service rejected the credentials": "Student Service từ chối phiên đăng nhập, hãy đăng nhập lại.",
    "Thesis Service rejected the credentials": "Thesis Service từ chối phiên đăng nhập, hãy đăng nhập lại.",
    "Students can only register for themselves": "Sinh viên chỉ được đăng ký cho chính mình.",
    "Your account is not linked to a student record": "Tài khoản chưa được gắn với hồ sơ sinh viên, liên hệ quản trị viên.",
    "Only pending registrations can be cancelled": "Chỉ hủy được đăng ký đang chờ duyệt.",
    "This student is already linked to another account.": "Sinh viên này đã có tài khoản khác.",
    "Only STUDENT accounts can have student_id.": "Chỉ tài khoản sinh viên mới gắn với sinh viên.",
    "user with this username already exists.": "Tên đăng nhập đã tồn tại.",
    "user with this email already exists.": "Email đã được dùng cho tài khoản khác.",
    "The password is too similar to the username.": "Mật khẩu quá giống tên đăng nhập.",
    "Registration Service không hoạt động": "Registration Service không hoạt động.",
    "Registration Service unavailable": "Registration Service không hoạt động, chưa thể kiểm tra đăng ký liên quan.",
    # Giai đoạn 3: quy trình đăng ký
    "Student already has an active registration": "Sinh viên đã có đăng ký đang chờ duyệt hoặc đã được duyệt.",
    "Registration is already cancelled": "Đăng ký này đã được hủy trước đó.",
    "Only pending or approved registrations can be cancelled": "Chỉ hủy được đăng ký đang chờ duyệt hoặc đã duyệt.",
    "Cancelled registrations cannot be changed": "Đăng ký đã hủy thì không thể thay đổi.",
    "A reason is required when rejecting.": "Cần nhập lý do khi từ chối.",
    "Progress notes can only be added to approved registrations": "Chỉ ghi tiến độ cho đăng ký đã được duyệt.",
    "Student has active registrations": "Sinh viên đang có đăng ký còn hiệu lực, hãy hủy đăng ký trước khi xóa.",
    "Thesis has active registrations": "Đề tài đang có đăng ký còn hiệu lực, hãy hủy đăng ký trước khi xóa.",
}

# Lỗi đăng nhập theo mã "code" do Identity Service trả về
LOGIN_ERRORS = {
    "invalid_credentials": "Sai tên đăng nhập hoặc mật khẩu.",
    "account_locked": "Tài khoản tạm bị khóa do đăng nhập sai nhiều lần. Vui lòng thử lại sau.",
    "account_disabled": "Tài khoản đã bị vô hiệu hóa. Liên hệ quản trị viên.",
    "throttled": "Bạn thử đăng nhập quá nhiều lần, vui lòng đợi một lát.",
}


def translate_error(message):
    if message.startswith("Cannot be lower than the number of active registrations"):
        count = message.rsplit("(", 1)[-1].rstrip(").")
        return f"Không được thấp hơn số đăng ký còn hiệu lực ({count})."
    return ERROR_MESSAGES.get(message, message)


def api_error_message(data):
    """Lấy thông báo lỗi đầu tiên trong JSON lỗi của API ({"error": ".."} hoặc {"field": [".."]})."""
    if not isinstance(data, dict):
        return translate_error(str(data))
    if "error" in data:
        return translate_error(str(data["error"]))
    for key, value in data.items():
        if key != "code" and value:
            return translate_error(str(value[0] if isinstance(value, list) else value))
    return "Yêu cầu không hợp lệ."
