from django.urls import path

from . import views, grading_views, account_views

urlpatterns = [
    path("cham-diem/", grading_views.grade_list, name="grade_list"),
    path("cham-diem/<int:pk>/chi-tiet/", grading_views.grade_detail, name="grade_detail"),
    path("cham-diem/<int:pk>/xoa/", grading_views.grade_delete, name="grade_delete"),
    path("cham-diem/<int:pk>/", grading_views.grade_edit, name="grade_edit"),
    path("tai-khoan/<int:pk>/sua/", account_views.account_edit, name="account_edit"),
    path("ho-so/", account_views.profile, name="profile"),
    path("nhat-ky/", account_views.audit_log_list, name="audit_log_list"),
    path("dang-nhap/", views.login_view, name="login"),
    path("dang-xuat/", views.logout_view, name="logout"),
    path("doi-mat-khau/", views.change_password_view, name="change_password"),

    path("", views.dashboard, name="dashboard"),

    path("sinh-vien/", views.student_list, name="student_list"),
    path("sinh-vien/them/", views.student_form, name="student_create"),
    path("sinh-vien/<int:pk>/sua/", views.student_form, name="student_edit"),
    path("sinh-vien/<int:pk>/xoa/", views.student_delete, name="student_delete"),

    path("de-tai/", views.thesis_list, name="thesis_list"),
    path("de-tai/them/", views.thesis_form, name="thesis_create"),
    path("de-tai/<int:pk>/sua/", views.thesis_form, name="thesis_edit"),
    path("de-tai/<int:pk>/xoa/", views.thesis_delete, name="thesis_delete"),

    # Mỗi path() ánh xạ một đường dẫn URL đến một hàm xử lý tương ứng trong views.py
    # URL: /dang-ky/
    # Gọi registration_list() để hiển thị danh sách đăng ký đồ án
    path("dang-ky/", views.registration_list, name="registration_list"),

    # URL: /dang-ky/them/
    # Gọi registration_create() để hiển thị biểu mẫu và xử lý việc đăng ký đồ án
    path("dang-ky/them/", views.registration_create, name="registration_create"),

    # URL: /dang-ky/<pk>/trang-thai/
    # Nhận mã định danh đăng ký qua pk
    # Gọi registration_status() để xử lý việc cập nhật trạng thái đăng ký
    path(
        "dang-ky/<int:pk>/trang-thai/",
        views.registration_status,
        name="registration_status"
    ),

    # URL: /dang-ky/<pk>/xoa/
    # Nhận mã định danh đăng ký qua pk
    # Gọi registration_delete() để xóa hẳn bản ghi đăng ký (chỉ ADMIN)
    path(
        "dang-ky/<int:pk>/xoa/",
        views.registration_delete,
        name="registration_delete"
    ),

    # URL: /dang-ky/<pk>/ - chi tiết đăng ký + nhận xét / tiến độ (GET), ghi tiến độ (POST)
    path("dang-ky/<int:pk>/", views.registration_detail, name="registration_detail"),

    # URL: /dang-ky/<pk>/huy/ - hủy đăng ký (giữ lịch sử, trạng thái CANCELLED)
    path("dang-ky/<int:pk>/huy/", views.registration_cancel, name="registration_cancel"),


    # Quản lý tài khoản (chỉ ADMIN) - gọi API của Identity Service
    path("tai-khoan/", views.account_list, name="account_list"),
    path("tai-khoan/them/", views.account_create, name="account_create"),
    path("tai-khoan/<int:pk>/trang-thai/", views.account_toggle_active, name="account_toggle_active"),
    path("tai-khoan/<int:pk>/mo-khoa/", views.account_unlock, name="account_unlock"),

    path("api-docs/", views.api_docs, name="api_docs"),
]
