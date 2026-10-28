"""Chuyển lỗi khi đọc REST thành phản hồi của Portal (không truy cập database)."""
from django.contrib import messages
from django.http import Http404
from .api_client import NotFound, ServiceUnavailable


def load(request, fn, *args, default=None):
    try:
        return fn(*args)
    except NotFound:
        raise Http404
    except ServiceUnavailable as exc:
        messages.error(request, str(exc))
        return default


