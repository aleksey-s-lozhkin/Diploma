from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import include, path
from drf_yasg import openapi
from drf_yasg.views import get_schema_view
from rest_framework import permissions


def health_check(request):
    return JsonResponse({"status": "ok"})


schema_view = get_schema_view(
    openapi.Info(
        title="Document Search API",
        default_version="v1",
        description="API для полнотекстового поиска документов",
        contact=openapi.Contact(email="aleksey.s.lozhkin@gmail.com"),
        license=openapi.License(name="MIT License"),
    ),
    public=True,
    permission_classes=[permissions.AllowAny],
)

urlpatterns = [
    # Swagger документация
    path("swagger/", schema_view.with_ui("swagger", cache_timeout=0), name="schema-swagger-ui"),
    path("redoc/", schema_view.with_ui("redoc", cache_timeout=0), name="schema-redoc"),
    path("swagger.json", schema_view.without_ui(cache_timeout=0), name="schema-json"),
    # Администрирование
    path("admin/", admin.site.urls),
    path("health/", health_check, name="health_check"),
    # API (REST)
    path("api/", include("documents.urls.urls_api")),
    path("api/", include("users.urls.urls_api")),
    # Frontend (HTML/HTMX)
    path("", include("documents.urls.urls_web")),
    path("", include("users.urls.urls_web")),
    # Перенаправления
    path("accounts/login/", lambda request: redirect("/login/")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
