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
import logging
from urllib.parse import urlencode

from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse

logger = logging.getLogger(__name__)

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


def has_valid_session(session):
    """Validate Portal session shape; API services still verify the actual JWT."""
    access = session.get(SESSION_ACCESS)
    user = session.get(SESSION_USER)
    return (
        isinstance(access, str) and bool(access.strip())
        and isinstance(user, dict)
        and type(user.get("id")) is int and user["id"] > 0
        and isinstance(user.get("username"), str) and bool(user["username"].strip())
        and user.get("role") in ("ADMIN", "LECTURER", "STUDENT")
    )


def current_user(request):
    user = request.session.get(SESSION_USER)
    return user if isinstance(user, dict) else None


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
            if not has_valid_session(request.session):
                request.session.flush()
                return redirect(login_url(request.get_full_path() if request.method == "GET" else None))
            if current_role(request) not in roles:
                return permission_denied_response(request)
            return view(request, *args, **kwargs)

        return wrapper

    return decorator


def login_url(next_path=None):
    url = reverse("login")
    return f"{url}?{urlencode({'next': next_path})}" if next_path else url


def permission_denied_response(request, service_name=None):
    # A permission denial does not invalidate an authenticated session.
    logger.warning("Access denied by %s at %s; Portal session preserved",
                   service_name or "Portal role check", request.path)
    message = f"{service_name}: Bạn không có quyền truy cập chức năng này." if service_name else "Bạn không có quyền truy cập chức năng này."
    if request.path == reverse("dashboard"):
        return render(request, "portal/forbidden.html", {"denial_message": message}, status=403)
    messages.error(request, message)
    return redirect("dashboard")


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
            valid = has_valid_session(request.session)
            auth_keys = (SESSION_ACCESS, SESSION_REFRESH, SESSION_USER, "_auth_user_id")
            if not valid and any(key in request.session for key in auth_keys):
                # Recover cookies from the old login implementation or an incomplete session.
                # Apply this on login URLs too, so their GET handler cannot bounce back to /.
                request.session.flush()
                messages.warning(request, "Phiên đăng nhập cũ không còn hợp lệ, vui lòng đăng nhập lại.")
            if not self.is_public(request.path) and not valid:
                return redirect(login_url(request.get_full_path() if request.method == "GET" else None))
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
            return permission_denied_response(request, service_name=exception.service_name)
        return None
