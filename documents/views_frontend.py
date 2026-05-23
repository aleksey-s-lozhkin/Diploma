import os
import re

import bleach
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.decorators import method_decorator
from django.views import View
from django_htmx.http import HttpResponseClientRedirect, HttpResponseClientRefresh
from elasticsearch_dsl import Search
from elasticsearch_dsl.connections import connections

from .models import Document, SearchHistory
from .rate_limit import check_rate_limit
from .utils import extract_text_from_file

ALLOWED_TAGS = [
    "p",
    "br",
    "b",
    "i",
    "u",
    "strong",
    "em",
    "h1",
    "h2",
    "h3",
    "h4",
    "ul",
    "ol",
    "li",
    "table",
    "tr",
    "td",
    "th",
    "thead",
    "tbody",
    "a",
    "img",
    "pre",
    "code",
    "blockquote",
    "hr",
    "div",
    "span",
]


class LogoutView(View):
    def get(self, request):
        logout(request)
        return redirect("index")


@method_decorator(login_required, name="dispatch")
class IndexView(View):
    def get(self, request):
        rubrics = Document.objects.filter(Q(user=request.user) | Q(is_public=True)).values_list("rubrics", flat=True)
        unique_rubrics = set()
        for rubrics_list in rubrics:
            for rubric in rubrics_list:
                unique_rubrics.add(rubric)
        return render(request, "index.html", {"rubrics": sorted(unique_rubrics)})


@method_decorator(login_required, name="dispatch")
class SearchResultsView(View):
    def post(self, request):
        user_id = request.user.id
        is_allowed, remaining, retry_after = check_rate_limit(f"search_{user_id}", 20, 60)

        if not is_allowed:
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
            rubric = request.POST.get("rubric", "")  # Получаем выбранную рубрику
            privacy = request.POST.get("privacy", "all")

            if not query:
                return render(request, "partials/search_results.html", {"results": [], "query": ""})

            connections.configure(default={"hosts": "http://elasticsearch:9200"})

            # Базовый поиск
            s = Search(index="documents").query(
                "bool",
                must=[{"match": {"text": query}}],
                should=[{"term": {"user_id": request.user.id}}, {"term": {"is_public": True}}],
                minimum_should_match=1,
            )

            # Фильтр по рубрике (если выбрана)
            if rubric and rubric != "":
                s = s.query("term", rubrics=rubric)

            # Фильтр по приватности
            if privacy == "public":
                s = s.query("term", is_public=True)
            elif privacy == "private":
                s = s.query("term", user_id=request.user.id)

            s = s.highlight(
                "text",
                fragment_size=300,
                number_of_fragments=3,
                pre_tags=["<mark>"],
                post_tags=["</mark>"],
            )

            response = s.execute()

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

            return render(request, "partials/search_results.html", {"results": results, "query": query})
        except Exception as e:
            return render(request, "partials/search_results.html", {"results": [], "query": query, "error": str(e)})


@method_decorator(login_required, name="dispatch")
class DashboardView(View):
    def get(self, request):
        # Получаем параметр show_public (по умолчанию False - только свои)
        show_public = request.GET.get("show_public") == "true"

        if show_public:
            # Показываем свои и публичные чужие
            from django.db.models import Q

            documents = Document.objects.filter(Q(user=request.user) | Q(is_public=True)).order_by("-created_date")
        else:
            # Показываем только свои
            documents = Document.objects.filter(user=request.user).order_by("-created_date")

        total_searches = SearchHistory.objects.filter(user=request.user).count()
        return render(
            request,
            "dashboard.html",
            {"documents": documents, "total_searches": total_searches, "show_public": show_public},
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
        rubrics_str = request.POST.get("rubrics", "")
        rubrics = [r.strip() for r in rubrics_str.split(",") if r.strip()]
        raw_text = request.POST.get("text", "")
        is_public = request.POST.get("is_public") == "on"

        text_source = "manual"
        final_text = raw_text
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

        cleaned_text = bleach.clean(final_text, tags=ALLOWED_TAGS, strip=True)
        Document.objects.create(
            user=request.user,
            rubrics=rubrics,
            text=cleaned_text,
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


@method_decorator(login_required, name="dispatch")
class SearchHistoryView(View):
    def get(self, request):
        history = SearchHistory.objects.filter(user=request.user).order_by("-created_at")
        return render(request, "search_history.html", {"history": history})


@method_decorator(login_required, name="dispatch")
class ClearHistoryView(View):
    def post(self, request):
        SearchHistory.objects.filter(user=request.user).delete()
        messages.success(request, "История поиска очищена")
        return redirect("search_history")


@method_decorator(login_required, name="dispatch")
class DocumentDetailView(View):
    def get(self, request, pk):
        doc = get_object_or_404(Document, pk=pk, user=request.user)
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
