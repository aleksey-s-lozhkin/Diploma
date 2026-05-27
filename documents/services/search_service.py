import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from django.contrib.auth import get_user_model
from elasticsearch_dsl import Search

from documents.models import SearchHistory

User = get_user_model()


@dataclass
class SearchResult:
    """Контейнер для результата поиска"""

    id: int
    rubrics: List[str]
    text: str
    created_date: str
    is_public: bool
    highlights: List[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "rubrics": self.rubrics,
            "text": self.text,
            "created_date": self.created_date,
            "is_public": self.is_public,
            "highlights": self.highlights or [],
        }


@dataclass
class SearchResponse:
    """Контейнер для ответа поиска"""

    results: List[SearchResult]
    total: int
    page: int
    page_size: int
    total_pages: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "count": self.total,
            "results": [r.to_dict() for r in self.results],
            "page": self.page,
            "total_pages": self.total_pages,
            "page_size": self.page_size,
        }


class SearchService:
    """Сервис для полнотекстового поиска документов"""

    INDEX_NAME = "documents"
    DEFAULT_PAGE_SIZE = 20
    MAX_PAGE_SIZE = 100

    def __init__(self, user):
        self.user = user

    def build_query(self, query: str, rubric: Optional[str] = None, privacy: str = "all") -> Search:
        """Построение Elasticsearch запроса с фильтрацией"""

        # Базовый поиск по тексту с правами доступа
        s = Search(index=self.INDEX_NAME).query(
            "bool",
            must=[{"match": {"text": query}}],
            should=[{"term": {"user_id": self.user.id}}, {"term": {"is_public": True}}],
            minimum_should_match=1,
        )

        # Фильтр по рубрике
        if rubric and rubric.strip():
            s = s.query("match", rubrics=rubric)

        # Фильтр по приватности
        if privacy == "public":
            s = s.query("term", is_public=True)
        elif privacy == "private":
            s = s.query("term", user_id=self.user.id)
        # privacy == "all" — без дополнительных фильтров

        return s

    @staticmethod
    def extract_highlights(hit) -> List[str]:
        """Извлечение подсветок из результата поиска"""
        highlights = []
        if hasattr(hit.meta, "highlight") and "text" in hit.meta.highlight:
            for fragment in hit.meta.highlight.text:
                cleaned = re.sub(r"\s+", " ", fragment).strip()
                if cleaned:
                    highlights.append(cleaned)
        return highlights

    @staticmethod
    def format_text(text: str, max_length: int = 500) -> str:
        """Обрезает текст до указанной длины"""
        if len(text) > max_length:
            return text[:max_length] + "..."
        return text

    def search(
        self,
        query: str,
        rubric: Optional[str] = None,
        privacy: str = "all",
        page: int = 1,
        page_size: int = None,
        save_history: bool = True,
        with_highlights: bool = True,
        with_truncation: bool = True,
    ) -> SearchResponse:
        """Выполняет поиск документов"""
        if not query:
            return SearchResponse(
                results=[], total=0, page=page, page_size=page_size or self.DEFAULT_PAGE_SIZE, total_pages=0
            )

        # Настройка пагинации
        page_size = page_size or self.DEFAULT_PAGE_SIZE
        page_size = min(page_size, self.MAX_PAGE_SIZE)
        start = (page - 1) * page_size

        # Построение и выполнение запроса
        s = self.build_query(query, rubric, privacy)
        s = s[start : start + page_size]

        # Добавляем highlighting (если нужно)
        if with_highlights:
            s = s.highlight("text", fragment_size=200, number_of_fragments=3)

        response = s.execute()
        total = response.hits.total.value

        # Сохраняем историю (только первая страница)
        if save_history and page == 1 and query:
            SearchHistory.objects.create(user=self.user, query=query, results_count=total)

        # Формируем результаты
        results = []
        for hit in response:
            text = hit.text
            if with_truncation:
                text = self.format_text(text)

            result = SearchResult(
                id=hit.id,
                rubrics=list(hit.rubrics) if hit.rubrics else [],
                text=text,
                created_date=hit.created_date,
                is_public=hit.is_public,
                highlights=self.extract_highlights(hit) if with_highlights else [],
            )
            results.append(result)

        total_pages = (total + page_size - 1) // page_size if total > 0 else 0

        return SearchResponse(
            results=results,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )
