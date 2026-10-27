"""
Hỏi Registration Service (qua HTTP/REST) xem còn đăng ký hiệu lực hay không,
trước khi xóa sinh viên / đề tài hoặc giảm số chỗ của đề tài.

Service này KHÔNG đọc registration_db: nó chỉ gọi
    GET {REGISTRATION_SERVICE_URL}/api/registrations/?student_id=..&active=true
kèm access token của người đang thao tác. Registration Service tắt thì
KHÔNG cho xóa (an toàn hơn là để lại đăng ký trỏ tới dữ liệu không còn).

File này giống hệt nhau ở student-service và thesis-service.
"""
import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class RegistrationServiceError(Exception):
    def __init__(self):
        super().__init__("Registration Service unavailable")


def count_active_registrations(token, **filters):
    """Số đăng ký còn hiệu lực (PENDING / APPROVED) khớp bộ lọc, ví dụ student_id=1."""
    url = f"{settings.REGISTRATION_SERVICE_URL}/api/registrations/"
    try:
        response = requests.get(
            url,
            params={**filters, "active": "true"},
            headers={"Authorization": f"Bearer {token}"} if token else {},
            timeout=settings.EXTERNAL_API_TIMEOUT,
        )
    except requests.RequestException as exc:
        logger.warning("Registration Service error: %s", exc)
        raise RegistrationServiceError() from exc
    if response.status_code != 200:
        logger.warning("Registration Service returned HTTP %s", response.status_code)
        raise RegistrationServiceError()
    try:
        data = response.json()
    except ValueError as exc:
        raise RegistrationServiceError() from exc
    if not isinstance(data, list):
        raise RegistrationServiceError()
    for item in data:
        if not isinstance(item, dict) or type(item.get("id")) is not int or item["id"] <= 0:
            raise RegistrationServiceError()
        if "status" in item and item["status"] not in ("PENDING", "APPROVED"):
            raise RegistrationServiceError()
        if any(key in item and item[key] != value for key, value in filters.items()):
            raise RegistrationServiceError()
    return len(data)
