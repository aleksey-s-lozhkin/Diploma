import logging

from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import exceptions, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from documents.rate_limit import RateLimiters
from users.email_utils import send_verification_email
from users.serializers import RegisterSerializer, UserSerializer

logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name="dispatch")
class APIRegisterView(APIView):
    """API регистрации пользователя"""

    permission_classes = [permissions.AllowAny]

    @extend_schema(
        tags=["user"],
        description="Регистрация нового пользователя",
        request={
            "application/json": {
                "type": "object",
                "required": ["email", "password", "password2"],
                "properties": {
                    "email": {
                        "type": "string",
                        "format": "email",
                        "description": "Email пользователя",
                        "example": "user@example.com",
                    },
                    "password": {
                        "type": "string",
                        "format": "password",
                        "description": "Пароль (минимум 8 символов)",
                        "example": "StrongPass123!",
                    },
                    "password2": {
                        "type": "string",
                        "format": "password",
                        "description": "Подтверждение пароля",
                        "example": "StrongPass123!",
                    },
                    "first_name": {"type": "string", "description": "Имя (опционально)", "example": "Иван"},
                    "last_name": {"type": "string", "description": "Фамилия (опционально)", "example": "Иванов"},
                },
            }
        },
        responses={
            201: OpenApiResponse(description="Пользователь создан, отправлено письмо с подтверждением"),
            400: OpenApiResponse(description="Ошибка валидации"),
            429: OpenApiResponse(description="Too many registration attempts (3 per hour)"),
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
    @extend_schema(
        tags=["user"],
        description="Авторизация пользователя (возвращает JWT токены)",
        request={
            "application/json": {
                "type": "object",
                "required": ["email", "password"],
                "properties": {
                    "email": {
                        "type": "string",
                        "format": "email",
                        "description": "Email пользователя",
                        "example": "user@example.com",
                    },
                    "password": {
                        "type": "string",
                        "format": "password",
                        "description": "Пароль",
                        "example": "StrongPass123!",
                    },
                },
            }
        },
        responses={
            200: OpenApiResponse(description="Успешный вход, возвращены токены"),
            401: OpenApiResponse(description="Неверный email, пароль или email не подтверждён"),
            429: OpenApiResponse(description="Too many login attempts (10 per 5 minutes)"),
        },
    )
    def post(self, request, *args, **kwargs):
        email = request.data.get("email")

        # Rate limiting
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

        return Response(
            {
                "refresh": str(serializer.validated_data.get("refresh")),
                "access": str(serializer.validated_data.get("access")),
            },
            status=status.HTTP_200_OK,
        )


@method_decorator(csrf_exempt, name="dispatch")
class APILogoutView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        tags=["user"],
        description="Выход из системы (blacklist refresh токена)",
        request={
            "application/json": {
                "type": "object",
                "required": ["refresh"],
                "properties": {
                    "refresh": {
                        "type": "string",
                        "description": "Refresh токен (полученный при логине)",
                        "example": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                    },
                },
            }
        },
        responses={
            205: OpenApiResponse(description="Токен успешно добавлен в blacklist"),
            400: OpenApiResponse(description="Refresh token required или Invalid token"),
        },
    )
    def post(self, request):
        try:
            refresh_token = request.data.get("refresh")
            token = RefreshToken(refresh_token)
            token.blacklist()
            return Response(status=status.HTTP_205_RESET_CONTENT)
        except Exception as e:
            logger.warning(f"Logout failed: {e}")
            return Response({"error": "Invalid or expired token"}, status=status.HTTP_400_BAD_REQUEST)


@method_decorator(csrf_exempt, name="dispatch")
class APIUserProfileView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["user"],
        description="Получить профиль текущего пользователя",
        parameters=[
            OpenApiParameter(
                name="Authorization",
                location="header",
                description="Bearer JWT токен (например: Bearer eyJhbGciOiJIUzI1NiIs...)",
                type=str,
                required=True,
            ),
        ],
        responses={
            200: OpenApiResponse(description="Профиль пользователя", response=UserSerializer),
            401: OpenApiResponse(description="Не авторизован"),
            429: OpenApiResponse(description="Too many requests (100 per minute)"),
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


class APITokenRefreshView(APIView):
    """Обновление access токена"""

    permission_classes = [permissions.AllowAny]

    @extend_schema(
        tags=["user"],
        description="Обновление access токена по refresh токену",
        request={
            "application/json": {
                "type": "object",
                "required": ["refresh"],
                "properties": {
                    "refresh": {
                        "type": "string",
                        "description": "Refresh токен (полученный при логине)",
                        "example": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                    },
                },
            }
        },
        responses={
            200: OpenApiResponse(description="Новый access токен"),
            400: OpenApiResponse(description="Refresh token required или Invalid token"),
            401: OpenApiResponse(description="Не авторизован"),
        },
    )
    def post(self, request):
        refresh_token = request.data.get("refresh")

        if not refresh_token:
            return Response({"error": "Refresh token required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            refresh = RefreshToken(refresh_token)
            return Response(
                {
                    "access": str(refresh.access_token),
                },
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            logger.warning(f"Token refresh failed: {e}")
            return Response({"error": "Invalid or expired refresh token"}, status=status.HTTP_401_UNAUTHORIZED)


class APITokenVerifyView(APIView):
    """Проверка валидности access токена"""

    permission_classes = [permissions.AllowAny]

    @extend_schema(
        tags=["user"],
        description="Проверка валидности access токена",
        request={
            "application/json": {
                "type": "object",
                "required": ["token"],
                "properties": {
                    "token": {
                        "type": "string",
                        "description": "Access токен для проверки",
                        "example": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                    },
                },
            }
        },
        responses={
            200: OpenApiResponse(description="Токен валиден"),
            401: OpenApiResponse(description="Токен не валиден"),
        },
    )
    def post(self, request):
        token = request.data.get("token")

        if not token:
            return Response({"valid": False, "error": "Token required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            AccessToken(token)
            return Response({"valid": True}, status=status.HTTP_200_OK)
        except (InvalidToken, TokenError) as e:
            logger.warning(f"Token verify failed: {e}")
            return Response({"valid": False, "error": "Invalid or expired token"}, status=status.HTTP_401_UNAUTHORIZED)
