from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
import audio_processing.routing

application = ProtocolTypeRouter({
    "http": ...,  # Оставьте это, если используется стандартный HTTP (обычно автоматически подтягивается Django)
    "websocket": AuthMiddlewareStack(
        URLRouter(
            audio_processing.routing.websocket_urlpatterns
        )
    ),
})
