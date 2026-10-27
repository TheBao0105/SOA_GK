from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import AuditLog, User


@admin.register(User)
class AccountAdmin(UserAdmin):
    list_display = ["id", "username", "email", "full_name", "role", "student_id", "is_active", "locked_until"]
    list_filter = ["role", "is_active"]
    search_fields = ["username", "email", "full_name"]
    fieldsets = UserAdmin.fieldsets + (
        ("Thông tin hệ thống đồ án", {"fields": ("full_name", "role", "student_id", "failed_login_count", "locked_until")}),
    )


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ["created_at", "action", "username", "actor_id", "target_id", "ip_address"]
    list_filter = ["action"]
    readonly_fields = [f.name for f in AuditLog._meta.fields]
