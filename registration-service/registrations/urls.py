from django.urls import path

from . import views

urlpatterns = [
    path("registrations/", views.RegistrationListCreateView.as_view(), name="registration-list"),
    path(
        "registrations/<int:pk>/",
        views.RegistrationDetailView.as_view(),
        name="registration-detail",
    ),
    path("registrations/<int:pk>/cancel/", views.RegistrationCancelView.as_view(), name="registration-cancel"),
    path("registrations/<int:pk>/notes/", views.ProgressNoteListCreateView.as_view(), name="registration-notes"),
    path("periods/", views.PeriodListCreateView.as_view(), name="period-list"),
    path("periods/current/", views.CurrentPeriodView.as_view(), name="period-current"),
    path("periods/<int:pk>/", views.PeriodDetailView.as_view(), name="period-detail"),
]
