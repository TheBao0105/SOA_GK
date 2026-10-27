from rest_framework.permissions import BasePermission

from .models import User


class IsAdminRole(BasePermission):
    """Chỉ tài khoản có role ADMIN (kiểm tra ở backend, không chỉ ẩn nút ở giao diện)."""

    message = "Only administrators can perform this action."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.role == User.Role.ADMIN)
