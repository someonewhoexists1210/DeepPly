from django.contrib import admin
from .models import *

# Register your models here.
admin.site.register(AnalysisResult)
admin.site.register(Position)

@admin.register(TaskResult)
class TaskAdmin(admin.ModelAdmin):
    list_display = ('task', 'status', 'progress', 'retry_count', 'started', 'updated_at')
    search_fields = ("task_id", )
    list_filter = ("status",)
    sortable_by = ("started", "updated_at")
    ordering = ("-updated_at",)

    def task(self, obj):
        return obj.task_id[:8]

