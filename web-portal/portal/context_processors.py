from django.conf import settings

ROLE_LABELS = {"ADMIN": "Quản trị", "LECTURER": "Giảng viên", "STUDENT": "Sinh viên"}


def service_urls(request):
    """Cho template biết địa chỉ các service (dùng ở menu API Docs)."""
    return {
        "STUDENT_SERVICE_URL": settings.STUDENT_SERVICE_URL,
        "THESIS_SERVICE_URL": settings.THESIS_SERVICE_URL,
        "REGISTRATION_SERVICE_URL": settings.REGISTRATION_SERVICE_URL,
        "IDENTITY_SERVICE_URL": settings.IDENTITY_SERVICE_URL,
    }


def current_user(request):
    """Thông tin người đang đăng nhập (lấy từ session) cho template."""
    session = getattr(request, "session", None)
    user = session.get("user") if session is not None else None
    if user:
        user = {
            **user,
            "role_label": ROLE_LABELS.get(user["role"], user["role"]),
            "is_admin": user["role"] == "ADMIN",
            "is_lecturer": user["role"] == "LECTURER",
            "is_student": user["role"] == "STUDENT",
        }
    return {"current_user": user}
