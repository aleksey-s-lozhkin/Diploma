import os

from django.conf import settings
from django.db import models
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import permissions, status, viewsets
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from documents.models import Document, SearchHistory
from documents.rate_limit import RateLimiters
from documents.serializers import DocumentCreateUpdateSerializer, DocumentSerializer
from documents.services.search_service import SearchService
from documents.utils import extract_text_from_file


class SearchView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        tags=["search"],
        operation_description="Полнотекстовый поиск по документам с фильтрацией",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["query"],
            properties={
                "query": openapi.Schema(
                    type=openapi.TYPE_STRING, description="Поисковый запрос", example="python разработка"
                ),
                "rubric": openapi.Schema(
                    type=openapi.TYPE_STRING, description="Фильтр по рубрике", example="технологии"
                ),
                "privacy": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    enum=["all", "public", "private"],
                    description="Тип доступа",
                    default="all",
                ),
                "page": openapi.Schema(type=openapi.TYPE_INTEGER, description="Номер страницы", default=1),
            },
        ),
        responses={
            200: "Успешный поиск",
            400: "Query parameter 'query' required",
            401: "Не авторизован",
            429: "Too many requests (30 per minute)",
        },
    )
    def post(self, request):
        user_id = request.user.id

        # Rate limiting
        limiter = RateLimiters.api_search()
        allowed, remaining, retry_after = limiter.check(f"user_{user_id}")

        if not allowed:
            return Response(
                {"error": f"Too many requests. Please wait {retry_after} seconds."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
                headers={"X-RateLimit-Retry-After": str(retry_after)},
            )

        # Получаем параметры запроса
        query = request.data.get("query", "").strip()
        rubric = request.data.get("rubric", "")
        privacy = request.data.get("privacy", "all")
        page = int(request.data.get("page", 1))

        if not query:
            return Response({"error": "Query parameter 'query' required"}, status=status.HTTP_400_BAD_REQUEST)

        # Используем сервис поиска
        service = SearchService(request.user)
        search_response = service.search(
            query=query,
            rubric=rubric,
            privacy=privacy,
            page=page,
            save_history=True,
            with_highlights=False,
            truncate_text=True,
            max_text_length=500,
        )

        total_pages = search_response.total_pages

        return Response(
            {
                "count": search_response.total,
                "next": page + 1 if page < total_pages else None,
                "previous": page - 1 if page > 1 else None,
                "results": [r.to_dict() for r in search_response.results],
            },
            headers={
                "X-RateLimit-Limit": str(limiter.limit),
                "X-RateLimit-Remaining": str(remaining),
            },
        )


class DocumentViewSet(viewsets.ModelViewSet):
    serializer_class = DocumentSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [JSONParser, MultiPartParser]

    @swagger_auto_schema(
        tags=["documents"],
        operation_description="Получить список всех документов пользователя",
        responses={200: DocumentSerializer(many=True)},
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @swagger_auto_schema(
        tags=["documents"],
        operation_description="Создать новый документ (текст или файл)",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "rubrics": openapi.Schema(
                    type=openapi.TYPE_STRING, description="Рубрики через запятую", example="технологии, python, django"
                ),
                "text": openapi.Schema(type=openapi.TYPE_STRING, description="Текст документа (если без файла)"),
                "is_public": openapi.Schema(type=openapi.TYPE_BOOLEAN, description="Публичный доступ", default=False),
                "file": openapi.Schema(type=openapi.TYPE_FILE, description="Файл (PDF, DOCX, XLSX, TXT)"),
            },
        ),
        responses={201: DocumentSerializer()},
    )
    def create(self, request, *args, **kwargs):
        # Rate limiting
        limiter = RateLimiters.api_general()
        allowed, remaining, retry_after = limiter.check(f"user_{request.user.id}_create")

        if not allowed:
            from rest_framework.exceptions import Throttled

            raise Throttled(wait=retry_after)

        # Обработка рубрик
        rubrics_data = request.data.get("rubrics", [])
        if isinstance(rubrics_data, str):
            rubrics = [r.strip() for r in rubrics_data.split(",") if r.strip()]
        else:
            rubrics = rubrics_data

        # Обработка is_public
        is_public = request.data.get("is_public", False)
        if isinstance(is_public, str):
            is_public = is_public.lower() == "true"

        # Проверяем, есть ли загруженный файл
        uploaded_file = request.FILES.get("file")

        if uploaded_file:
            file_name = uploaded_file.name
            file_type = file_name.split(".")[-1].lower()

            # Валидация типа файла
            allowed_types = ["pdf", "docx", "xlsx", "txt"]
            if file_type not in allowed_types:
                return Response(
                    {"error": f"Неподдерживаемый тип файла. Разрешены: {', '.join(allowed_types)}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Валидация количества рубрик
            if len(rubrics) > 10:
                return Response({"error": "Не более 10 рубрик"}, status=status.HTTP_400_BAD_REQUEST)

            # Создаём документ
            document = Document.objects.create(
                user=request.user,
                rubrics=rubrics,
                text="",
                is_public=is_public,
                file=uploaded_file,
                file_name=file_name,
                file_type=file_type,
                text_source="file",
            )

            # Извлекаем текст из файла
            file_path = os.path.join(settings.MEDIA_ROOT, document.file.name)
            extracted_text = extract_text_from_file(file_path, file_type)
            document.text = extracted_text
            document.save()

            serializer = self.get_serializer(document)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        else:
            text = request.data.get("text", "")
            if not text:
                return Response(
                    {"error": "Укажите либо 'text', либо загрузите 'file'"}, status=status.HTTP_400_BAD_REQUEST
                )

            # Валидация количества рубрик
            if len(rubrics) > 10:
                return Response({"error": "Не более 10 рубрик"}, status=status.HTTP_400_BAD_REQUEST)

            # Передаём обработанные данные в сериализатор
            modified_data = request.data.copy()
            modified_data["rubrics"] = rubrics
            modified_data["is_public"] = is_public

            serializer = self.get_serializer(data=modified_data)
            serializer.is_valid(raise_exception=True)
            self.perform_create(serializer)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

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
        serializer.save(user=self.request.user)


class RubricsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        tags=["search"],
        operation_description="Получить список всех рубрик из доступных пользователю документов",
        responses={200: openapi.Schema(type=openapi.TYPE_ARRAY, items=openapi.Schema(type=openapi.TYPE_STRING))},
    )
    def get(self, request):
        documents = Document.objects.filter(models.Q(user=request.user) | models.Q(is_public=True)).values_list(
            "rubrics", flat=True
        )

        unique_rubrics = set()
        for rubrics_list in documents:
            for rubric in rubrics_list:
                unique_rubrics.add(rubric)

        return Response(sorted(unique_rubrics))


class SearchHistoryDeleteView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        tags=["search"],
        operation_description="Удалить запись из истории поиска",
        responses={204: "Удалено", 404: "Не найдено"},
    )
    def delete(self, request, pk):
        try:
            history = SearchHistory.objects.get(pk=pk, user=request.user)
            history.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except SearchHistory.DoesNotExist:
            return Response({"error": "History entry not found"}, status=status.HTTP_404_NOT_FOUND)
