from django.urls import path
from . import consumers

websocket_urlpatterns = [
    path("ws/audio/", consumers.AudioConsumer.as_asgi()),
]