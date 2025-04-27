from django.urls import path
from . import views

urlpatterns = [
    path('simexp/<int:experiment_id>/', views.run_simulation, name='run_simulation'),
]