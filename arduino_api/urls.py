from django.urls import path
from . import views

urlpatterns = [
    path('connect/', views.connect_arduino, name='connect_arduino'),
    path('disconnect/', views.disconnect_arduino, name='disconnect_arduino'),
    path('status/', views.arduino_status, name='arduino_status'),
    path('read-distance/', views.read_distance, name='read_distance'),
] 