import re

import bleach
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.core.files.storage import default_storage
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.decorators import method_decorator
from django.views import View
from django_htmx.http import HttpResponseClientRefresh
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


class LoginView(View):
    def get(self, request):
        if request.user.is_authenticated:
            return redirect("dashboard")
        return render(request, "login.html")

    def post(self, request):
        if request.user.is_authenticated:
            return redirect("dashboard")

        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            return redirect("dashboard")
        messages.error(request, "Неверное имя пользователя или пароль")
        return render(request, "login.html")


class RegisterView(View):
    def get(self, request):
        if request.user.is_authenticated:
            return redirect("dashboard")
        return render(request, "register.html")

    def post(self, request):
        if request.user.is_authenticated:
            return redirect("dashboard")

        from django.contrib.auth.models import User

        username = request.POST.get("username")
        password1 = request.POST.get("password1")
        password2 = request.POST.get("password2")

        if password1 != password2:
            messages.error(request, "Пароли не совпадают")
        elif len(password1) < 8:
            messages.error(request, "Пароль должен содержать не менее 8 символов")
        elif User.objects.filter(username=username).exists():
            messages.error(request, "Пользователь с таким именем уже существует")
        else:
            user = User.objects.create_user(username=username, password=password1)
            login(request, user)
            messages.success(request, f"Добро пожаловать, {username}!")
            return redirect("dashboard")

        return render(request, "register.html")


class LogoutView(View):
    def get(self, request):
        logout(request)
        return redirect("index")


class IndexView(View):
    def get(self, request):
        return render(request, "index.html", {"user": request.user})


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

            if not query:
                return render(request, "partials/search_results.html", {"results": [], "query": ""})

            connections.configure(default={"hosts": "http://elasticsearch:9200"})
            s = Search(index="documents")
            s = s.query("match", text=query)
            s = s.filter("term", user_id=request.user.id)
            s = s.highlight(
                "text",
                fragment_size=300,
                number_of_fragments=5,
                pre_tags=["<mark>"],
                post_tags=["</mark>"],
                boundary_chars=" .,;:!?()[]{}\"' \n\t\r",
                boundary_max_scan=50,
                fragmenter="span",
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
                    }
                )

            return render(request, "partials/search_results.html", {"results": results, "query": query})
        except Exception as e:
            return render(request, "partials/search_results.html", {"results": [], "query": query, "error": str(e)})


@method_decorator(login_required, name="dispatch")
class DashboardView(View):
    def get(self, request):
        documents = Document.objects.filter(user=request.user).order_by("-created_date")
        total_searches = SearchHistory.objects.filter(user=request.user).count()
        return render(request, "dashboard.html", {"documents": documents, "total_searches": total_searches})


@method_decorator(login_required, name="dispatch")
class DocumentCreateView(View):
    def get(self, request):
        return render(request, "document_form.html", {"is_edit": False, "rubrics_value": "", "text_value": ""})

    def post(self, request):
        rubrics_str = request.POST.get("rubrics", "")
        rubrics = [r.strip() for r in rubrics_str.split(",") if r.strip()]
        html_text = request.POST.get("text", "")

        # Очищаем HTML от опасных тегов
        cleaned_text = bleach.clean(html_text, tags=ALLOWED_TAGS, strip=True)

        # Обработка загруженного файла
        uploaded_file = request.FILES.get("file")
        file_name = ""
        file_type = ""
        extracted_text = ""

        if uploaded_file:
            file_name = uploaded_file.name
            file_type = file_name.split(".")[-1].lower()

            # Сохраняем файл
            file_path = default_storage.save(f"temp/{uploaded_file.name}", uploaded_file)
            full_path = default_storage.path(file_path)

            # Извлекаем текст
            extracted_text = extract_text_from_file(full_path, file_type)

            # Удаляем временный файл
            default_storage.delete(file_path)

        # Используем HTML текст или извлечённый из файла
        final_text = cleaned_text if cleaned_text else extracted_text

        # Создаём документ
        Document.objects.create(
            user=request.user,
            rubrics=rubrics,
            text=final_text,
            file=uploaded_file if uploaded_file else None,
            file_name=file_name,
            file_type=file_type,
        )

        messages.success(request, "Документ успешно создан")
        return redirect("dashboard")


@method_decorator(login_required, name="dispatch")
class DocumentEditView(View):
    def get(self, request, pk):
        doc = get_object_or_404(Document, pk=pk, user=request.user)
        rubrics_value = ", ".join(doc.rubrics) if doc.rubrics else ""
        return render(
            request,
            "document_form.html",
            {"is_edit": True, "rubrics_value": rubrics_value, "text_value": doc.text, "doc": doc},
        )

    def post(self, request, pk):
        doc = get_object_or_404(Document, pk=pk, user=request.user)
        rubrics_str = request.POST.get("rubrics", "")
        rubrics = [r.strip() for r in rubrics_str.split(",") if r.strip()]
        html_text = request.POST.get("text", "")

        # Очищаем HTML
        cleaned_text = bleach.clean(html_text, tags=ALLOWED_TAGS, strip=True)

        doc.rubrics = rubrics
        doc.text = cleaned_text
        doc.save()

        messages.success(request, "Документ успешно обновлён")
        return redirect("dashboard")


@method_decorator(login_required, name="dispatch")
class DocumentDeleteView(View):
    def delete(self, request, pk):
        doc = get_object_or_404(Document, pk=pk, user=request.user)
        doc.delete()
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
