from rest_framework.views import exception_handler


def api_exception_handler(exc, context):
    """Thêm trường "code" vào lỗi của DRF để client biết lý do (token_expired, ...)."""
    response = exception_handler(exc, context)
    if response is not None and isinstance(response.data, dict) and "detail" in response.data:
        code = getattr(response.data["detail"], "code", None)
        if code:
            response.data["code"] = code
    return response
