import os
import re

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
from elasticsearch_dsl import Search
from elasticsearch_dsl.connections import connections

from documents.models import Document, SearchHistory
from documents.rate_limit import RateLimiters
from documents.utils import extract_text_from_file

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

        limiter = RateLimiters.api_search()
        allowed, remaining, retry_after = limiter.check(f"user_{user_id}")

        if not allowed:
            return render(
                request,
                "partials/search_results.html",
                {
                    "results": [],
                    "query": request.POST.get("query", ""),
                    "error": f"⏱️ Слишком много запросов. Подождите {retry_after} секунд.",
                },
            )

        try:
            query = request.POST.get("query", "")
            rubric = request.POST.get("rubric", "")
            privacy = request.POST.get("privacy", "all")
            page = int(request.POST.get("page", 1))
            page_size = 20

            if not query:
                return render(request, "partials/search_results.html", {"results": [], "query": ""})

            connections.configure(default={"hosts": "http://elasticsearch:9200"})

            s = Search(index="documents").query(
                "bool",
                must=[{"match": {"text": query}}],
            )

            s = s.query(
                "bool",
                should=[{"term": {"user_id": request.user.id}}, {"term": {"is_public": True}}],
                minimum_should_match=1,
            )

            if rubric and rubric != "":
                s = s.query("match", rubrics=rubric)

            if privacy == "public":
                s = s.query("term", is_public=True)
            elif privacy == "private":
                s = s.query("term", user_id=request.user.id)

            start = (page - 1) * page_size
            s = s[start : start + page_size]

            response = s.execute()

            if page == 1:
                SearchHistory.objects.create(user=request.user, query=query, results_count=response.hits.total.value)

            results = []
            for hit in response:
                highlights = []
                if hasattr(hit.meta, "highlight") and "text" in hit.meta.highlight:
                    for fragment in hit.meta.highlight.text:
                        cleaned = re.sub(r"\s+", " ", fragment).strip()
                        if cleaned:
                            highlights.append(cleaned)

                results.append(
                    {
                        "id": hit.id,
                        "rubrics": hit.rubrics,
                        "text": hit.text,
                        "created_date": hit.created_date,
                        "highlights": highlights,
                        "is_public": hit.is_public,
                    }
                )

            total = response.hits.total.value
            total_pages = (total + page_size - 1) // page_size

            return render(
                request,
                "partials/search_results.html",
                {
                    "results": results,
                    "query": query,
                    "page": page,
                    "total_pages": total_pages,
                    "total": total,
                    "rubric": rubric,
                    "privacy": privacy,
                },
            )
        except Exception as e:
            return render(request, "partials/search_results.html", {"results": [], "query": query, "error": str(e)})


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
