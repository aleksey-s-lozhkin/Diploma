from django.http import JsonResponse
from rest_framework import permissions, status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .models import Document
from .serializers import DocumentCreateUpdateSerializer, DocumentSerializer, RegisterSerializer, UserSerializer


def health_check(request):
    return JsonResponse({"status": "ok"})


class RegisterView(APIView):
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
        serializer = UserSerializer(request.user)
        return Response(serializer.data)


class SearchView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        from elasticsearch_dsl import Search
        from elasticsearch_dsl.connections import connections

        query = request.data.get("query", "")
        if not query:
            return Response({"error": "Query required"}, status=400)

        connections.configure(default={"hosts": "http://elasticsearch:9200"})
        s = Search(index="documents")
        s = s.query("match", text=query)
        s = s.filter("term", user_id=request.user.id)
        response = s.execute()

        results = [{"id": hit.id, "text": hit.text} for hit in response]

        return Response({"count": response.hits.total.value, "results": results})


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
