from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.db import connections
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from elasticsearch_dsl.connections import connections as es_connections


def health_check(request):
    status = {"status": "ok", "checks": {}}
    http_status = 200

    # Проверка PostgreSQL
    try:
        connections["default"].ensure_connection()
    except Exception as e:
        status["status"] = "warning"
        status["database"] = str(e)
        http_status = 503

    # Проверка Elasticsearch
    try:
        es = es_connections.get_connection()
        es.info()
    except Exception as e:
        status["status"] = "warning"
        status["elasticsearch"] = str(e)
        http_status = 503

    return JsonResponse(status, status=http_status)


urlpatterns = [
    # Swagger документация
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
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
