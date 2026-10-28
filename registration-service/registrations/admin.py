from django.contrib import admin

from .models import ProgressNote, Registration


@admin.register(Registration)
class RegistrationAdmin(admin.ModelAdmin):
    list_display = ["id", "student_id", "thesis_id", "status", "registered_at", "processed_by"]
    list_filter = ["status"]


@admin.register(ProgressNote)
class ProgressNoteAdmin(admin.ModelAdmin):
    list_display = ["id", "registration", "author_name", "progress", "created_at"]
