from django.contrib import admin

from .models import Thesis


@admin.register(Thesis)
class ThesisAdmin(admin.ModelAdmin):
    list_display = ["id", "thesis_code", "title", "supervisor", "max_students", "status"]
    list_filter = ["status"]
    search_fields = ["thesis_code", "title", "supervisor"]
