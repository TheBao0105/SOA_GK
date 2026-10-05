"""
Client gọi REST API của 3 service.

Web Portal chỉ là một "người dùng" của các service: nó không biết gì về
database, chỉ biết URL + JSON. Đây chính là tính tái sử dụng của SOA:
cùng một API mà Registration Service đang dùng, Web Portal cũng dùng được.
"""
import requests
from django.conf import settings


class ServiceUnavailable(Exception):
    """Service không phản hồi (đang tắt, timeout...)."""


class NotFound(Exception):
    """API trả về 404."""


class ApiError(Exception):
    """API trả về 400 - dữ liệu không hợp lệ. data là JSON lỗi của API."""

    def __init__(self, data):
        self.data = data if isinstance(data, dict) else {"error": str(data)}
        super().__init__(str(self.data))


class Resource:
    """Một tài nguyên REST, ví dụ /api/students/ của Student Service."""

    def __init__(self, service_name, base_url, path):
        self.service_name = service_name
        self.url = f"{base_url}{path}"

    def _request(self, method, url, **kwargs):
        try:
            response = requests.request(
                method, url, timeout=settings.EXTERNAL_API_TIMEOUT, **kwargs
            )
        except requests.RequestException:
            raise ServiceUnavailable(f"{self.service_name} không hoạt động")

        if response.status_code == 404:
            raise NotFound()
        if response.status_code == 503:
            # Registration Service báo một service khác đang tắt
            raise ServiceUnavailable(response.json().get("error", self.service_name))
        if response.status_code >= 500:
            raise ServiceUnavailable(f"{self.service_name} gặp lỗi")
        if response.status_code >= 400:
            raise ApiError(response.json())
        return response.json() if response.content else None

    def list(self, params=None):
        return self._request("GET", self.url, params=params)

    def get(self, pk):
        return self._request("GET", f"{self.url}{pk}/")

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


def is_online(base_url):
    """Kiểm tra nhanh một service có đang chạy không (dùng ở trang API Docs)."""
    try:
        requests.get(f"{base_url}/api/schema/", timeout=2)
        return True
    except requests.RequestException:
        return False
