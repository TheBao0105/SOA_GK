from django.conf import settings


def service_urls(request):
    """Cho template biết địa chỉ 3 service (dùng ở menu API Docs)."""
    return {
        "STUDENT_SERVICE_URL": settings.STUDENT_SERVICE_URL,
        "THESIS_SERVICE_URL": settings.THESIS_SERVICE_URL,
        "REGISTRATION_SERVICE_URL": settings.REGISTRATION_SERVICE_URL,
    }
