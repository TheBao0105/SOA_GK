from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),

    path("sinh-vien/", views.student_list, name="student_list"),
    path("sinh-vien/them/", views.student_form, name="student_create"),
    path("sinh-vien/<int:pk>/sua/", views.student_form, name="student_edit"),
    path("sinh-vien/<int:pk>/xoa/", views.student_delete, name="student_delete"),

    path("de-tai/", views.thesis_list, name="thesis_list"),
    path("de-tai/them/", views.thesis_form, name="thesis_create"),
    path("de-tai/<int:pk>/sua/", views.thesis_form, name="thesis_edit"),
    path("de-tai/<int:pk>/xoa/", views.thesis_delete, name="thesis_delete"),

    path("dang-ky/", views.registration_list, name="registration_list"),
    path("dang-ky/them/", views.registration_create, name="registration_create"),
    path("dang-ky/<int:pk>/trang-thai/", views.registration_status, name="registration_status"),
    path("dang-ky/<int:pk>/xoa/", views.registration_delete, name="registration_delete"),

    path("api-docs/", views.api_docs, name="api_docs"),
]
