from django.contrib import admin

from .models import Document, SearchHistory

admin.site.register(Document)
admin.site.register(SearchHistory)
