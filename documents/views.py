from django.http import JsonResponse
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .serializers import RegisterSerializer, UserSerializer


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
        import sys
        import traceback

        try:
            print("=== SEARCH CALLED ===", file=sys.stderr)
            print(f"User: {request.user}", file=sys.stderr)
            print(f"Data: {request.data}", file=sys.stderr)

            from elasticsearch_dsl import Search
            from elasticsearch_dsl.connections import connections

            query = request.data.get("query", "")

            client = connections.get_connection()
            s = Search(using=client, index="documents")
            s = s.query("match", text=query)
            s = s.filter("term", user_id=request.user.id)
            response = s.execute()

            return Response(
                {"count": response.hits.total.value, "results": [{"id": hit.id, "text": hit.text} for hit in response]}
            )
        except Exception as e:
            print(f"ERROR: {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            return Response({"error": str(e)}, status=500)


class PingView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        return Response({"ping": "pong"})
