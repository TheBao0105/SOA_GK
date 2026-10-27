"""
Lớp giao tiếp với các service khác qua HTTP/REST.

Registration Service KHÔNG truy cập student_db / thesis_db.
Muốn biết thông tin sinh viên / đề tài thì phải gọi REST API:

    GET {STUDENT_SERVICE_URL}/api/students/{id}/
    GET {THESIS_SERVICE_URL}/api/theses/{id}/

Chỉ cần các service kia giữ nguyên API (URL + JSON trả về) thì file này
không phải sửa, dù bên trong chúng thay đổi cách cài đặt như thế nào.

Xác thực: mỗi lời gọi gửi kèm header  Authorization: Bearer <token>
- Khi xử lý request của người dùng: chuyển tiếp chính access token của người đó.
- Khi không có người dùng (lệnh seed_data): dùng SERVICE_TOKEN trong .env.
"""
import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class ServiceUnavailableError(Exception):
    """Service bên ngoài không phản hồi (tắt, timeout, lỗi 5xx...)."""

    def __init__(self, service_name, message=None):
        self.service_name = service_name
        super().__init__(message or f"{service_name} unavailable")


class ServiceContractError(ServiceUnavailableError):
    """HTTP succeeds but the returned JSON violates the fields this caller needs."""

    def __init__(self, service_name):
        super().__init__(service_name, f"{service_name} returned an invalid API response")


def _invalid(service_name):
    # Do not log response bodies: they may include personal data.
    logger.warning("%s returned JSON that violates the API contract", service_name)
    raise ServiceContractError(service_name)


def _positive_id(value):
    return type(value) is int and value > 0


def _record(data, service_name, expected_id=None, code_field=None):
    if not isinstance(data, dict) or not _positive_id(data.get("id")):
        _invalid(service_name)
    if expected_id is not None and data["id"] != expected_id:
        _invalid(service_name)
    if code_field and (not isinstance(data.get(code_field), str) or not data[code_field].strip()):
        _invalid(service_name)
    return data


def _records(data, service_name, code_field=None):
    if not isinstance(data, list):
        _invalid(service_name)
    return [_record(item, service_name, code_field=code_field) for item in data]


class ServiceAuthError(Exception):
    """Service bên ngoài từ chối token (401/403): token hết hạn, sai, hoặc thiếu SERVICE_TOKEN."""

    def __init__(self, service_name, status_code):
        self.service_name = service_name
        self.status_code = status_code
        super().__init__(f"{service_name} rejected the credentials")


def _auth_headers(token):
    token = token or settings.SERVICE_TOKEN
    return {"Authorization": f"Bearer {token}"} if token else {}


def _get_json(service_name, url, token=None):
    """
    Gọi GET tới một service khác.

    - 200 -> trả về dict JSON
    - 404 -> trả về None (không tồn tại)
    - 401/403 -> ServiceAuthError (token không được chấp nhận)
    - không kết nối được / timeout / lỗi khác -> ServiceUnavailableError
    """
    logger.info("Calling %s: GET %s", service_name, url)  # không ghi token vào log
    try:
        response = requests.get(url, headers=_auth_headers(token), timeout=settings.EXTERNAL_API_TIMEOUT)
    except requests.RequestException as exc:  # ConnectionError, Timeout, ...
        logger.warning("%s error: %s", service_name, exc)
        raise ServiceUnavailableError(service_name) from exc

    if response.status_code == 404:
        return None
    if response.status_code in (401, 403):
        logger.warning("%s rejected credentials (HTTP %s)", service_name, response.status_code)
        raise ServiceAuthError(service_name, response.status_code)
    if response.status_code != 200:
        raise ServiceUnavailableError(service_name)
    try:
        data = response.json()
    except ValueError as exc:  # trả 200 nhưng không phải JSON
        raise ServiceUnavailableError(service_name) from exc
    if not isinstance(data, (dict, list)):
        _invalid(service_name)
    return data


def get_student(student_id, token=None):
    """Lấy sinh viên từ Student Service. Trả None nếu không tồn tại."""
    url = f"{settings.STUDENT_SERVICE_URL}/api/students/{student_id}/"
    data = _get_json("Student Service", url, token)
    return None if data is None else _record(data, "Student Service", expected_id=student_id)


def get_thesis(thesis_id, token=None):
    """Lấy đề tài từ Thesis Service. Trả None nếu không tồn tại."""
    url = f"{settings.THESIS_SERVICE_URL}/api/theses/{thesis_id}/"
    data = _get_json("Thesis Service", url, token)
    if data is None:
        return None
    _record(data, "Thesis Service", expected_id=thesis_id)
    if data.get("status") not in ("OPEN", "CLOSED") or not _positive_id(data.get("max_students")):
        _invalid("Thesis Service")
    return data


def list_supervised_thesis_ids(lecturer_id, token=None):
    """Id các đề tài do giảng viên hướng dẫn (hỏi Thesis Service: ?supervisor_id=)."""
    url = f"{settings.THESIS_SERVICE_URL}/api/theses/?supervisor_id={int(lecturer_id)}"
    return [t["id"] for t in _records(_get_json("Thesis Service", url, token), "Thesis Service")]


def find_student_by_code(student_code, token=None):
    """Tìm sinh viên theo mã (dùng cho seed_data). Trả None nếu không có."""
    url = f"{settings.STUDENT_SERVICE_URL}/api/students/?search={student_code}"
    students = _records(_get_json("Student Service", url, token), "Student Service", "student_code")
    return next((s for s in students if s["student_code"] == student_code), None)


def find_thesis_by_code(thesis_code, token=None):
    """Tìm đề tài theo mã (dùng cho seed_data). Trả None nếu không có."""
    url = f"{settings.THESIS_SERVICE_URL}/api/theses/?search={thesis_code}"
    theses = _records(_get_json("Thesis Service", url, token), "Thesis Service", "thesis_code")
    return next((t for t in theses if t["thesis_code"] == thesis_code), None)


def validate_account(data, account_id):
    _record(data, "Identity Service", expected_id=account_id)
    if data.get("role") not in ("ADMIN", "LECTURER", "STUDENT") or type(data.get("is_active")) is not bool:
        _invalid("Identity Service")
    return data
