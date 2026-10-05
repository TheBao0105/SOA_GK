"""
Lớp giao tiếp với các service khác qua HTTP/REST.

Registration Service KHÔNG truy cập student_db / thesis_db.
Muốn biết thông tin sinh viên / đề tài thì phải gọi REST API:

    GET {STUDENT_SERVICE_URL}/api/students/{id}/
    GET {THESIS_SERVICE_URL}/api/theses/{id}/

Chỉ cần các service kia giữ nguyên API (URL + JSON trả về) thì file này
không phải sửa, dù bên trong chúng thay đổi cách cài đặt như thế nào.
"""
import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class ServiceUnavailableError(Exception):
    """Service bên ngoài không phản hồi (tắt, timeout, lỗi 5xx...)."""

    def __init__(self, service_name):
        self.service_name = service_name
        super().__init__(f"{service_name} unavailable")


def _get_json(service_name, url):
    """
    Gọi GET tới một service khác.

    - 200 -> trả về dict JSON
    - 404 -> trả về None (không tồn tại)
    - không kết nối được / timeout / lỗi khác -> ServiceUnavailableError
    """
    logger.info("Calling %s: GET %s", service_name, url)
    try:
        response = requests.get(url, timeout=settings.EXTERNAL_API_TIMEOUT)
    except requests.RequestException as exc:  # ConnectionError, Timeout, ...
        logger.warning("%s error: %s", service_name, exc)
        raise ServiceUnavailableError(service_name) from exc

    if response.status_code == 404:
        return None
    if response.status_code != 200:
        raise ServiceUnavailableError(service_name)
    return response.json()


def get_student(student_id):
    """Lấy sinh viên từ Student Service. Trả None nếu không tồn tại."""
    url = f"{settings.STUDENT_SERVICE_URL}/api/students/{student_id}/"
    return _get_json("Student Service", url)


def get_thesis(thesis_id):
    """Lấy đề tài từ Thesis Service. Trả None nếu không tồn tại."""
    url = f"{settings.THESIS_SERVICE_URL}/api/theses/{thesis_id}/"
    return _get_json("Thesis Service", url)


def find_student_by_code(student_code):
    """Tìm sinh viên theo mã (dùng cho seed_data). Trả None nếu không có."""
    url = f"{settings.STUDENT_SERVICE_URL}/api/students/?search={student_code}"
    students = _get_json("Student Service", url) or []
    return next((s for s in students if s["student_code"] == student_code), None)


def find_thesis_by_code(thesis_code):
    """Tìm đề tài theo mã (dùng cho seed_data). Trả None nếu không có."""
    url = f"{settings.THESIS_SERVICE_URL}/api/theses/?search={thesis_code}"
    theses = _get_json("Thesis Service", url) or []
    return next((t for t in theses if t["thesis_code"] == thesis_code), None)
