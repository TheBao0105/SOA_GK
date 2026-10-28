"""
Cấu hình Django cho STUDENT SERVICE (port 8001).

Mọi thông tin nhạy cảm (database, secret key) được đọc từ file .env,
không hard-code trong code.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Đọc biến môi trường từ file .env nằm cùng thư mục manage.py
load_dotenv(BASE_DIR / ".env")


def _path_from_env(name, default):
    """Đọc đường dẫn từ .env; đường dẫn tương đối được tính từ thư mục service."""
    path = Path(os.getenv(name, default))
    return path if path.is_absolute() else (BASE_DIR / path).resolve()

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-student-service")
DEBUG = os.getenv("DEBUG", "True") == "True"
ALLOWED_HOSTS = [h.strip() for h in os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]").split(",") if h.strip()]

if not DEBUG and (SECRET_KEY.startswith("dev-secret-key") or len(SECRET_KEY) < 50):
    from django.core.exceptions import ImproperlyConfigured
    raise ImproperlyConfigured("Production requires a unique SECRET_KEY of at least 50 characters.")

SECURE_SSL_REDIRECT = os.getenv("SECURE_SSL_REDIRECT", str(not DEBUG)) == "True"
SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", str(not DEBUG)) == "True"
CSRF_COOKIE_SECURE = os.getenv("CSRF_COOKIE_SECURE", str(SESSION_COOKIE_SECURE)) == "True"
SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "3600" if not DEBUG else "0"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = os.getenv("SECURE_HSTS_INCLUDE_SUBDOMAINS", "False") == "True"
SECURE_HSTS_PRELOAD = os.getenv("SECURE_HSTS_PRELOAD", "False") == "True"
CSRF_TRUSTED_ORIGINS = [v.strip() for v in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",") if v.strip()]
# Chỉ bật khi chạy sau reverse proxy tin cậy (proxy xóa header X-Forwarded do client tự gửi).
if os.getenv("TRUST_PROXY_HEADERS", "False") == "True":
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Thư viện bên thứ ba
    "rest_framework",
    "drf_spectacular",
    # App của service
    "students",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
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
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# Student Service CHỈ kết nối tới database của chính nó: student_db

DATABASES = {
    "default": {
        "ENGINE": "mssql",
        "NAME": os.getenv("DB_NAME", "student_db"),
        # Mặc định giữ nguyên instance đang dùng; đổi được qua DB_HOST trong .env
        "HOST": os.getenv("DB_HOST", r".\MSSQLSERVER01"),
        "PORT": os.getenv("DB_PORT", ""),
        "Trusted_Connection": "yes",
        "OPTIONS": {
            "driver": os.getenv("DB_DRIVER", "ODBC Driver 17 for SQL Server"),
        },
    }
}


AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Ho_Chi_Minh"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Django REST Framework: mọi API đều phải đăng nhập (JWT do Identity Service cấp)
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["config.jwt_auth.JWTAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "UNAUTHENTICATED_USER": None,
    "EXCEPTION_HANDLER": "config.exceptions.api_exception_handler",
}

# Tài liệu API Swagger (drf-spectacular)
SPECTACULAR_SETTINGS = {
    "TITLE": "Student Service API",
    "DESCRIPTION": "Dịch vụ quản lý SINH VIÊN (SOA demo - port 8001)",
    "VERSION": "1.0.0",
    # Swagger và schema xem được mà không cần token; bấm "Authorize" để dán access token
    "SERVE_PERMISSIONS": ["rest_framework.permissions.AllowAny"],
    "SERVE_AUTHENTICATION": [],
    "SWAGGER_UI_SETTINGS": {"persistAuthorization": True},
}

# ----------------------------------------------------------------- Xác thực JWT
# Chỉ cần KHÓA CÔNG KHAI của Identity Service để xác minh token (không cần khóa bí mật)
JWT_ALGORITHM = "RS256"
JWT_ISSUER = os.getenv("JWT_ISSUER", "identity-service")
JWT_PUBLIC_KEY_PATH = _path_from_env("JWT_PUBLIC_KEY_PATH", "../identity-service/keys/jwt_public.pem")
JWT_PUBLIC_KEY = ""  # dùng trong test: nội dung PEM
JWT_LEEWAY_SECONDS = 10

# Registration Service: hỏi trước khi xóa / giảm chỉ tiêu (đồng bộ dữ liệu giữa các service)
REGISTRATION_SERVICE_URL = os.getenv("REGISTRATION_SERVICE_URL", "http://127.0.0.1:8003")
EXTERNAL_API_TIMEOUT = float(os.getenv("EXTERNAL_API_TIMEOUT", "5"))

IDENTITY_SERVICE_URL = os.getenv("IDENTITY_SERVICE_URL", "http://127.0.0.1:8004")

JWT_CHECK_ACCOUNT_STATE = os.getenv("JWT_CHECK_ACCOUNT_STATE", str(not DEBUG)) == "True"
