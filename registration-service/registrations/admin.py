from django.contrib import admin

from .models import Registration


@admin.register(Registration)
class RegistrationAdmin(admin.ModelAdmin):
    list_display = ["id", "student_id", "thesis_id", "status", "registered_at"]
    list_filter = ["status"]
