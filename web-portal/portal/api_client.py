"""
Client gọi REST API của các service.

Web Portal chỉ là một "người dùng" của các service: nó không biết gì về
database, chỉ biết URL + JSON. Đây chính là tính tái sử dụng của SOA:
cùng một API mà Registration Service đang dùng, Web Portal cũng dùng được.

Mỗi request gửi kèm access token của người đang đăng nhập
(Authorization: Bearer ...). Khi service trả 401 (token hết hạn),
client tự xin token mới ở Identity Service bằng refresh token rồi gửi lại 1 lần.
"""
import requests
from django.conf import settings

from .auth import AuthExpired, SESSION_ACCESS, SESSION_REFRESH, get_session, save_tokens


class ServiceUnavailable(Exception):
    """Service không phản hồi (đang tắt, timeout...)."""


class NotFound(Exception):
    """API trả về 404."""


class Forbidden(Exception):
    """API trả về 403: đã đăng nhập nhưng không có quyền."""

    def __init__(self, message="Bạn không có quyền thực hiện thao tác này.", service_name=None):
        self.service_name = service_name
        super().__init__(message)


class ApiError(Exception):
    """API trả về 4xx - dữ liệu không hợp lệ. data là JSON lỗi của API."""

    def __init__(self, data, status_code=400):
        self.data = data if isinstance(data, dict) else {"error": str(data)}
        self.status_code = status_code
        super().__init__(str(self.data))

    @property
    def code(self):
        return self.data.get("code")


def _json(response):
    try:
        return response.json() if response.content else None
    except ValueError:
        return None


def _json_dict(response):
    data = _json(response)
    return data if isinstance(data, dict) else {}


def _valid_token_pair(data):
    return isinstance(data, dict) and all(isinstance(data.get(key), str) and data[key] for key in ("access", "refresh"))


def _refresh_tokens(session):
    """Xin cặp token mới bằng refresh token. Trả True nếu thành công."""
    refresh = session.get(SESSION_REFRESH)
    if not refresh:
        return False
    try:
        response = requests.post(
            f"{settings.IDENTITY_SERVICE_URL}/api/auth/refresh/",
            json={"refresh": refresh},
            timeout=settings.EXTERNAL_API_TIMEOUT,
        )
    except requests.RequestException:
        raise ServiceUnavailable("Identity Service không hoạt động")
    if response.status_code in (400, 401, 403):
        return False
    if response.status_code != 200:
        raise ServiceUnavailable("Identity Service chưa thể làm mới phiên đăng nhập")
    data = _json(response)
    if not _valid_token_pair(data):
        raise ServiceUnavailable("Identity Service trả dữ liệu token không hợp lệ")
    save_tokens(session, data)
    return True


def call(service_name, method, url, *, auth=True, retry=True, **kwargs):
    session = get_session() if auth else None
    headers = dict(kwargs.pop("headers", {}) or {})
    if session is not None and session.get(SESSION_ACCESS):
        headers["Authorization"] = f"Bearer {session[SESSION_ACCESS]}"

    try:
        response = requests.request(
            method, url, headers=headers, timeout=settings.EXTERNAL_API_TIMEOUT, **kwargs
        )
    except requests.RequestException:
        raise ServiceUnavailable(f"{service_name} không hoạt động")

    if auth and response.status_code == 401:
        # Access token hết hạn -> làm mới rồi thử lại đúng 1 lần
        if retry and session is not None and _refresh_tokens(session):
            return call(service_name, method, url, auth=auth, retry=False, **kwargs)
        raise AuthExpired()
    if response.status_code == 404:
        raise NotFound()
    if auth and response.status_code == 403:
        raise Forbidden(_json_dict(response).get("detail", "Bạn không có quyền thực hiện thao tác này."), service_name=service_name)
    if response.status_code == 503:
        # Registration Service báo một service khác đang tắt
        raise ServiceUnavailable(_json_dict(response).get("error", f"{service_name} không hoạt động"))
    if response.status_code >= 500:
        raise ServiceUnavailable(f"{service_name} gặp lỗi")
    if response.status_code >= 400:
        raise ApiError(_json(response) or {"error": response.reason}, response.status_code)
    if response.status_code == 204:
        return None
    data = _json(response)
    if not isinstance(data, (dict, list)):
        raise ServiceUnavailable(f"{service_name} trả dữ liệu API không hợp lệ")
    return data


class Resource:
    """Một tài nguyên REST, ví dụ /api/students/ của Student Service."""

    def __init__(self, service_name, base_url, path):
        self.service_name = service_name
        self.url = f"{base_url}{path}"

    def _request(self, method, url, **kwargs):
        return call(self.service_name, method, url, **kwargs)

    def list(self, params=None):
        data = self._request("GET", self.url, params=params)
        if not isinstance(data, list) or any(not isinstance(item, dict) or type(item.get("id")) is not int or item["id"] <= 0 for item in data):
            raise ServiceUnavailable(f"{self.service_name} trả danh sách API không hợp lệ")
        return data

    def get(self, pk):
        data = self._request("GET", f"{self.url}{pk}/")
        if not isinstance(data, dict) or type(data.get("id")) is not int or str(data["id"]) != str(pk):
            raise ServiceUnavailable(f"{self.service_name} trả đối tượng API không hợp lệ")
        return data

    def create(self, data):
        return self._request("POST", self.url, json=data)

    def update(self, pk, data):
        return self._request("PATCH", f"{self.url}{pk}/", json=data)

    def delete(self, pk):
        return self._request("DELETE", f"{self.url}{pk}/")


students = Resource("Student Service", settings.STUDENT_SERVICE_URL, "/api/students/")
theses = Resource("Thesis Service", settings.THESIS_SERVICE_URL, "/api/theses/")
registrations = Resource(
    "Registration Service", settings.REGISTRATION_SERVICE_URL, "/api/registrations/"
)


def cancel_registration(pk):
    """POST /api/registrations/{id}/cancel/ - hủy đăng ký (giữ lại lịch sử, trạng thái CANCELLED)."""
    return call("Registration Service", "POST", f"{registrations.url}{pk}/cancel/")


def list_notes(pk):
    return call("Registration Service", "GET", f"{registrations.url}{pk}/notes/")


def add_note(pk, data):
    return call("Registration Service", "POST", f"{registrations.url}{pk}/notes/", json=data)


# ---------------------------------------------------------------- Dịch vụ Identity
IDENTITY = "Identity Service"


def login(username, password):
    """Trả {access, refresh, user, ...}; sai thông tin -> ApiError (code: invalid_credentials...)."""
    data = call(
        IDENTITY, "POST", f"{settings.IDENTITY_SERVICE_URL}/api/auth/login/",
        auth=False, json={"username": username, "password": password},
    )
    user = data.get("user") if isinstance(data, dict) else None
    if (not _valid_token_pair(data) or not isinstance(user, dict)
            or type(user.get("id")) is not int or user["id"] <= 0
            or not isinstance(user.get("username"), str) or not user["username"]
            or user.get("role") not in ("ADMIN", "LECTURER", "STUDENT")):
        raise ServiceUnavailable("Identity Service trả dữ liệu đăng nhập không hợp lệ")
    return data


def logout(refresh_token):
    return call(
        IDENTITY, "POST", f"{settings.IDENTITY_SERVICE_URL}/api/auth/logout/",
        retry=False, json={"refresh": refresh_token},
    )


def change_password(old_password, new_password):
    data = call(
        IDENTITY, "POST", f"{settings.IDENTITY_SERVICE_URL}/api/auth/change-password/",
        json={"old_password": old_password, "new_password": new_password},
    )
    if not _valid_token_pair(data):
        raise ServiceUnavailable("Identity Service trả dữ liệu token không hợp lệ")
    return data


users = Resource(IDENTITY, settings.IDENTITY_SERVICE_URL, "/api/users/")


def unlock_user(pk):
    return call(IDENTITY, "POST", f"{users.url}{pk}/unlock/")


def is_online(base_url):
    """Kiểm tra nhanh một service có đang chạy không (dùng ở trang API Docs)."""
    try:
        response = requests.get(f"{base_url}/api/schema/", timeout=2, allow_redirects=False)
        return response.status_code == 200
    except requests.RequestException:
        return False

# Chấm điểm thuộc Registration Service, giữ nguyên cổng và cấu hình SOA.
grades = Resource("Registration Service", settings.REGISTRATION_SERVICE_URL, "/api/grading/grades/")


def my_profile(data=None):
    return call(IDENTITY, "PATCH" if data is not None else "GET", f"{settings.IDENTITY_SERVICE_URL}/api/auth/me/", **({"json": data} if data is not None else {}))


def audit_logs():
    return call(IDENTITY, "GET", f"{settings.IDENTITY_SERVICE_URL}/api/audit-logs/")


def grade_history(pk):
    return call("Registration Service", "GET", f"{grades.url}{pk}/history/")
