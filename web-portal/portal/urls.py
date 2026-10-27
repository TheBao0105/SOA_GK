from django.urls import path

from . import views, grading_views

urlpatterns = [
    path("tai-khoan/<int:pk>/sua/", grading_views.account_edit, name="account_edit"),
    path("cham-diem/", grading_views.assessment_list, name="assessment_list"),
    path("cham-diem/them/", grading_views.assessment_create, name="assessment_create"),
    path("cham-diem/<int:pk>/", grading_views.assessment_detail, name="assessment_detail"),
    path("dot-cham-diem/", grading_views.grading_period_list, name="grading_period_list"),
    path("dot-cham-diem/them/", grading_views.grading_period_form, name="grading_period_create"),
    path("dot-cham-diem/<int:pk>/sua/", grading_views.grading_period_form, name="grading_period_edit"),
    path("ho-so/", grading_views.profile, name="profile"),
    path("nhat-ky/", grading_views.audit_log_list, name="audit_log_list"),
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

    # Đợt đăng ký (chỉ ADMIN) - gọi /api/periods/ của Registration Service
    path("dot-dang-ky/", views.period_list, name="period_list"),
    path("dot-dang-ky/them/", views.period_form, name="period_create"),
    path("dot-dang-ky/<int:pk>/sua/", views.period_form, name="period_edit"),
    path("dot-dang-ky/<int:pk>/trang-thai/", views.period_toggle, name="period_toggle"),
    path("dot-dang-ky/<int:pk>/xoa/", views.period_delete, name="period_delete"),

    # Quản lý tài khoản (chỉ ADMIN) - gọi API của Identity Service
    path("tai-khoan/", views.account_list, name="account_list"),
    path("tai-khoan/them/", views.account_create, name="account_create"),
    path("tai-khoan/<int:pk>/trang-thai/", views.account_toggle_active, name="account_toggle_active"),
    path("tai-khoan/<int:pk>/mo-khoa/", views.account_unlock, name="account_unlock"),

    path("api-docs/", views.api_docs, name="api_docs"),
]
