from django.http import JsonResponse
from elasticsearch_dsl import Search
from elasticsearch_dsl.connections import connections
from rest_framework import permissions, status, viewsets
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .models import Document
from .rate_limit import RateLimiters  # ← меняем импорт
from .serializers import DocumentCreateUpdateSerializer, DocumentSerializer


def health_check(request):
    return JsonResponse({"status": "ok"})


class LogoutView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        refresh_token = request.data.get("refresh")

        if not refresh_token:
            return Response({"error": "Refresh token required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
            return Response(status=status.HTTP_205_RESET_CONTENT)
        except Exception:
            return Response({"error": "Invalid token"}, status=status.HTTP_400_BAD_REQUEST)


class UserProfileView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        from users.serializers import UserSerializer

        serializer = UserSerializer(request.user)
        return Response(serializer.data)


class SearchView(APIView):
    permission_classes = [permissions.IsAuthenticated]

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

    def update(self, request, *args, **kwargs):
        # Rate limiting на обновление
        limiter = RateLimiters.api_general()
        allowed, remaining, retry_after = limiter.check(f"user_{request.user.id}_update")

        if not allowed:
            from rest_framework.exceptions import Throttled

            raise Throttled(wait=retry_after)

        return super().update(request, *args, **kwargs)
