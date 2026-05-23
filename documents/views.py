from django.http import JsonResponse
from elasticsearch_dsl import Search
from elasticsearch_dsl.connections import connections
from rest_framework import permissions, status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .models import Document
from .rate_limit import check_rate_limit
from .serializers import DocumentCreateUpdateSerializer, DocumentSerializer


def health_check(request):
    return JsonResponse({"status": "ok"})


class LogoutView(APIView):
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
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        # Используем сериализатор для кастомной модели
        from users.serializers import UserSerializer

        serializer = UserSerializer(request.user)
        return Response(serializer.data)


class SearchView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user_id = request.user.id
        is_allowed, remaining, retry_after = check_rate_limit(f"api_search_{user_id}", 30, 60)

        if not is_allowed:
            return Response({"error": f"Too many requests. Please wait {retry_after} seconds."}, status=429)

        query = request.data.get("query", "")
        if not query:
            return Response({"error": "Query required"}, status=400)

        connections.configure(default={"hosts": "http://elasticsearch:9200"})

        s = Search(index="documents").query(
            "bool",
            must=[{"match": {"text": query}}],
            should=[{"term": {"user_id": request.user.id}}, {"term": {"is_public": True}}],
            minimum_should_match=1,
        )

        response = s.execute()

        results = [{"id": hit.id, "text": hit.text} for hit in response]

        return Response(
            {"count": response.hits.total.value, "results": results, "rate_limit": {"remaining": remaining}}
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
        serializer.save(user=self.request.user)
