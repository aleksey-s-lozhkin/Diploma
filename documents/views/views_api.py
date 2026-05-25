from django.http import JsonResponse
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from elasticsearch_dsl import Search
from elasticsearch_dsl.connections import connections
from rest_framework import permissions, status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models import Document
from ..rate_limit import RateLimiters
from ..serializers import DocumentCreateUpdateSerializer, DocumentSerializer


def health_check(request):
    return JsonResponse({"status": "ok"})


class SearchView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        tags=["search"],
        operation_description="Полнотекстовый поиск по документам",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["query"],
            properties={
                "query": openapi.Schema(
                    type=openapi.TYPE_STRING, description="Поисковый запрос", example="разработка python"
                ),
                "page": openapi.Schema(
                    type=openapi.TYPE_INTEGER, description="Номер страницы (по умолчанию 1)", default=1, example=2
                ),
            },
        ),
        responses={
            200: "Успешный поиск",
            400: 'Query parameter "query" required',
            401: "Не авторизован",
            429: "Too many requests (30 per minute)",
        },
    )
    def post(self, request):
        user_id = request.user.id

        # ← Используем новый классовый RateLimiter
        limiter = RateLimiters.api_search()
        allowed, remaining, retry_after = limiter.check(f"user_{user_id}")

        if not allowed:
            return Response(
                {"error": f"Too many requests. Please wait {retry_after} seconds."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        query = request.data.get("query", "")
        if not query:
            return Response({"error": "Query parameter 'query' required"}, status=400)

        connections.configure(default={"hosts": "http://elasticsearch:9200"})

        s = Search(index="documents").query(
            "bool",
            must=[{"match": {"text": query}}],
            should=[{"term": {"user_id": request.user.id}}, {"term": {"is_public": True}}],
            minimum_should_match=1,
        )

        page = int(request.data.get("page", 1))
        page_size = 20
        start = (page - 1) * page_size
        s = s[start : start + page_size]

        response = s.execute()

        results = []
        for hit in response:
            rubrics = list(hit.rubrics) if hit.rubrics else []

            results.append(
                {
                    "id": hit.id,
                    "rubrics": rubrics,
                    "text": hit.text[:500] + "..." if len(hit.text) > 500 else hit.text,
                }
            )

        total = response.hits.total.value
        total_pages = (total + page_size - 1) // page_size

        return Response(
            {
                "count": total,
                "next": page + 1 if page < total_pages else None,
                "previous": page - 1 if page > 1 else None,
                "results": results,
                "rate_limit": {"remaining": remaining},
            }
        )


class DocumentViewSet(viewsets.ModelViewSet):
    serializer_class = DocumentSerializer
    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        tags=["documents"],
        operation_description="Получить список всех документов пользователя",
        responses={200: DocumentSerializer(many=True)},
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @swagger_auto_schema(
        tags=["documents"],
        operation_description="Создать новый документ",
        request_body=DocumentCreateUpdateSerializer,
        responses={201: DocumentSerializer()},
    )
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @swagger_auto_schema(
        tags=["documents"], operation_description="Получить документ по ID", responses={200: DocumentSerializer()}
    )
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @swagger_auto_schema(
        tags=["documents"],
        operation_description="Обновить документ полностью",
        request_body=DocumentCreateUpdateSerializer,
        responses={200: DocumentSerializer()},
    )
    def update(self, request, *args, **kwargs):
        # Rate limiting на обновление
        limiter = RateLimiters.api_general()
        allowed, remaining, retry_after = limiter.check(f"user_{request.user.id}_update")

        if not allowed:
            from rest_framework.exceptions import Throttled

            raise Throttled(wait=retry_after)

        return super().update(request, *args, **kwargs)

    @swagger_auto_schema(
        tags=["documents"],
        operation_description="Частично обновить документ",
        request_body=DocumentCreateUpdateSerializer,
        responses={200: DocumentSerializer()},
    )
    def partial_update(self, request, *args, **kwargs):
        return super().partial_update(request, *args, **kwargs)

    @swagger_auto_schema(
        tags=["documents"], operation_description="Удалить документ", responses={204: "Документ удалён"}
    )
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    def get_queryset(self):
        return Document.objects.filter(user=self.request.user).order_by("-created_date")

    def get_serializer_class(self):
        if self.action in ["create", "update", "partial_update"]:
            return DocumentCreateUpdateSerializer
        return DocumentSerializer

    def perform_create(self, serializer):
        # Добавим rate limiting на создание документов
        limiter = RateLimiters.api_general()
        allowed, remaining, retry_after = limiter.check(f"user_{self.request.user.id}_create")

        if not allowed:
            from rest_framework.exceptions import Throttled

            raise Throttled(wait=retry_after)

        serializer.save(user=self.request.user)
