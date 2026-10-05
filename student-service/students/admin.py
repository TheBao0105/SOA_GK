from django.contrib import admin

from .models import Student


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ["id", "student_code", "full_name", "email", "class_name", "major"]
    search_fields = ["student_code", "full_name", "email"]
