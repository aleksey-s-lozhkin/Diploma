from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import exceptions, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from documents.rate_limit import RateLimiters

from .email_utils import send_verification_email
from .serializers import RegisterSerializer, UserSerializer


@method_decorator(csrf_exempt, name="dispatch")
class APIRegisterView(APIView):
    """API регистрации пользователя"""

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = request.data.get("email")

        # Rate limiting по email
        limiter = RateLimiters.register()
        allowed, remaining, retry_after = limiter.check(email)

        if not allowed:
            return Response(
                {
                    "error": f"Too many registration attempts. Please try again in {retry_after} seconds.",
                    "retry_after": retry_after,
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            send_verification_email(user, request)
            refresh = RefreshToken.for_user(user)
            return Response(
                {
                    "user": UserSerializer(user).data,
                    "refresh": str(refresh),
                    "access": str(refresh.access_token),
                    "message": "Пожалуйста, подтвердите email",
                },
                status=status.HTTP_201_CREATED,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class APILoginView(TokenObtainPairView):
    def post(self, request, *args, **kwargs):
        email = request.data.get("email")

        # Rate limiting по email для логина
        limiter = RateLimiters.login()
        allowed, remaining, retry_after = limiter.check(email)

        if not allowed:
            return Response(
                {
                    "error": f"Too many login attempts. Please try again in {retry_after} seconds.",
                    "retry_after": retry_after,
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        serializer = self.get_serializer(data=request.data)

        try:
            serializer.is_valid(raise_exception=True)
            user = serializer.user

            # Проверка верификации email
            if not user.is_email_verified:
                raise exceptions.AuthenticationFailed("Email не подтверждён")

        except exceptions.AuthenticationFailed as e:
            return Response({"error": str(e)}, status=status.HTTP_401_UNAUTHORIZED)

        return Response(serializer.validated_data, status=status.HTTP_200_OK)


@method_decorator(csrf_exempt, name="dispatch")
class APILogoutView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        try:
            refresh_token = request.data.get("refresh")
            token = RefreshToken(refresh_token)
            token.blacklist()
            return Response(status=status.HTTP_205_RESET_CONTENT)
        except Exception:
            return Response(status=status.HTTP_400_BAD_REQUEST)


@method_decorator(csrf_exempt, name="dispatch")
class APIUserProfileView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        limiter = RateLimiters.api_general()
        allowed, remaining, retry_after = limiter.check(f"user_{request.user.id}_profile")

        if not allowed:
            return Response(
                {"error": f"Too many requests. Please try again in {retry_after} seconds."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        serializer = UserSerializer(request.user)
        return Response(serializer.data)
