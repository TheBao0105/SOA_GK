"""
Cấu hình WSGI của project config.

Biến ``application`` ở cấp module là đối tượng WSGI để máy chủ gọi.

Xem thêm về file này tại
https://docs.djangoproject.com/en/6.1/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

application = get_wsgi_application()
