from django.http import JsonResponse
from elasticsearch_dsl import Search
from elasticsearch_dsl.connections import connections
from rest_framework import permissions, status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .models import Document, SearchHistory
from .serializers import (
    DocumentCreateUpdateSerializer,
    DocumentSerializer,
    RegisterSerializer,
    SearchHistorySerializer,
    UserSerializer,
)


def health_check(request):
    """Эндпоинт для проверки работоспособности сервиса."""

    return JsonResponse({"status": "ok", "service": "document-search"})


class RegisterView(APIView):
    """Регистрация нового пользователя"""

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            refresh = RefreshToken.for_user(user)
            return Response(
                {
                    "user": UserSerializer(user).data,
                    "refresh": str(refresh),
                    "access": str(refresh.access_token),
                },
                status=status.HTTP_201_CREATED,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LogoutView(APIView):
    """Выход из системы"""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        try:
            refresh_token = request.data.get("refresh")
            token = RefreshToken(refresh_token)
            token.blacklist()
            return Response(status=status.HTTP_205_RESET_CONTENT)
        except Exception:
            return Response(status=status.HTTP_400_BAD_REQUEST)


class UserProfileView(APIView):
    """Получение информации о текущем пользователе"""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        serializer = UserSerializer(request.user)
        return Response(serializer.data)


class DocumentViewSet(viewsets.ModelViewSet):
    """ViewSet для CRUD операций с документами. Пользователь видит только свои документы."""

    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """Возвращает только документы текущего пользователя"""

        return Document.objects.filter(user=self.request.user).order_by("-created_date")

    def get_serializer_class(self):
        """Разные сериализаторы для разных действий"""

        if self.action in ["create", "update", "partial_update"]:
            return DocumentCreateUpdateSerializer
        return DocumentSerializer

    def perform_create(self, serializer):
        """При создании документа автоматически подставляем пользователя"""

        serializer.save(user=self.request.user)


class SearchView(APIView):
    """Поиск документов через Elasticsearch"""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        query = request.data.get("query", "")
        rubric = request.data.get("rubric", "")
        page = int(request.data.get("page", 1))
        page_size = int(request.data.get("page_size", 20))

        if not query:
            return Response({"error": "Query parameter is required"}, status=status.HTTP_400_BAD_REQUEST)

        # Подключение к Elasticsearch
        client = connections.get_connection()
        s = Search(using=client, index="documents")

        # Поиск по тексту
        s = s.query("match", text=query)

        # Фильтр по пользователю
        s = s.filter("term", user_id=request.user.id)

        # Фильтр по рубрике
        if rubric:
            s = s.filter("term", rubrics=rubric)

        # Highlighting
        s = s.highlight("text", fragment_size=150, number_of_fragments=2)

        # Пагинация
        start = (page - 1) * page_size
        s = s[start : start + page_size]

        # Выполнение поиска
        response = s.execute()

        # Сохраняем историю поиска
        SearchHistory.objects.create(user=request.user, query=query, results_count=response.hits.total.value)

        # Формируем результат
        results = []
        for hit in response:
            result = {
                "id": hit.id,
                "rubrics": hit.rubrics,
                "text": hit.text,
                "created_date": hit.created_date,
                "highlights": hit.meta.highlight.to_dict() if hasattr(hit.meta, "highlight") else {},
            }
            results.append(result)

        return Response({"count": response.hits.total.value, "results": results})


class SearchHistoryView(APIView):
    """История поисковых запросов"""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """Получить историю поиска текущего пользователя"""

        history = SearchHistory.objects.filter(user=request.user).order_by("-created_at")[:50]
        serializer = SearchHistorySerializer(history, many=True)
        return Response(serializer.data)

    def delete(self, request):
        """Очистить историю поиска текущего пользователя"""

        SearchHistory.objects.filter(user=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
