import logging

from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.cache import never_cache
from django_htmx.http import HttpResponseClientRedirect, HttpResponseClientRefresh
from elasticsearch.exceptions import NotFoundError, TransportError

from documents.constants import (
    MAX_TEXT_LENGTH,
    MIN_EXTRACTED_CHARS,
    DocumentValidationError,
    normalize_rubrics,
    parse_positive_int,
    validate_uploaded_file,
)
from documents.models import Document, SearchHistory
from documents.rate_limit import RateLimiters
from documents.rubrics import get_cached_rubrics
from documents.services.search_service import SearchService
from documents.utils import extract_text_from_file

logger = logging.getLogger(__name__)


class LogoutView(View):
    def get(self, request):
        logout(request)
        return redirect("index")


@method_decorator(never_cache, name="dispatch")
@method_decorator(login_required, name="dispatch")
class IndexView(View):
    """Главная страница.

    Кэшируется не страница целиком, а список рубрик: cache_page без
    vary_on_cookie отдавал пользователю разметку, собранную для другого.
    """

    def get(self, request):
        return render(request, "index.html", {"rubrics": get_cached_rubrics(request.user)})


@method_decorator(never_cache, name="dispatch")
@method_decorator(login_required, name="dispatch")
class SearchResultsView(View):
    def post(self, request):
        user_id = request.user.id

        # Обработка сброса фильтров
        if request.POST.get("reset") == "true":
            return render(
                request,
                "partials/search_results.html",
                {
                    "reset": True,
                },
            )

        query = request.POST.get("query", "").strip()
        rubric = request.POST.get("rubric", "")
        privacy = request.POST.get("privacy", "all")
        page = parse_positive_int(request.POST.get("page", 1))
        sort_by = request.POST.get("sort", "relevance")

        # Пустой запрос - показываем подсказку
        if not query:
            return render(
                request,
                "partials/search_results.html",
                {
                    "empty_query": True,
                },
            )

        limiter = RateLimiters.api_search()
        allowed, remaining, retry_after = limiter.check(f"user_{user_id}")

        if not allowed:
            return render(
                request,
                "partials/search_results.html",
                {
                    "results": [],
                    "query": query,
                    "error": f"⏱️ Слишком много запросов. Подождите {retry_after} секунд.",
                },
            )

        try:
            # Используем сервис поиска. Сортировка передаётся в Elasticsearch:
            # сортировка списка результатов в Python упорядочивала только
            # текущую страницу, а не весь найденный набор.
            service = SearchService(request.user)
            search_response = service.search(
                query=query,
                rubric=rubric,
                privacy=privacy,
                page=page,
                save_history=True,
                with_highlights=True,
                with_truncation=False,
                sort=sort_by,
            )

            results_list = [r.to_dict() for r in search_response.results]

            # Имя файла и ссылка на него: по отрывку не понять, из какого он
            # документа, а «открыть оригинал» — первое, что нужно после находки.
            document_ids = [item.get("id") for item in results_list if item.get("id")]
            files = {
                document.pk: (document.file_name, document.file.url if document.file else "")
                for document in Document.objects.filter(pk__in=document_ids)
            }
            for item in results_list:
                item["file_name"], item["file_url"] = files.get(item.get("id"), ("", ""))

            # Получаем page_range для пагинации
            total_pages = search_response.total_pages
            current_page = page

            if total_pages <= 7:
                page_range = list(range(1, total_pages + 1))
            else:
                if current_page <= 4:
                    page_range = [1, 2, 3, 4, 5, "...", total_pages - 1, total_pages]
                elif current_page >= total_pages - 3:
                    page_range = [
                        1,
                        2,
                        "...",
                        total_pages - 4,
                        total_pages - 3,
                        total_pages - 2,
                        total_pages - 1,
                        total_pages,
                    ]
                else:
                    page_range = [1, "...", current_page - 1, current_page, current_page + 1, "...", total_pages]

            return render(
                request,
                "partials/search_results.html",
                {
                    "results": results_list,
                    "query": query,
                    "page": page,
                    "total_pages": total_pages,
                    "total": search_response.total,
                    "rubric": rubric,
                    "privacy": privacy,
                    "page_range": page_range,
                    "sort": sort_by,
                },
            )
        except TransportError as e:
            # Любая ошибка Elasticsearch: недоступен, отказал в доступе, не нашёл
            # индекс, ответил 429. Раньше ловились только ConnectionError и
            # NotFoundError, а остальные — например 401 при включённой
            # безопасности — давали 500.
            if isinstance(e, NotFoundError):
                logger.error("Индекс 'documents' не найден: %s", e)
                message = "⚙️ Ошибка конфигурации поиска. Администратор уже уведомлён."
            else:
                logger.warning("Elasticsearch недоступен для пользователя %s: %s", user_id, e)
                message = "🔍 Поиск временно недоступен. Пожалуйста, попробуйте позже."

            return render(
                request,
                "partials/search_results.html",
                {
                    "results": [],
                    "query": query,
                    "error": message,
                },
            )

        except Exception as e:
            logger.exception(f"Unexpected search error for user {user_id}: {e}")
            return render(
                request,
                "partials/search_results.html",
                {
                    "results": [],
                    "query": query,
                    "error": "❌ Произошла внутренняя ошибка. Мы уже работаем над этим.",
                },
            )


@method_decorator(never_cache, name="dispatch")
@method_decorator(login_required, name="dispatch")
class DashboardView(View):
    def get(self, request):
        show_public = request.GET.get("show_public") == "true"
        page = parse_positive_int(request.GET.get("page", 1))
        page_size = 6

        if show_public:
            documents_list = Document.objects.filter(Q(user=request.user) | Q(is_public=True)).order_by("-created_date")
        else:
            documents_list = Document.objects.filter(user=request.user).order_by("-created_date")

        paginator = Paginator(documents_list, page_size)
        documents = paginator.get_page(page)

        # Скан без текстового слоя не должен выглядеть как исправный документ:
        # человек видит «текст не извлёкся», а не пустоту вместо описания.
        for document in documents:
            document.no_text_layer = bool(document.file) and len((document.text or "").strip()) < MIN_EXTRACTED_CHARS

        total_searches = SearchHistory.objects.filter(user=request.user).count()

        # Фильтры и страницы подменяют только список. Если на такой запрос
        # отдать всю страницу, она вложится в свой же контейнер: на экране
        # появятся вторые шапка, логотип и подвал.
        template = "partials/dashboard_content.html" if getattr(request, "htmx", False) else "dashboard.html"

        return render(
            request,
            template,
            {
                "documents": documents,
                "total_searches": total_searches,
                "public_count": Document.objects.filter(user=request.user, is_public=True).count(),
                "show_public": show_public,
                "page": page,
                "total_pages": paginator.num_pages,
            },
        )


@method_decorator(login_required, name="dispatch")
class DocumentCreateView(View):
    def get(self, request):
        return render(
            request,
            "document_form.html",
            {
                "is_edit": False,
                "rubrics_value": "",
                "text_value": "",
                "text_source": "manual",
                "is_file_uploaded": False,
            },
        )

    def post(self, request):
        limiter = RateLimiters.api_general()
        allowed, remaining, retry_after = limiter.check(f"user_{request.user.id}_create")

        if not allowed:
            messages.error(request, f"Слишком много действий. Подождите {retry_after} секунд.")
            return redirect("dashboard")

        rubrics_str = request.POST.get("rubrics", "")
        raw_text = request.POST.get("text", "").strip()
        is_public = request.POST.get("is_public") == "on"
        uploaded_file = request.FILES.get("file")

        def form_error(message):
            """Возвращает форму с сохранённым вводом и сообщением об ошибке."""
            messages.error(request, message)
            return render(
                request,
                "document_form.html",
                {
                    "is_edit": False,
                    "rubrics_value": rubrics_str,
                    "text_value": raw_text,
                    "text_source": "file" if uploaded_file else "manual",
                    "is_file_uploaded": bool(uploaded_file),
                },
            )

        try:
            rubrics = normalize_rubrics(rubrics_str)
        except DocumentValidationError as exc:
            return form_error(str(exc))

        if len(raw_text) > MAX_TEXT_LENGTH:
            return form_error(f"Текст слишком длинный (максимум {MAX_TEXT_LENGTH} символов)")

        if uploaded_file:
            try:
                file_type = validate_uploaded_file(uploaded_file)
            except DocumentValidationError as exc:
                return form_error(str(exc))

            # Текст читается из загруженного файла до сохранения: документ
            # записывается один раз, а не дважды, и не зависит от того, по
            # какому пути оказался файл в MEDIA_ROOT.
            extracted_text = extract_text_from_file(uploaded_file, file_type)
            Document.objects.create(
                user=request.user,
                rubrics=rubrics,
                text=extracted_text,
                is_public=is_public,
                file=uploaded_file,
                file_name=uploaded_file.name,
                file_type=file_type,
                text_source="file",
            )
            if not extracted_text:
                messages.warning(
                    request,
                    "Текст из файла извлечь не удалось — документ сохранён без содержимого",
                )
        else:
            Document.objects.create(
                user=request.user,
                rubrics=rubrics,
                text=raw_text,
                is_public=is_public,
                file=None,
                file_name="",
                file_type="",
                text_source="manual",
            )

        messages.success(request, "Документ успешно создан")
        if request.htmx:
            response = HttpResponseClientRedirect("/dashboard/")
            response["HX-Trigger"] = "rubricsUpdated"
            return response
        return redirect("dashboard")


@method_decorator(login_required, name="dispatch")
class DocumentDeleteView(View):
    def delete(self, request, pk):
        doc = get_object_or_404(Document, pk=pk, user=request.user)
        # Файл сам по себе не удаляется вместе со строкой: без этого каталог
        # media копил бы осиротевшие документы, недоступные из интерфейса.
        if doc.file:
            doc.file.delete(save=False)
        doc.delete()
        messages.success(request, f"Документ #{pk} удалён")
        return HttpResponseClientRefresh()


@method_decorator(never_cache, name="dispatch")
@method_decorator(login_required, name="dispatch")
class SearchHistoryView(View):
    def get(self, request):
        page = parse_positive_int(request.GET.get("page", 1))
        page_size = 20

        history_list = SearchHistory.objects.filter(user=request.user).order_by("-created_at")
        paginator = Paginator(history_list, page_size)
        history = paginator.get_page(page)

        # Подпись дня считается здесь, а не в шаблоне: «вчера» и «на этой неделе»
        # зависят от сегодняшней даты, а шаблон её не знает. Список приходит
        # упорядоченным по убыванию, поэтому одинаковые подписи идут подряд — по
        # ним шаблон и группирует.
        today = timezone.localdate()
        for item in history:
            day = timezone.localtime(item.created_at).date()
            days_ago = (today - day).days
            if days_ago == 0:
                item.day_label = "Сегодня"
            elif days_ago == 1:
                item.day_label = "Вчера"
            elif days_ago < 7:
                item.day_label = "На этой неделе"
            else:
                item.day_label = day.strftime("%d.%m.%Y")

        return render(
            request,
            "search_history.html",
            {
                "history": history,
                "page": page,
                "total_pages": paginator.num_pages,
            },
        )


@method_decorator(login_required, name="dispatch")
class ClearHistoryView(View):
    def post(self, request):
        SearchHistory.objects.filter(user=request.user).delete()
        messages.success(request, "История поиска очищена")
        return redirect("search_history")


@method_decorator(never_cache, name="dispatch")
@method_decorator(login_required, name="dispatch")
class DocumentDetailView(View):
    def get(self, request, pk):
        doc = get_object_or_404(Document, Q(user=request.user) | Q(is_public=True), pk=pk)
        return render(request, "document_detail.html", {"doc": doc})


@method_decorator(login_required, name="dispatch")
class DeleteHistoryItemView(View):
    def post(self, request, pk):
        history = get_object_or_404(SearchHistory, pk=pk, user=request.user)
        history.delete()
        return JsonResponse({"status": "ok"})


@method_decorator(login_required, name="dispatch")
class TogglePublicView(View):
    def post(self, request, pk):
        doc = get_object_or_404(Document, pk=pk, user=request.user)
        doc.is_public = not doc.is_public
        doc.save()
        messages.success(request, f"Статус документа #{doc.id} изменён")
        return redirect(request.META.get("HTTP_REFERER", "dashboard"))


@method_decorator(login_required, name="dispatch")
class GetRubricsView(View):
    def get(self, request):
        return render(request, "partials/rubrics_select.html", {"rubrics": get_cached_rubrics(request.user)})
