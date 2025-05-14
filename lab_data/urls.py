from django.urls import path
from . import views



urlpatterns = [
   # path('simexp/<int:user_id>/', views.run_simulation, name='run_simulation'),
   path('', views.home_view, name='home'),
    path('login/', views.LoginChoiceView.as_view(), name='login_choice'),
    path('login/student/', views.StudentLoginView.as_view(), name='student_login'),
    path('login/teacher/', views.TeacherLoginView.as_view(), name='teacher_login'),
        path('home/', views.home_view, name='home'),  # Добавляем URL для домашней страницы
        path('group/<str:group_name>/', views.group_students_view, name='group_students'),
        path('download-manual/', views.DownloadManualView.as_view(), name='download_manual'),
    path('experiment/results/<int:experiment_id>/', views.experiment_results, name='experiment_results'),
    path('retry_experiment/<int:experiment_id>', views.retry_experiment, name='retry_experiment'),
    path('download-protocol/<int:experiment_id>/', views.download_protocol, name='download_protocol'),

    path('assistant/start-experiment/', views.assistant_start_experiment, name='assistant_start_experiment'),
    path('assistant/add-stage/<int:experiment_id>/', views.add_experiment_stage, name='add_experiment_stage'),
    path('api/save-experiment/<int:experiment_id>/', views.save_experiment_results, name='save_results'),
path('assistant/dashboard/', views.assistant_dashboard, name='assistant_dashboard'),
path('assistant/', views.assistant_dashboard, name='assistant_home'),  # Специально для лаборантов  
path('assistant/start-experiment/', views.assistant_start_experiment, name='start_experiment'),
    path('login/assistant/', views.AssistantLoginView.as_view(), name='assistant_login'),
    path('api/student-experiments/', views.get_student_experiments, name='student_experiments'),
    path('api/upload-data/<int:experiment_id>/', views.upload_experiment_data, name='upload_data'),

 path('experiment/control/<int:experiment_id>/', views.experiment_control_view, name='experiment_control'),
    path('api/experiment/<int:experiment_id>/save-params/', views.save_experiment_params, name='save_experiment_params'),
    path('api/experiment/<int:experiment_id>/complete/', views.complete_experiment, name='complete_experiment'),
    path('api/experiment/<int:experiment_id>/save-results/', views.save_experiment_results, name='save_experiment_results'),
    path('api/experiment/<int:experiment_id>/student-data/', views.get_experiment_details_for_student, name='get_experiment_details_for_student'),
    path('api/get_experiment_details_for_student/<int:experiment_id>/', views.get_experiment_details_for_student, name='get_experiment_details_for_student'),
    path('experiment/<int:experiment_id>/', views.student_experiment_detail_view, name='student_experiment_detail_view'),
]