from django.urls import path
from . import views



urlpatterns = [
   # path('simexp/<int:user_id>/', views.run_simulation, name='run_simulation'),
    path('login/', views.LoginChoiceView.as_view(), name='login_choice'),
    path('login/student/', views.StudentLoginView.as_view(), name='student_login'),
    path('login/teacher/', views.TeacherLoginView.as_view(), name='teacher_login'),
        path('home/', views.home_view, name='home'),  # Добавляем URL для домашней страницы
        path('group/<str:group_name>/', views.group_students_view, name='group_students'),
        path('download-manual/', views.DownloadManualView.as_view(), name='download_manual'),
         path('experiment/start/', views.start_experiment, name='start_experiment'),
    path('experiment/results/<int:experiment_id>/', views.experiment_results, name='experiment_results'),
    path('retry_experiment/<int:experiment_id>', views.retry_experiment, name='retry_experiment'),

]