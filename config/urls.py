from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.shortcuts import redirect
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from config.health import liveness, readiness

urlpatterns = [
    # API документация Swagger
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    # Стандартные маршруты
    path("admin/", admin.site.urls),
    # Healthcheck: liveness — жив ли процесс, readiness — готов ли он к трафику
    path("health/", liveness, name="health_liveness"),
    path("health/ready/", readiness, name="health_readiness"),
    # REST API
    path("api/", include("documents.urls.urls_api")),
    path("api/", include("users.urls.urls_api")),
    # Web интерфейс (HTMX)
    path("", include("documents.urls.urls_web")),
    path("", include("users.urls.urls_web")),
    # Редирект для совместимости со стандартным URL входа
    path("accounts/login/", lambda request: redirect("/login/")),
]

# Раздача статики и медиа в режиме DEBUG
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
