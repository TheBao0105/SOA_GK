"""
Cấu hình Django cho IDENTITY SERVICE (port 8004).

Đây là service DUY NHẤT giữ tài khoản và mật khẩu (đã hash) của hệ thống.
Nó cấp JWT ký bằng KHÓA BÍ MẬT RS256; các service khác chỉ cần KHÓA CÔNG KHAI
để tự xác minh token, không cần gọi lại Identity Service ở mỗi request.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")


def _path_from_env(name, default):
    """Đọc đường dẫn từ .env; đường dẫn tương đối được tính từ thư mục service."""
    path = Path(os.getenv(name, default))
    return path if path.is_absolute() else (BASE_DIR / path).resolve()


SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-identity-service")
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
    "accounts",
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

# Identity Service CHỈ kết nối tới database của chính nó: auth_db
DATABASES = {
    "default": {
        "ENGINE": "mssql",
        "NAME": os.getenv("DB_NAME", "auth_db"),
        "HOST": os.getenv("DB_HOST", r".\MSSQLSERVER01"),
        "PORT": os.getenv("DB_PORT", ""),
        "Trusted_Connection": "yes",
        "OPTIONS": {
            "driver": os.getenv("DB_DRIVER", "ODBC Driver 17 for SQL Server"),
        },
    }
}

# Model tài khoản riêng: có vai trò (ADMIN / LECTURER / STUDENT) và khóa tạm thời
AUTH_USER_MODEL = "accounts.User"

# Mật khẩu được hash bằng PBKDF2 (mặc định của Django) và phải đủ mạnh
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Ho_Chi_Minh"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["accounts.authentication.JWTAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "accounts.exceptions.api_exception_handler",
    # Giới hạn số lần gọi API đăng nhập / làm mới token (chống dò mật khẩu)
    "DEFAULT_THROTTLE_RATES": {
        "login": os.getenv("LOGIN_RATE", "10/min"),
        "refresh": os.getenv("REFRESH_RATE", "30/min"),
    },
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Identity Service API",
    "DESCRIPTION": (
        "Dịch vụ ĐĂNG NHẬP / TÀI KHOẢN (SOA - port 8004). "
        "Cấp JWT (RS256) cho Student, Thesis, Registration Service và Web Portal."
    ),
    "VERSION": "1.0.0",
    # Swagger và schema xem được mà không cần token
    "SERVE_PERMISSIONS": ["rest_framework.permissions.AllowAny"],
    "SERVE_AUTHENTICATION": [],
    "SWAGGER_UI_SETTINGS": {"persistAuthorization": True},
}

# ----------------------------------------------------------------- Xác thực JWT
JWT_ALGORITHM = "RS256"
JWT_ISSUER = os.getenv("JWT_ISSUER", "identity-service")
# Khóa BÍ MẬT (chỉ Identity Service có) và khóa CÔNG KHAI (chia cho các service khác)
JWT_PRIVATE_KEY_PATH = _path_from_env("JWT_PRIVATE_KEY_PATH", "keys/jwt_private.pem")
JWT_PUBLIC_KEY_PATH = _path_from_env("JWT_PUBLIC_KEY_PATH", "keys/jwt_public.pem")
# Dùng trong test: truyền thẳng nội dung PEM thay vì đọc file
JWT_PRIVATE_KEY = ""
JWT_PUBLIC_KEY = ""
JWT_LEEWAY_SECONDS = 10

ACCESS_TOKEN_LIFETIME_MINUTES = int(os.getenv("ACCESS_TOKEN_LIFETIME_MINUTES", "15"))
REFRESH_TOKEN_LIFETIME_HOURS = int(os.getenv("REFRESH_TOKEN_LIFETIME_HOURS", "24"))

# Khóa tài khoản tạm thời khi đăng nhập sai nhiều lần
MAX_FAILED_LOGINS = int(os.getenv("MAX_FAILED_LOGINS", "5"))
LOCKOUT_MINUTES = int(os.getenv("LOCKOUT_MINUTES", "15"))

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {"accounts": {"handlers": ["console"], "level": "INFO"}},
}
