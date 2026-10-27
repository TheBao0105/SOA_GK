"""
Phân quyền theo vai trò (RBAC) dựa trên trường "role" trong JWT.

Vai trò do Identity Service cấp và được ký trong token, nên người dùng
KHÔNG thể tự đổi vai trò (sửa token sẽ làm hỏng chữ ký).

File này giống hệt nhau ở student-service, thesis-service và registration-service.
"""
from rest_framework.permissions import SAFE_METHODS, BasePermission

ADMIN = "ADMIN"
LECTURER = "LECTURER"
STUDENT = "STUDENT"
SERVICE = "SERVICE"  # token kỹ thuật giữa các service (chỉ được đọc)

ALL_ROLES = (ADMIN, LECTURER, STUDENT, SERVICE)


def role_of(user):
    return getattr(user, "role", None)


def is_admin(user):
    return role_of(user) == ADMIN


def is_lecturer(user):
    return role_of(user) == LECTURER


def is_student(user):
    return role_of(user) == STUDENT


class RolePermission(BasePermission):
    """
    Khai báo trên view:
        read_roles  = vai trò được GET / HEAD / OPTIONS
        write_roles = {"POST": (...), "PUT": (...), "PATCH": (...), "DELETE": (...)}
    Vai trò không có trong danh sách -> 403.
    """

    message = "You do not have permission to perform this action."

    def has_permission(self, request, view):
        role = role_of(request.user)
        if request.method in SAFE_METHODS:
            return role in getattr(view, "read_roles", ALL_ROLES)
        return role in getattr(view, "write_roles", {}).get(request.method, ())
