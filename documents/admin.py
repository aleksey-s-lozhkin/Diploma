from django.contrib import admin
from django.utils.html import format_html

from .models import Document, SearchHistory


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ["id", "user", "rubrics_preview", "text_preview", "created_date"]
    list_filter = ["user", "created_date", "rubrics"]
    search_fields = ["text", "rubrics"]
    ordering = ["-created_date"]
    list_per_page = 25
    readonly_fields = ["created_date"]
    fields = ["user", "rubrics", "text", "is_public", "file", "file_name", "file_type", "created_date"]
    actions = ["delete_selected"]

    def rubrics_preview(self, obj):
        if obj.rubrics:
            return ", ".join(obj.rubrics[:3])
        return "-"

    rubrics_preview.short_description = "Рубрики"

    def text_preview(self, obj):
        if obj.text:
            preview = obj.text[:100]
            if len(obj.text) > 100:
                preview += "..."
            return format_html('<span title="{}">{}</span>', obj.text, preview)
        return "-"

    text_preview.short_description = "Текст (превью)"

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.user = request.user
        super().save_model(request, obj, form, change)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("user")


@admin.register(SearchHistory)
class SearchHistoryAdmin(admin.ModelAdmin):
    list_display = ["id", "user", "query", "results_count", "created_at"]
    list_filter = ["user", "created_at"]
    search_fields = ["query", "user__email"]  # изменено с user__username
    ordering = ["-created_at"]
    list_per_page = 25
    readonly_fields = ["user", "query", "results_count", "created_at"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
