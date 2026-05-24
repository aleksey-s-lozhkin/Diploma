from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import include, path
from drf_yasg import openapi
from drf_yasg.views import get_schema_view
from rest_framework import permissions


def health_check(request):
    return HttpResponse("OK")


schema_view = get_schema_view(
    openapi.Info(
        title="Document Search API",
        default_version="v1",
        description="API для полнотекстового поиска документов",
        terms_of_service="https://www.google.com/policies/terms/",
        contact=openapi.Contact(email="aleksey.s.lozhkin@gmail.com"),
        license=openapi.License(name="MIT License"),
    ),
    public=True,
    permission_classes=[permissions.AllowAny],
)


urlpatterns = [
    # Документация API
    path("swagger/", schema_view.with_ui("swagger", cache_timeout=0), name="schema-swagger-ui"),
    path("redoc/", schema_view.with_ui("redoc", cache_timeout=0), name="schema-redoc"),
    path("swagger.json", schema_view.without_ui(cache_timeout=0), name="schema-json"),
    # Администрирование и мониторинг
    path("admin/", admin.site.urls),
    path("health/", health_check, name="health_check"),
    # API эндпоинты
    path("api/", include("documents.urls")),
    path("api/", include("users.urls")),
    # Frontend (HTMX)
    path("", include("documents.urls_frontend")),
    # Перенаправления
    path("accounts/login/", lambda request: redirect("/login/")),
]


if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
