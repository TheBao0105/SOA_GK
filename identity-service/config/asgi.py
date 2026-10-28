"""
Cấu hình ASGI của project config.

Biến ``application`` ở cấp module là đối tượng ASGI để máy chủ gọi.

Xem thêm về file này tại
https://docs.djangoproject.com/en/6.1/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

application = get_asgi_application()
