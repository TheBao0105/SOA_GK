"""
Đăng nhập ở Web Portal.

Portal không có database: sau khi đăng nhập tại Identity Service, cặp token
(access + refresh) được lưu trong session dạng cookie đã ký, HttpOnly
(JavaScript trên trình duyệt không đọc được).

- LoginRequiredMiddleware: chưa đăng nhập thì chuyển về /dang-nhap/.
- api_client đọc access token của request hiện tại qua get_session()
  và tự làm mới token khi service trả 401.
"""
import contextvars
import functools
from urllib.parse import urlencode

from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse

_current_session = contextvars.ContextVar("portal_session", default=None)

SESSION_ACCESS = "access_token"
SESSION_REFRESH = "refresh_token"
SESSION_USER = "user"

# Các trang không cần đăng nhập
PUBLIC_URL_NAMES = ("login", "accounts:login")


class AuthExpired(Exception):
    """Phiên đăng nhập hết hạn và không làm mới được -> phải đăng nhập lại."""


def get_session():
    return _current_session.get()


def save_tokens(session, data):
    session[SESSION_ACCESS] = data["access"]
    session[SESSION_REFRESH] = data["refresh"]


def login_session(request, data):
    """Lưu kết quả đăng nhập vào session (chỉ thông tin cần hiển thị, không lưu mật khẩu)."""
    request.session.cycle_key()  # chống session fixation
    save_tokens(request.session, data)
    user = data["user"]
    request.session[SESSION_USER] = {
        "id": user["id"],
        "username": user["username"],
        "full_name": user.get("full_name") or user["username"],
        "role": user["role"],
        "student_id": user.get("student_id"),
    }


def current_user(request):
    return request.session.get(SESSION_USER)


def current_role(request):
    return (current_user(request) or {}).get("role")


def role_required(*roles):
    """
    Ẩn các trang không thuộc vai trò hiện tại.

    Đây chỉ là lớp giao diện cho thân thiện: quyền thật sự do backend
    (các service) kiểm tra; gọi API vượt quyền vẫn bị trả 403.
    """

    def decorator(view):
        @functools.wraps(view)
        def wrapper(request, *args, **kwargs):
            if current_role(request) not in roles:
                messages.error(request, "Bạn không có quyền truy cập chức năng này.")
                return redirect("dashboard")
            return view(request, *args, **kwargs)

        return wrapper

    return decorator


def login_url(next_path=None):
    url = reverse("login")
    return f"{url}?{urlencode({'next': next_path})}" if next_path else url


class LoginRequiredMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self._public_paths = None

    def is_public(self, path):
        if self._public_paths is None:
            self._public_paths = {reverse(name) for name in PUBLIC_URL_NAMES}
        return path in self._public_paths

    def __call__(self, request):
        token = _current_session.set(request.session)
        try:
            if not self.is_public(request.path) and not request.session.get(SESSION_ACCESS):
                return redirect(login_url(request.get_full_path()))
            return self.get_response(request)
        finally:
            _current_session.reset(token)

    def process_exception(self, request, exception):
        from .api_client import Forbidden  # tránh import vòng

        if isinstance(exception, AuthExpired):
            request.session.flush()
            messages.warning(request, "Phiên đăng nhập đã hết hạn, vui lòng đăng nhập lại.")
            next_path = request.get_full_path() if request.method == "GET" else None
            return redirect(login_url(next_path))
        if isinstance(exception, Forbidden):
            # Backend từ chối (403): báo cho người dùng thay vì trang lỗi
            messages.error(request, "Bạn không có quyền thực hiện thao tác này.")
            return redirect("dashboard")
        return None
