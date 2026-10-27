from django.urls import include, path

urlpatterns = [
    # Compatibility URLs use the same Identity/JWT login as the main Portal.
    path("accounts/", include("accounts.urls")),
    path("", include("portal.urls")),
]
