import os
import django

# Установите переменную окружения DJANGO_SETTINGS_MODULE и вызовите django.setup()
# ДО импорта модулей, которые могут зависеть от настроек Django.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'autolab.settings')
django.setup()

# Теперь можно импортировать остальное
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from audio_processing.routing import websocket_urlpatterns

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AuthMiddlewareStack(
        URLRouter(
            websocket_urlpatterns
        )
    ),
})