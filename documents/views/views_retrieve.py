"""Поиск отрывков для потребителей поиска.

Форма границы зафиксирована в docs/SEARCH-CONTRACT.md и меняется только вместе
с потребителями (Семён и лапот). Здесь — реализация этой формы: кого искать
решает токен, порог принадлежит поиску, отказ Elasticsearch — это 503, а пустой
результат — нормальный ответ 200.
"""

import logging
from collections import Counter

from drf_spectacular.utils import OpenApiResponse, extend_schema
from elasticsearch.exceptions import NotFoundError, TransportError
from elasticsearch_dsl import Q, Search
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from documents.auth import ApiTokenAuthentication, HasApiToken
from documents.models import ApiToken
from documents.serializers import RetrieveRequestSerializer, RetrieveResponseSerializer
from documents.services.chunk_service import CHUNKS_INDEX

logger = logging.getLogger(__name__)

#: Границы запроса — из контракта (§2).
MIN_QUERY_LENGTH = 3
MAX_QUERY_LENGTH = 1000
DEFAULT_LIMIT = 10
MAX_LIMIT = 50

#: Не больше трёх отрывков одного документа в выдаче: иначе один документ
#: займёт весь ответ (контракт, §6).
MAX_CHUNKS_PER_DOCUMENT = 3

#: Сколько кусков запрашивать у Elasticsearch, чтобы после отсечения по
#: документу и по лимиту осталось нужное количество.
FETCH_FACTOR = 4

#: Порог отсечения по близости. Пока векторной части нет, а у BM25 нет
#: абсолютной шкалы: ноль уже означает «совпадений нет». Порог применяется
#: здесь, а не у потребителя, потому что измерять и настраивать его должен
#: поиск (контракт, §5).
VECTOR_MIN_SCORE = None


class RetrieveView(APIView):
    """POST /api/v1/search/retrieve — отрывки документов для потребителей."""

    authentication_classes = [ApiTokenAuthentication]
    permission_classes = [HasApiToken]

    @extend_schema(
        summary="Поиск отрывков документов",
        description=(
            "Отдаёт отрывки документов, найденные по запросу. Кого искать — решает токен: "
            "служебный видит только публичные документы, персональный — свои и публичные. "
            "Пустой results при 200 означает «не нашлось»; 503 — поиск недоступен, и "
            "потребитель обязан сказать об этом, а не отвечать по памяти модели."
        ),
        request=RetrieveRequestSerializer,
        responses={
            200: RetrieveResponseSerializer,
            400: OpenApiResponse(description="Ошибка потребителя: запрос вне границ контракта"),
            503: OpenApiResponse(description="Поиск недоступен: Elasticsearch или индекс отрывков"),
        },
    )
    def post(self, request):
        # Идентификатор пользователя в запросе запрещён контрактом (§2): иначе
        # ошибка в любом потребителе открывала бы чужие документы. Отвечаем
        # явной ошибкой, а не молча игнорируем поле.
        if "user_id" in request.data or "user" in request.data:
            return Response(
                {"error": "Кого искать — решает токен; идентификатор пользователя в запросе не принимается"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        query = (request.data.get("query") or "").strip()
        if not MIN_QUERY_LENGTH <= len(query) <= MAX_QUERY_LENGTH:
            return Response(
                {"error": f"query: от {MIN_QUERY_LENGTH} до {MAX_QUERY_LENGTH} знаков"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            limit = int(request.data.get("limit", DEFAULT_LIMIT))
        except (TypeError, ValueError):
            return Response({"error": "limit: целое число"}, status=status.HTTP_400_BAD_REQUEST)
        if limit < 1:
            return Response({"error": "limit: не меньше единицы"}, status=status.HTTP_400_BAD_REQUEST)
        limit = min(limit, MAX_LIMIT)

        rubrics = request.data.get("rubrics") or []
        if not isinstance(rubrics, list) or any(not isinstance(rubric, str) for rubric in rubrics):
            return Response({"error": "rubrics: список строк"}, status=status.HTTP_400_BAD_REQUEST)

        search = self._build_search(request.auth, query, rubrics, limit)

        try:
            response = search.execute()
        except NotFoundError:
            # Индекс не создан — это не «ничего не нашлось», а неполадка:
            # пустой ответ читался бы как «материала нет».
            logger.error("Индекс кусков %s не создан", CHUNKS_INDEX)
            return Response(
                {"error": "Индекс отрывков не создан: нужен пересбор индекса"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except TransportError as exc:
            logger.warning("Поиск отрывков недоступен: %s", exc)
            return Response(
                {"error": "Поиск недоступен"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        results = self._collect(response, limit)
        logger.info("Поиск отрывков: «%s» → %s результатов", query, len(results))
        # Пока векторов нет, честный источник — полнотекстовый (контракт, §3).
        return Response({"results": results, "source": "fulltext"})

    @staticmethod
    def _build_search(api_token, query, rubrics, limit):
        """Запрос к индексу кусков с учётом видимости документов токена."""
        search = Search(index=CHUNKS_INDEX)

        search = search.query(
            "multi_match",
            query=query,
            # Текст весомее заголовка: заголовок часто повторяет рубрику.
            fields=["text^3", "title^2"],
            operator="and",
            fuzziness="AUTO",
            minimum_should_match="70%",
        )

        # Видимость: служебный токен — только публичные, персональный — свои и
        # публичные. Потребитель этого не выбирает, это следствие токена (§2).
        visible = [Q("term", is_public=True)]
        if api_token.scope == ApiToken.SCOPE_PERSONAL and api_token.user_id:
            visible.append(Q("term", user_id=api_token.user_id))
        search = search.query("bool", should=visible, minimum_should_match=1)

        if rubrics:
            search = search.query(
                "bool",
                should=[Q("match", rubrics=rubric) for rubric in rubrics],
                minimum_should_match=1,
            )

        if VECTOR_MIN_SCORE is not None:
            search = search.extra(min_score=VECTOR_MIN_SCORE)

        return search[: max(limit * FETCH_FACTOR, limit)]

    @staticmethod
    def _collect(response, limit) -> list:
        """Собрать ответ, не давая одному документу занять всю выдачу."""
        results = []
        per_document = Counter()

        for hit in response:
            document_id = hit.document_id
            if per_document[document_id] >= MAX_CHUNKS_PER_DOCUMENT:
                continue
            per_document[document_id] += 1

            results.append(
                {
                    "document_id": document_id,
                    "chunk_index": hit.chunk_index,
                    "chunk_total": hit.chunk_total,
                    # Ответ на §8.3 контракта: по отпечатку видно, что документ
                    # изменился и отрывок мог устареть.
                    "document_version": getattr(hit, "document_version", None),
                    "title": getattr(hit, "title", None),
                    "text": hit.text,
                    # Шкала — BM25, а не вероятность: сравнивать score разных
                    # источников нельзя, о чём сказано в docs/ARCHITECTURE.md.
                    "score": round(float(hit.meta.score or 0.0), 4),
                    "rubrics": list(hit.rubrics) if isinstance(hit.rubrics, list) else [],
                    "is_public": bool(hit.is_public),
                }
            )
            if len(results) >= limit:
                break

        return results
