from django.urls import include, path

urlpatterns = [
    # URL cũ /accounts/ dùng chung luồng đăng nhập Identity/JWT với Portal.
    path("accounts/", include("accounts.urls")),
    path("", include("portal.urls")),
]
