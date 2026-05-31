import logging
import os

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.cache import cache_page, never_cache
from django.views.decorators.vary import vary_on_cookie
from django_htmx.http import HttpResponseClientRedirect, HttpResponseClientRefresh
from elasticsearch.exceptions import ConnectionError, NotFoundError

from documents.models import Document, SearchHistory
from documents.rate_limit import RateLimiters
from documents.services.search_service import SearchService
from documents.utils import extract_text_from_file

logger = logging.getLogger(__name__)

MAX_TEXT_LENGTH = 100000


class LogoutView(View):
    def get(self, request):
        logout(request)
        return redirect("index")


@method_decorator(cache_page(60 * 2), name="dispatch")
@method_decorator(vary_on_cookie, name="dispatch")
@method_decorator(login_required, name="dispatch")
class IndexView(View):
    def get(self, request):
        rubrics = Document.objects.filter(Q(user=request.user) | Q(is_public=True)).values_list("rubrics", flat=True)
        unique_rubrics = set()
        for rubrics_list in rubrics:
            for rubric in rubrics_list:
                unique_rubrics.add(rubric)
        return render(request, "index.html", {"rubrics": sorted(unique_rubrics)})


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
        page = int(request.POST.get("page", 1))
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
            # Используем сервис поиска
            service = SearchService(request.user)
            search_response = service.search(
                query=query,
                rubric=rubric,
                privacy=privacy,
                page=page,
                save_history=True,
                with_highlights=True,
                with_truncation=False,
            )

            results_list = [r.to_dict() for r in search_response.results]

            if sort_by == "date":
                results_list.sort(key=lambda x: x.get("created_date", ""), reverse=True)
            elif sort_by == "date_asc":
                results_list.sort(key=lambda x: x.get("created_date", ""))

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
        except ConnectionError as e:
            logger.warning(f"Elasticsearch connection failed for user {user_id}: {e}")
            return render(
                request,
                "partials/search_results.html",
                {
                    "results": [],
                    "query": query,
                    "error": "🔍 Поиск временно недоступен. Пожалуйста, попробуйте позже.",
                },
            )

        except NotFoundError as e:
            logger.error(f"Elasticsearch index 'documents' not found: {e}")
            return render(
                request,
                "partials/search_results.html",
                {
                    "results": [],
                    "query": query,
                    "error": "⚙️ Ошибка конфигурации поиска. Администратор уже уведомлён.",
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
        page = int(request.GET.get("page", 1))
        page_size = 6

        if show_public:
            documents_list = Document.objects.filter(Q(user=request.user) | Q(is_public=True)).order_by("-created_date")
        else:
            documents_list = Document.objects.filter(user=request.user).order_by("-created_date")

        paginator = Paginator(documents_list, page_size)
        documents = paginator.get_page(page)

        total_searches = SearchHistory.objects.filter(user=request.user).count()

        return render(
            request,
            "dashboard.html",
            {
                "documents": documents,
                "total_searches": total_searches,
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
        rubrics = [r.strip() for r in rubrics_str.split(",") if r.strip()]

        # Проверка количества рубрик
        if len(rubrics) > 10:
            messages.error(request, "Не более 10 рубрик")
            return render(
                request,
                "document_form.html",
                {
                    "is_edit": False,
                    "rubrics_value": rubrics_str,
                    "text_value": request.POST.get("text", ""),
                    "text_source": request.POST.get("text_source", "manual"),
                    "is_file_uploaded": bool(request.FILES.get("file")),
                },
            )

        # Проверка длины каждой рубрики
        for rubric in rubrics:
            if len(rubric) > 100:
                messages.error(request, f"Рубрика '{rubric[:50]}...' слишком длинная. Максимум 100 символов.")
                return render(
                    request,
                    "document_form.html",
                    {
                        "is_edit": False,
                        "rubrics_value": rubrics_str,
                        "text_value": request.POST.get("text", ""),
                        "text_source": request.POST.get("text_source", "manual"),
                        "is_file_uploaded": bool(request.FILES.get("file")),
                    },
                )

        raw_text = request.POST.get("text", "").strip()
        is_public = request.POST.get("is_public") == "on"

        if len(raw_text) > MAX_TEXT_LENGTH:
            messages.error(request, f"Текст слишком длинный (максимум {MAX_TEXT_LENGTH} символов)")
            return render(request, "document_form.html", {"form": request.POST})

        text_source = "manual"
        uploaded_file = request.FILES.get("file")

        if uploaded_file:
            file_name = uploaded_file.name
            file_type = file_name.split(".")[-1].lower()
            text_source = "file"

            doc = Document.objects.create(
                user=request.user,
                rubrics=rubrics,
                text="",
                is_public=is_public,
                file=uploaded_file,
                file_name=file_name,
                file_type=file_type,
                text_source=text_source,
            )

            file_path = os.path.join(settings.MEDIA_ROOT, doc.file.name)
            extracted_text = extract_text_from_file(file_path, file_type)
            doc.text = extracted_text
            doc.save()

            messages.success(request, "Документ успешно создан")
            if request.htmx:
                response = HttpResponseClientRedirect("/dashboard/")
                response["HX-Trigger"] = "rubricsUpdated"
                return response
            return redirect("dashboard")

        Document.objects.create(
            user=request.user,
            rubrics=rubrics,
            text=raw_text,
            is_public=is_public,
            file=None,
            file_name="",
            file_type="",
            text_source=text_source,
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
        doc.delete()
        messages.success(request, f"Документ #{pk} удалён")
        return HttpResponseClientRefresh()


@method_decorator(never_cache, name="dispatch")
@method_decorator(login_required, name="dispatch")
class SearchHistoryView(View):
    def get(self, request):
        page = int(request.GET.get("page", 1))
        page_size = 20

        history_list = SearchHistory.objects.filter(user=request.user).order_by("-created_at")
        paginator = Paginator(history_list, page_size)
        history = paginator.get_page(page)

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


@method_decorator(cache_page(60 * 60), name="dispatch")
@method_decorator(login_required, name="dispatch")
class GetRubricsView(View):
    def get(self, request):
        rubrics = Document.objects.filter(Q(user=request.user) | Q(is_public=True)).values_list("rubrics", flat=True)
        unique_rubrics = set()
        for rubrics_list in rubrics:
            for rubric in rubrics_list:
                unique_rubrics.add(rubric)

        return render(request, "partials/rubrics_select.html", {"rubrics": sorted(unique_rubrics)})
