from .urls_api import urlpatterns as api_urlpatterns
from .urls_web import urlpatterns as web_urlpatterns

urlpatterns = api_urlpatterns + web_urlpatterns
