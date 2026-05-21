from django.contrib import admin
from django.contrib.auth.models import User
from django.utils.html import format_html

from .models import Document, SearchHistory


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    """Настройка отображения документов в админке"""

    # Поля, отображаемые в списке
    list_display = ["id", "user", "rubrics_preview", "text_preview", "created_date"]

    # Фильтры
    list_filter = ["user", "created_date", "rubrics"]

    # Поиск
    search_fields = ["text", "rubrics"]

    # Сортировка по умолчанию
    ordering = ["-created_date"]

    # Количество записей на странице
    list_per_page = 25

    # Только для чтения (редактировать нельзя)
    readonly_fields = ["created_date"]

    # Поля для редактирования
    fields = ["user", "rubrics", "text", "is_public", "file", "file_name", "file_type", "created_date"]

    # Действия
    actions = ["delete_selected"]

    def rubrics_preview(self, obj):
        """Превью рубрик"""
        if obj.rubrics:
            return ", ".join(obj.rubrics[:3])
        return "-"

    rubrics_preview.short_description = "Рубрики"
    rubrics_preview.admin_order_field = "rubrics"

    def text_preview(self, obj):
        """Превью текста (первые 100 символов)"""
        if obj.text:
            preview = obj.text[:100]
            if len(obj.text) > 100:
                preview += "..."
            return format_html('<span title="{}">{}</span>', obj.text, preview)
        return "-"

    text_preview.short_description = "Текст (превью)"

    def save_model(self, request, obj, form, change):
        """Автоматически устанавливаем пользователя при создании"""
        if not obj.pk:
            obj.user = request.user
        super().save_model(request, obj, form, change)

    def get_queryset(self, request):
        """Оптимизация запросов"""
        return super().get_queryset(request).select_related("user")


@admin.register(SearchHistory)
class SearchHistoryAdmin(admin.ModelAdmin):
    """Настройка отображения истории поиска в админке"""

    list_display = ["id", "user", "query", "results_count", "created_at"]
    list_filter = ["user", "created_at"]
    search_fields = ["query", "user__username"]
    ordering = ["-created_at"]
    list_per_page = 25
    readonly_fields = ["user", "query", "results_count", "created_at"]

    def has_add_permission(self, request):
        """Запрещаем добавление через админку"""
        return False

    def has_change_permission(self, request, obj=None):
        """Запрещаем изменение через админку"""
        return False


# Настройка админки для пользователей (расширение)
class CustomUserAdmin(admin.ModelAdmin):
    """Расширенная админка для пользователей"""

    list_display = ["id", "username", "email", "first_name", "last_name", "is_staff", "documents_count", "date_joined"]
    list_filter = ["is_staff", "is_active", "date_joined"]
    search_fields = ["username", "email", "first_name", "last_name"]
    ordering = ["-date_joined"]

    def documents_count(self, obj):
        """Количество документов пользователя"""
        return obj.documents.count()

    documents_count.short_description = "Документов"
    documents_count.admin_order_field = "documents__count"


# Перерегистрируем модель User с расширенными настройками
try:
    admin.site.unregister(User)
except admin.sites.NotRegistered:
    pass
admin.site.register(User, CustomUserAdmin)
