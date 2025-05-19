from django.urls import path
from . import views



urlpatterns = [
   # path('simexp/<int:user_id>/', views.run_simulation, name='run_simulation'),
   path('', views.home_view, name='home'),
    path('login/', views.LoginChoiceView.as_view(), name='login_choice'),
    path('login/student/', views.StudentLoginView.as_view(), name='student_login'),
    path('login/teacher/', views.TeacherLoginView.as_view(), name='teacher_login'),
    path('login/assistant/', views.AssistantLoginView.as_view(), name='assistant_login'),
    path('logout/', views.logout_view, name='logout'),
    path('teacher/protocol/<int:experiment_id>/', views.protocol_detail_view, name='protocol_detail'),
    path('teacher/protocol/<int:experiment_id>/download/', views.download_protocol_pdf, name='download_protocol_pdf'),
    path('group/<str:group_name>/', views.group_students_view, name='group_students'),
    path('download-manual/', views.DownloadManualView.as_view(), name='download_manual'),
    path('assistant/dashboard/', views.assistant_dashboard, name='assistant_dashboard'),
    path('assistant/start-experiment/', views.assistant_start_experiment, name='assistant_start_experiment'),
    path('experiment/results/<int:experiment_id>/', views.experiment_results, name='experiment_results'),
    path('retry_experiment/<int:experiment_id>/', views.retry_experiment, name='retry_experiment'),
    path('experiment/control/<int:experiment_id>/', views.experiment_control_view, name='experiment_control'),
    path('experiment/<int:experiment_id>/', views.student_experiment_detail_view, name='student_experiment_detail_view'),
    path('api/student-experiments/', views.get_student_experiments, name='student_experiments'),
    path('api/experiment/<int:experiment_id>/save-params/', views.save_experiment_params, name='save_experiment_params'),
    path('api/experiment/<int:experiment_id>/complete/', views.complete_experiment, name='complete_experiment'),
    path('api/experiment/<int:experiment_id>/save-results/', views.save_experiment_results, name='save_experiment_results'),
    path('api/experiment/<int:experiment_id>/student-data/', views.get_experiment_details_for_student, name='get_experiment_details_for_student'),
    path('api/experiment/<int:experiment_id>/upload-data/', views.upload_experiment_data, name='upload_experiment_data_api'),
]