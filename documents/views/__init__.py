from .views_api import DocumentViewSet, SearchView
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
