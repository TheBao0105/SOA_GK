from django.contrib import admin

from .models import ProgressNote, Registration, RegistrationPeriod


@admin.register(Registration)
class RegistrationAdmin(admin.ModelAdmin):
    list_display = ["id", "student_id", "thesis_id", "period", "status", "registered_at", "processed_by"]
    list_filter = ["status", "period"]


@admin.register(RegistrationPeriod)
class RegistrationPeriodAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "start_at", "end_at", "is_active", "max_active_per_student"]


@admin.register(ProgressNote)
class ProgressNoteAdmin(admin.ModelAdmin):
    list_display = ["id", "registration", "author_name", "progress", "created_at"]
