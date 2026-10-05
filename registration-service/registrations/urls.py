from django.urls import path

from . import views

urlpatterns = [
    path("registrations/", views.RegistrationListCreateView.as_view(), name="registration-list"),
    path(
        "registrations/<int:pk>/",
        views.RegistrationDetailView.as_view(),
        name="registration-detail",
    ),
]
