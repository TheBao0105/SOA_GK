from django.urls import path

from . import views

urlpatterns = [
    path("theses/", views.ThesisListCreateView.as_view(), name="thesis-list"),
    path("theses/<int:pk>/", views.ThesisDetailView.as_view(), name="thesis-detail"),
]
