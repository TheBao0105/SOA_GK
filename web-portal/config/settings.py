"""
Cấu hình Django cho WEB PORTAL (port 8000) - giao diện quản lý.

Web Portal KHÔNG có database riêng và KHÔNG kết nối database của service nào.
Mọi dữ liệu đều lấy qua REST API của các service:
Student (8001), Thesis (8002), Registration (8003), Identity (8004 - đăng nhập).
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-web-portal")
DEBUG = os.getenv("DEBUG", "True") == "True"
ALLOWED_HOSTS = [h.strip() for h in os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]").split(",") if h.strip()]

# Giữ cấu hình triển khai thật giống các API service: chặn SECRET_KEY yếu khi DEBUG=False.
if not DEBUG and (SECRET_KEY.startswith("dev-secret-key") or len(SECRET_KEY) < 50):
    from django.core.exceptions import ImproperlyConfigured
    raise ImproperlyConfigured("Production requires a unique SECRET_KEY of at least 50 characters.")

SECURE_SSL_REDIRECT = os.getenv("SECURE_SSL_REDIRECT", str(not DEBUG)) == "True"
SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "3600" if not DEBUG else "0"))
CSRF_TRUSTED_ORIGINS = [v.strip() for v in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",") if v.strip()]
if os.getenv("TRUST_PROXY_HEADERS", "False") == "True":
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

INSTALLED_APPS = [
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "portal",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    # Chưa đăng nhập -> chuyển về /dang-nhap/; gắn token cho mọi lời gọi API
    "portal.auth.LoginRequiredMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.messages.context_processors.messages",
                "portal.context_processors.service_urls",
                "portal.context_processors.current_user",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# Không dùng database
DATABASES = {}

# Thông báo (Lưu thành công, lỗi...) lưu trong cookie vì không có database
MESSAGE_STORAGE = "django.contrib.messages.storage.cookie.CookieStorage"

# Phiên đăng nhập (chứa access/refresh token) lưu trong cookie ĐÃ KÝ:
# người dùng không sửa được, JavaScript không đọc được (HttpOnly).
SESSION_ENGINE = "django.contrib.sessions.backends.signed_cookies"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 60 * 60 * 24  # bằng thời hạn refresh token (24 giờ)
SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", str(not DEBUG)) == "True"  # True khi chạy HTTPS
CSRF_COOKIE_SECURE = SESSION_COOKIE_SECURE

LANGUAGE_CODE = "vi"
TIME_ZONE = "Asia/Ho_Chi_Minh"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"

# Địa chỉ 3 service (đọc từ .env)
STUDENT_SERVICE_URL = os.getenv("STUDENT_SERVICE_URL", "http://127.0.0.1:8001")
THESIS_SERVICE_URL = os.getenv("THESIS_SERVICE_URL", "http://127.0.0.1:8002")
REGISTRATION_SERVICE_URL = os.getenv("REGISTRATION_SERVICE_URL", "http://127.0.0.1:8003")
IDENTITY_SERVICE_URL = os.getenv("IDENTITY_SERVICE_URL", "http://127.0.0.1:8004")

# Timeout (giây) cho mỗi HTTP request
EXTERNAL_API_TIMEOUT = float(os.getenv("EXTERNAL_API_TIMEOUT", "10"))
