from django.urls import include, path

urlpatterns = [
    # Khi người dùng truy cập đường dẫn gốc "/",
    # Django chuyển việc xử lý URL sang file portal.urls
    path("", include("portal.urls")),
]
