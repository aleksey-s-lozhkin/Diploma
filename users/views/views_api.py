from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import exceptions, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from documents.rate_limit import RateLimiters

from ..email_utils import send_verification_email
from ..serializers import RegisterSerializer, UserSerializer


@method_decorator(csrf_exempt, name="dispatch")
class APIRegisterView(APIView):
    """API регистрации пользователя"""

    permission_classes = [permissions.AllowAny]

    @swagger_auto_schema(
        tags=["user"],
        operation_description="Регистрация нового пользователя",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["email", "password", "password2"],
            properties={
                "email": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    format="email",
                    description="Email пользователя",
                    example="user@example.com",
                ),
                "password": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    format="password",
                    description="Пароль (минимум 8 символов)",
                    example="StrongPass123!",
                ),
                "password2": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    format="password",
                    description="Подтверждение пароля",
                    example="StrongPass123!",
                ),
                "first_name": openapi.Schema(type=openapi.TYPE_STRING, description="Имя (опционально)", example="Иван"),
                "last_name": openapi.Schema(
                    type=openapi.TYPE_STRING, description="Фамилия (опционально)", example="Иванов"
                ),
            },
        ),
        responses={
            201: "Пользователь создан, отправлено письмо с подтверждением",
            400: "Ошибка валидации",
            429: "Too many registration attempts (3 per hour)",
        },
    )
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
    @swagger_auto_schema(
        tags=["user"],
        operation_description="Авторизация пользователя (возвращает JWT токены)",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["email", "password"],
            properties={
                "email": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    format="email",
                    description="Email пользователя",
                    example="user@example.com",
                ),
                "password": openapi.Schema(
                    type=openapi.TYPE_STRING, format="password", description="Пароль", example="StrongPass123!"
                ),
            },
        ),
        responses={
            200: "Успешный вход, возвращены токены",
            401: "Неверный email, пароль или email не подтверждён",
            429: "Too many login attempts (10 per 5 minutes)",
        },
    )
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

    @swagger_auto_schema(
        tags=["user"],
        operation_description="Выход из системы (blacklist refresh токена)",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["refresh"],
            properties={
                "refresh": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="Refresh токен (полученный при логине)",
                    example="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                ),
            },
        ),
        responses={
            205: "Токен успешно добавлен в blacklist",
            400: "Refresh token required или Invalid token",
        },
    )
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

    @swagger_auto_schema(
        tags=["user"],
        operation_description="Получить профиль текущего пользователя",
        manual_parameters=[
            openapi.Parameter(
                "Authorization",
                openapi.IN_HEADER,
                description="Bearer JWT токен (например: Bearer eyJhbGciOiJIUzI1NiIs...)",
                type=openapi.TYPE_STRING,
                required=True,
                default="Bearer ",
            ),
        ],
        responses={
            200: UserSerializer,
            401: "Не авторизован",
            429: "Too many requests (100 per minute)",
        },
    )
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
