from .views_api import DocumentViewSet, SearchView, health_check
from .views_web import (
    ClearHistoryView,
    DashboardView,
    DeleteHistoryItemView,
    DocumentCreateView,
    DocumentDeleteView,
    DocumentDetailView,
    GetRubricsView,
    IndexView,
    LogoutView,
    SearchHistoryView,
    SearchResultsView,
    TogglePublicView,
)

__all__ = [
    # API views
    "DocumentViewSet",
    "SearchView",
    "health_check",
    # Web views
    "IndexView",
    "DashboardView",
    "SearchResultsView",
    "SearchHistoryView",
    "ClearHistoryView",
    "DocumentCreateView",
    "DocumentDeleteView",
    "DocumentDetailView",
    "DeleteHistoryItemView",
    "TogglePublicView",
    "GetRubricsView",
    "LogoutView",
]
