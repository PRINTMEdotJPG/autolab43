from django.http import (
    JsonResponse,
    HttpResponse,
    HttpResponseForbidden,
    Http404,
    FileResponse
)
from django.shortcuts import get_object_or_404, render, redirect
from django.contrib.auth import login as auth_login
from django.contrib import messages
from django.views import View
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.decorators.http import require_http_methods
from django.core.exceptions import PermissionDenied
from django.contrib.auth import login as authenticate
from django.contrib.auth import logout as auth_logout
from django.contrib.auth import get_user_model
from typing import Dict, Any, Optional
import json
import logging
import os
from config import config
from django.forms.models import model_to_dict
import numpy as np

from .models import User, Experiments, EquipmentData, Results
from .imitate_module.sensors_simulator import ExperimentSimulator
from .forms import StudentLoginForm, TeacherLoginForm, StudentResultForm, AssistantLoginForm
from .generate_graphs import (
    generate_gamma_frequency_graph,
    generate_interference_graph,
    generate_signal_time_graph
)
from django.template.loader import render_to_string

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm

from io import BytesIO
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from django.conf import settings



# Настройка логгера
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.FileHandler('experiment.log')
handler.setFormatter(logging.Formatter(
    '%(asctime)s - %(levelname)s - %(message)s'
))
logger.addHandler(handler)

# Глобальный флаг для переключения режима (симуляция/реальное оборудование)
USE_SIMULATION = True


@login_required
def home_view(request) -> HttpResponse:
    """
    Главная страница системы с разным контентом для студентов и преподавателей.

    Args:
        request: HttpRequest объект

    Returns:
        HttpResponse: Отрендеренный шаблон home.html с контекстом
    """
    logger.info(f"User {request.user.email} (Role: {request.user.role}) accessed home page.")
    context: Dict[str, Any] = {
        'user': request.user,
        'full_name': request.user.full_name,
        'role': request.user.get_role_display(),
    }

    if request.user.role == 'student':
        logger.info(f"Building context for student: {request.user.email}")
        try:
            experiments_query = Experiments.objects.filter(
                user=request.user
            ).select_related('assistant', 'results').order_by('-created_at')
            
            logger.info(f"Found {experiments_query.count()} raw experiments for student {request.user.email}.")

            student_experiments_data = []
            for exp in experiments_query:
                student_facing_status = 'Неизвестно'
                badge_class = 'bg-secondary' # Класс для badge по умолчанию
                results_status = exp.results.status if hasattr(exp, 'results') and exp.results else None
                exp_status_from_model = exp.status # Статус из модели Experiment

                if results_status: # Если есть статус в Results
                    if results_status == 'pending_student_input':
                        student_facing_status = 'в процессе выполнения'
                        badge_class = 'bg-primary' 
                    elif results_status == 'success' or results_status == 'final_completed':
                        student_facing_status = 'Завершен'
                        badge_class = 'bg-success'
                    elif results_status == 'fail':
                        student_facing_status = exp.results.get_status_display() # Должно быть 'Ошибка'
                        badge_class = 'bg-danger'
                    else: # Другие возможные статусы Results
                        student_facing_status = exp.results.get_status_display()
                        badge_class = 'bg-info' # Общий класс для прочих Result статусов
                elif exp_status_from_model == 'failed': # Обработка нового статуса Experiments
                    student_facing_status = exp.get_status_display() # Должно вернуть "Провальный"
                    badge_class = 'bg-danger'
                elif exp_status_from_model == 'completed':
                    student_facing_status = 'Ожидает ваших результатов'
                    badge_class = 'bg-info'
                else:
                    # Статус из модели Experiment, если нет данных в Results
                    student_facing_status = exp.get_status_display()
                    if exp_status_from_model == 'aborted':
                        badge_class = 'bg-dark'
                    elif exp_status_from_model == 'preparing' or 'stage' in exp_status_from_model:
                        badge_class = 'bg-warning'
                    else:
                        badge_class = 'bg-light text-dark'

                student_experiments_data.append({
                    'id': exp.id,
                    'created_at': exp.created_at, # Оставляем datetime для шаблонизатора
                    'status_for_student': student_facing_status,
                    'raw_experiment_status': exp.status, # Оригинальный статус из Experiments
                    'results_status': results_status, # Статус из Results
                    'assistant_name': exp.assistant.full_name if exp.assistant else 'Нет данных',
                    'status_badge_class': badge_class # Новое поле для класса badge
                })
            
            context['student_experiments_list'] = student_experiments_data
            logger.info(f"Prepared {len(student_experiments_data)} experiments for student {request.user.email} to display. Data: {student_experiments_data}")

        except Exception as e:
            logger.error(f"Error fetching experiments for student {request.user.email} in home_view: {str(e)}", exc_info=True)
            context['student_experiments_list'] = []
            context['student_experiments_error'] = "Не удалось загрузить список экспериментов."


    elif request.user.role == 'teacher':
        logger.info(f"Building context for teacher: {request.user.email}")
        
        students_with_experiments = []
        # Получаем всех студентов
        all_students = User.objects.filter(role='student').order_by('group_name', 'full_name')
        
        for student in all_students:
            experiments_query = Experiments.objects.filter(
                user=student
            ).select_related('results').order_by('-created_at')
            
            student_experiments_data = []
            for exp in experiments_query:
                results = getattr(exp, 'results', None)
                status_display = 'Неизвестно'
                badge_class = 'bg-secondary'

                if results:
                    if results.status == 'pending_student_input':
                        status_display = 'В процессе (студент)'
                        badge_class = 'bg-primary'
                    elif results.status == 'success' or results.status == 'final_completed':
                        status_display = 'Завершен (успешно)'
                        badge_class = 'bg-success'
                    elif results.status == 'fail':
                        status_display = 'Провален'
                        badge_class = 'bg-danger'
                    else:
                        status_display = results.get_status_display()
                        badge_class = 'bg-info'
                elif exp.status == 'failed':
                    status_display = 'Провален (системой)'
                    badge_class = 'bg-danger'
                elif exp.status == 'completed':
                    status_display = 'Ожидает данных студента'
                    badge_class = 'bg-warning'
                else:
                    status_display = exp.get_status_display()
                    # Дополнительные классы можно назначить здесь на основе exp.status
                    if exp.status == 'aborted':
                        badge_class = 'bg-dark'
                    elif 'stage' in exp.status or exp.status == 'preparing':
                        badge_class = 'bg-warning text-dark'
                    
                student_experiments_data.append({
                    'id': exp.id,
                    'created_at': exp.created_at,
                    'status_display': status_display,
                    'badge_class': badge_class,
                    'raw_status_experiment': exp.status,
                    'raw_status_results': results.status if results else None,
                })
            
            students_with_experiments.append({
                'student_id': student.id,
                'full_name': student.full_name,
                'group_name': student.group_name if student.group_name else 'Без группы',
                'experiments': student_experiments_data
            })
            
        context.update({
            'students_with_experiments': students_with_experiments,
            'is_teacher': True,
        })
        logger.info(f"Prepared data for {len(students_with_experiments)} students for teacher {request.user.email}.")

    elif request.user.role == 'assistant':
        logger.info(f"Building context for assistant: {request.user.email}")
        # Логика для лаборанта остается здесь, если она отличается от общей home_view
        # Если home_view для лаборанта - это assistant_dashboard, то этот блок может не нужен
        # или нужно решить, какая view является основной для home лаборанта.
        # Судя по urls.py, assistant_dashboard это отдельный view.
        # Этот блок home_view для assistant, возможно, избыточен или должен быть другим.
        # Пока оставим как есть, предполагая, что есть общая home_view.
        
        # Пример: если лаборанту тоже нужен список его активных экспериментов на общей home
        context['active_experiments_for_assistant'] = Experiments.objects.filter(
            assistant=request.user,
            status__in=['preparing', 'stage_1', 'stage_2', 'stage_3']
        ).select_related('user').order_by('-created_at')
        context['students_for_assistant'] = User.objects.filter(role='student').order_by('full_name')
        logger.info(f"Found {context['active_experiments_for_assistant'].count()} active experiments for assistant {request.user.email}")


    return render(request, 'home.html', context)


@login_required
def group_students_view(request, group_name: str) -> HttpResponse:
    """
    Отображение списка студентов в группе (доступно только преподавателям).

    Args:
        request: HttpRequest объект
        group_name: Название группы

    Returns:
        HttpResponse: Отрендеренный шаблон group_students.html или 403 ошибка
    """
    if request.user.role != 'teacher':
        logger.warning(
            f"User {request.user.email} tried to access group students without permission"
        )
        return HttpResponseForbidden()

    logger.info(f"Teacher {request.user.email} viewing group {group_name}")
    students = User.objects.filter(
        role='student',
        group_name=group_name
    ).order_by('full_name')

    return render(request, 'group_students.html', {
        'group_name': group_name,
        'students': students
    })


class LoginChoiceView(View):
    """Представление выбора типа входа (студент/преподаватель)."""

    def get(self, request) -> HttpResponse:
        """
        Обработка GET-запроса - отображение страницы выбора.

        Args:
            request: HttpRequest объект

        Returns:
            HttpResponse: Отрендеренный шаблон login_choice.html
        """
        logger.debug("Login choice page accessed")
        return render(request, 'auth/login_choice.html')


class StudentLoginView(View):
    """Представление для входа студентов."""

    def get(self, request) -> HttpResponse:
        """
        Обработка GET-запроса - отображение формы входа.

        Args:
            request: HttpRequest объект

        Returns:
            HttpResponse: Отрендеренный шаблон student_login.html
        """
        logger.debug("Student login form accessed")
        form = StudentLoginForm()
        return render(request, 'auth/student_login.html', {'form': form})

    def post(self, request) -> HttpResponse:
        """
        Обработка POST-запроса - проверка данных и вход.

        Args:
            request: HttpRequest объект с данными формы

        Returns:
            HttpResponse: Редирект на home или форма с ошибками
        """
        form = StudentLoginForm(data=request.POST)
        if form.is_valid():
            user = form.get_user()
            auth_login(request, user)
            logger.info(f"Student {user.email} successfully logged in")
            messages.success(request, "Вы успешно вошли в систему!")
            return redirect('home')

        logger.warning("Invalid student login attempt")
        messages.error(request, "Ошибка входа. Проверьте введенные данные.")
        return render(request, 'auth/student_login.html', {'form': form})


class TeacherLoginView(View):
    """Представление для входа преподавателей."""

    def get(self, request) -> HttpResponse:
        """
        Обработка GET-запроса - отображение формы входа.

        Args:
            request: HttpRequest объект

        Returns:
            HttpResponse: Отрендеренный шаблон teacher_login.html
        """
        logger.debug("Teacher login form accessed")
        form = TeacherLoginForm()
        return render(request, 'auth/teacher_login.html', {
            'form': form,
            'user_type': 'teacher'
        })

    def post(self, request) -> HttpResponse:
        """
        Обработка POST-запроса - проверка данных и вход.

        Args:
            request: HttpRequest объект с данными формы

        Returns:
            HttpResponse: Редирект на home или форма с ошибками
        """
        form = TeacherLoginForm(data=request.POST)
        if form.is_valid():
            user = form.get_user()
            auth_login(request, user)
            logger.info(f"Teacher {user.email} successfully logged in")
            messages.success(request, f"Добро пожаловать, {user.full_name}!")
            return redirect('home')

        logger.warning("Invalid teacher login attempt")
        messages.error(request, "Ошибка входа. Проверьте email и пароль.")
        return render(request, 'auth/teacher_login.html', {
            'form': form,
            'user_type': 'teacher'
        })




@login_required
def experiment_results(request, experiment_id):
    experiment = get_object_or_404(Experiments, id=experiment_id)
    
    if request.user != experiment.user and request.user != experiment.assistant:
        raise PermissionDenied
    
    data_points = EquipmentData.objects.filter(experiment=experiment).order_by('time_ms')
    context = {
        'experiment': experiment,
        'data_points': data_points,
        'is_assistant': request.user == experiment.assistant
    }
    return render(request, 'experiment/results.html', context)

@login_required
def retry_experiment(request, experiment_id: int) -> HttpResponse:
    """
    Сброс попытки студента для эксперимента для повторного ввода результатов.
    Не удаляет сам эксперимент или его данные, только предыдущий ввод студента.

    Args:
        request: HttpRequest объект
        experiment_id: ID эксперимента

    Returns:
        HttpResponse: Редирект на страницу эксперимента
    """
    experiment = get_object_or_404(Experiments, id=experiment_id)
    if experiment.user != request.user:
        logger.warning(
            f"User {request.user.email} tried to reset attempt for experiment {experiment_id} without permission"
        )
        raise PermissionDenied

    try:
        results_entry = Results.objects.get(experiment=experiment)
        
        # Сброс полей, относящихся к предыдущей попытке студента
        results_entry.student_gamma = None
        results_entry.student_speed = None
        results_entry.error_percent = None
        results_entry.status = 'pending_student_input' # Возвращаем статус для нового ввода
        results_entry.save()
        
        logger.info(f"Student's attempt for experiment {experiment_id} (Results ID: {results_entry.id}) has been reset by user {request.user.email}.")
        messages.success(request, "Ваша предыдущая попытка сброшена. Вы можете ввести рассчитанные значения заново.")
        
        # Редирект обратно на страницу деталей эксперимента
        return redirect('student_experiment_detail', experiment_id=experiment.id)

    except Results.DoesNotExist:
        logger.error(f"No Results entry found for experiment {experiment_id} when trying to reset attempt. This may happen if results were never submitted or an error occurred.")
        messages.error(request, "Не удалось найти данные для сброса попытки. Возможно, результаты еще не были отправлены.")
        # Если записи Results нет, возможно, стоит просто перенаправить на страницу эксперимента,
        # где студент сможет ввести данные в первый раз.
        return redirect('student_experiment_detail', experiment_id=experiment.id)
    except Exception as e:
        logger.error(f"Error resetting student's attempt for experiment {experiment_id}: {str(e)}", exc_info=True)
        messages.error(request, "Произошла ошибка при сбросе вашей попытки. Пожалуйста, попробуйте снова или обратитесь к администратору.")
        return redirect('student_experiment_detail', experiment_id=experiment.id)


class DownloadManualView(LoginRequiredMixin, View):
    """Представление для скачивания методического пособия."""

    def get(self, request) -> FileResponse:
        """
        Обработка GET-запроса - возврат PDF-файла методички.

        Args:
            request: HttpRequest объект

        Returns:
            FileResponse: PDF файл или 404 ошибка
        """
        file_path = config.MANUAL_PDF_PATH
        if os.path.exists(file_path):
            logger.info(f"User {request.user.email} downloaded manual")
            return FileResponse(
                open(file_path, 'rb'),
                content_type='application/pdf'
            )
        
        logger.error(f"Manual not found at {file_path}")
        raise Http404("Методичка не найдена")
    
@login_required
def submit_results(request):
    data = json.loads(request.body)
    experiment = Experiments.objects.get(id=data['experiment_id'])
    
    # Расчет эталонного значения
    system_gamma = experiment.system_gamma
    
    # Сравнение
    error = abs((data['gamma'] - system_gamma) / system_gamma) * 100
    experiment.error_percent = error
    experiment.save()
    
    return JsonResponse({
        'status': 'success' if error <= 5 else 'fail',
        'system_gamma': system_gamma,
        'error': error
    })

@login_required
@require_http_methods(["POST"])
def save_experiment_results(request, experiment_id):
    """Сохранение результатов, введенных студентом (поэтапно)."""
    try:
        experiment = get_object_or_404(Experiments, id=experiment_id, user=request.user)
        # results_entry, created = Results.objects.get_or_create(experiment=experiment) # Results будет обновлен позже

        data = json.loads(request.body)
        logger.info(f"Experiment {experiment_id}: Сохранение результатов студента. Полученные данные: {data}")

        # Ожидаем данные для каждого этапа
        # student_values_stages = data.get('stages') # Предположим, что данные приходят как список словарей
        # Пример: data = {
        # 'student_speed_stage1': 340, 'student_gamma_stage1': 1.4,
        # 'student_speed_stage2': 342, 'student_gamma_stage2': 1.41,
        # 'student_speed_stage3': 339, 'student_gamma_stage3': 1.39
        # }

        all_stages_successful = True
        per_stage_student_data = []

        for i in range(1, 4): # Для трех этапов
            student_speed_str = data.get(f'student_speed_stage{i}')
            student_gamma_str = data.get(f'student_gamma_stage{i}')

            if student_speed_str is None or student_gamma_str is None:
                logger.error(f"Experiment {experiment_id}, этап {i}: отсутствуют поля student_speed_stage{i} или student_gamma_stage{i}")
                return JsonResponse({
                    'status': 'error',
                    'message': f'Отсутствуют обязательные поля для этапа {i}: скорость и гамма'
                }, status=400)
            
            try:
                student_speed = float(student_speed_str)
                student_gamma = float(student_gamma_str)
            except ValueError:
                logger.error(f"Experiment {experiment_id}, этап {i}: скорость или гамма не являются числами.")
                return JsonResponse({
                    'status': 'error',
                    'message': f'Скорость и гамма для этапа {i} должны быть числами.'
                }, status=400)

            # Сохраняем студенческие значения в модель Experiments
            setattr(experiment, f'student_speed_stage{i}', student_speed)
            setattr(experiment, f'student_gamma_stage{i}', student_gamma)
            
            per_stage_student_data.append({
                'stage': i,
                'speed': student_speed,
                'gamma': student_gamma
            })

            # Получаем системные значения для этого этапа
            system_speed = getattr(experiment, f'system_speed_stage{i}', None)
            system_gamma = getattr(experiment, f'system_gamma_stage{i}', None)

            error_percent_s = None
            error_percent_g = None
            stage_successful = True # Флаг успеха для текущего этапа

            if system_speed is not None and system_speed != 0:
                error_percent_s = round(abs((student_speed - system_speed) / system_speed) * 100, 2)
                setattr(experiment, f'error_percent_speed_stage{i}', error_percent_s)
                if error_percent_s > config.ACCEPTABLE_ERROR_PERCENT:
                    stage_successful = False
            else:
                logger.warning(f"Experiment {experiment.id}, этап {i}: системная скорость = {system_speed}. Невозможно рассчитать ошибку скорости.")
                setattr(experiment, f'error_percent_speed_stage{i}', None)
                stage_successful = False 

            if system_gamma is not None and system_gamma != 0:
                error_percent_g = round(abs((student_gamma - system_gamma) / system_gamma) * 100, 2)
                setattr(experiment, f'error_percent_gamma_stage{i}', error_percent_g)
                if error_percent_g > config.ACCEPTABLE_ERROR_PERCENT:
                    stage_successful = False
            else:
                logger.warning(f"Experiment {experiment.id}, этап {i}: системная гамма = {system_gamma}. Невозможно рассчитать ошибку гаммы.")
                setattr(experiment, f'error_percent_gamma_stage{i}', None)
                stage_successful = False
            
            if not stage_successful:
                all_stages_successful = False
        
        # Обработка student_final_gamma
        student_final_gamma_str = data.get('student_final_gamma')
        if student_final_gamma_str is None:
            logger.error(f"Experiment {experiment_id}: отсутствует поле student_final_gamma")
            return JsonResponse({
                'status': 'error',
                'message': 'Отсутствует обязательное поле: Финальная гамма (средняя по этапам)'
            }, status=400)
        try:
            student_final_gamma = float(student_final_gamma_str)
            experiment.student_final_gamma = student_final_gamma
        except ValueError:
            logger.error(f"Experiment {experiment_id}: финальная гамма не является числом.")
            return JsonResponse({
                'status': 'error',
                'message': 'Финальная гамма должна быть числом.'
            }, status=400)

        # Расчет system_final_gamma
        system_gammas_for_avg = []
        if experiment.system_gamma_stage1 is not None: system_gammas_for_avg.append(experiment.system_gamma_stage1)
        if experiment.system_gamma_stage2 is not None: system_gammas_for_avg.append(experiment.system_gamma_stage2)
        if experiment.system_gamma_stage3 is not None: system_gammas_for_avg.append(experiment.system_gamma_stage3)
        
        system_final_gamma = None
        if system_gammas_for_avg:
            system_final_gamma = round(sum(system_gammas_for_avg) / len(system_gammas_for_avg), 3)
            experiment.system_final_gamma = system_final_gamma
        else:
            logger.warning(f"Experiment {experiment.id}: нет системных поэтапных гамм для расчета system_final_gamma.")
            experiment.system_final_gamma = None

        # Расчет error_percent_final_gamma
        error_percent_final_gamma = None
        final_gamma_successful = True # Флаг успеха для финальной гаммы
        if system_final_gamma is not None and system_final_gamma != 0:
            error_percent_final_gamma = round(abs((student_final_gamma - system_final_gamma) / system_final_gamma) * 100, 2)
            experiment.error_percent_final_gamma = error_percent_final_gamma
            if error_percent_final_gamma > config.ACCEPTABLE_ERROR_PERCENT:
                final_gamma_successful = False
        else:
            logger.warning(f"Experiment {experiment.id}: системная финальная гамма = {system_final_gamma}. Невозможно рассчитать ошибку финальной гаммы.")
            experiment.error_percent_final_gamma = None
            final_gamma_successful = False # Считаем неуспешным, если нет системных данных для сравнения

        experiment.save() # Сохраняем все обновленные поля эксперимента

        # Обновляем статус в Results и Experiments
        results_entry, created = Results.objects.get_or_create(experiment=experiment)
        # Итоговый успех, если ВСЕ этапы успешны И финальная гамма успешна
        final_overall_status_value = 'success' if all_stages_successful and final_gamma_successful else 'fail'
        
        # Если успех — фиксируем success, если нет — оставляем возможность повторного ввода
        if final_overall_status_value == 'success':
            results_entry.status = 'success'
        else:
            results_entry.status = 'pending_student_input'
        # Очистим старые поля усредненных значений в Results
        results_entry.student_speed = None 
        results_entry.student_gamma = None
        results_entry.gamma_calculated = None 
        results_entry.speed_of_sound_calculated = None 
        results_entry.error_percent_gamma = None 
        results_entry.error_percent_speed = None 
        results_entry.save()

        experiment.status = 'completed' if final_overall_status_value == 'success' else 'failed'
        experiment.save()

        logger.info(f"Результаты для эксперимента {experiment_id} сохранены. Итоговый статус: {final_overall_status_value}. Поэтапные: {per_stage_student_data}. Финальная гамма студ: {student_final_gamma}, сист: {system_final_gamma}, ошибка: {error_percent_final_gamma}")

        # Формируем ответ для клиента
        response_payload = {
            'status': 'success', # Статус HTTP запроса
            'message': 'Результаты успешно сохранены!',
            'overall_status': final_overall_status_value, # Общий итог (success/fail)
            'stages': [],
            'final_gamma_results': { # Новая секция для финальной гаммы
                'student_final_gamma': student_final_gamma,
                'system_final_gamma': system_final_gamma,
                'error_percent_final_gamma': error_percent_final_gamma
            }
        }
        for i in range(1, 4):
            response_payload['stages'].append({
                'stage_number': i,
                'student_speed': getattr(experiment, f'student_speed_stage{i}'),
                'student_gamma': getattr(experiment, f'student_gamma_stage{i}'),
                'system_speed': getattr(experiment, f'system_speed_stage{i}'),
                'system_gamma': getattr(experiment, f'system_gamma_stage{i}'),
                'error_percent_speed': getattr(experiment, f'error_percent_speed_stage{i}'),
                'error_percent_gamma': getattr(experiment, f'error_percent_gamma_stage{i}'),
            })
        
        return JsonResponse(response_payload)
    
    except Experiments.DoesNotExist:
        logger.error(f"Experiment {experiment_id} не найден при попытке сохранения результатов студента.")
        return JsonResponse({'status': 'error', 'message': 'Эксперимент не найден'}, status=404)
    except Exception as e:
        logger.error(f"Ошибка при сохранении результатов студента для эксперимента {experiment_id}: {str(e)}", exc_info=True)
        return JsonResponse({
            'status': 'error',
            'message': f'Внутренняя ошибка сервера: {str(e)}'
        }, status=500)
    
@login_required
def download_protocol(request, experiment_id):
    experiment = get_object_or_404(Experiments, id=experiment_id)
    student = experiment.user
    
    # Проверка прав доступа
    if not (request.user.is_staff or request.user == student):
        return HttpResponseForbidden()
    
    # Генерация PDF
    pdf_content = generate_protocol_pdf(experiment, student)
    
    # Возвращаем PDF как ответ
    response = HttpResponse(pdf_content, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="protocol_{experiment_id}.pdf"'
    return response

def generate_protocol_pdf(experiment, student_data):
    """Генерация PDF протокола с использованием ReportLab"""
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    
    # Регистрируем шрифт с поддержкой кириллицы
    font_path = os.path.join(settings.BASE_DIR, 'static', 'fonts', 'DejaVuSans-Bold.ttf')
    pdfmetrics.registerFont(TTFont('DejaVu', font_path))
    
    # Настройки документа
    width, height = A4
    margin = 2 * cm
    line_height = 0.5 * cm
    
    # 1. Заголовок документа
    p.setFont("DejaVu", 16)
    p.drawString(margin, height - margin, f"Протокол эксперимента #{experiment.id}")
    
    # 2. Информация о студенте
    p.setFont("DejaVu", 12)
    y_position = height - margin - line_height * 2
    p.drawString(margin, y_position, f"Студент: {student_data['full_name']}")
    y_position -= line_height
    p.drawString(margin, y_position, f"Группа: {student_data['group_name']}")
    y_position -= line_height
    p.drawString(margin, y_position, f"Дата: {experiment.created_at.strftime('%d.%m.%Y %H:%M')}")
    
    # 3. Этап 1
    y_position -= line_height * 1.5
    p.setFont("DejaVu", 14)
    p.drawString(margin, y_position, "Этап 1:")
    
    p.setFont("DejaVu", 12)
    y_position -= line_height
    p.drawString(margin, y_position, f"Введенная скорость звука: {experiment.student_speed_stage1 or '-'} м/с")
    y_position -= line_height
    p.drawString(margin, y_position, f"Введенное значение γ: {experiment.student_gamma_stage1 or '-'}")
    y_position -= line_height
    p.drawString(margin, y_position, f"Рассчитанная скорость звука: {experiment.system_speed_stage1 or '-'} м/с")
    y_position -= line_height
    p.drawString(margin, y_position, f"Рассчитанное значение γ: {experiment.system_gamma_stage1 or '-'}")
    y_position -= line_height
    p.drawString(margin, y_position, f"Отклонения: Скорость: {experiment.error_percent_speed_stage1 or '-'}%, γ: {experiment.error_percent_gamma_stage1 or '-'}%")
    
    # 4. Этап 2
    y_position -= line_height * 1.5
    p.setFont("DejaVu", 14)
    p.drawString(margin, y_position, "Этап 2:")
    
    p.setFont("DejaVu", 12)
    y_position -= line_height
    p.drawString(margin, y_position, f"Введенная скорость звука: {experiment.student_speed_stage2 or '-'} м/с")
    y_position -= line_height
    p.drawString(margin, y_position, f"Введенное значение γ: {experiment.student_gamma_stage2 or '-'}")
    y_position -= line_height
    p.drawString(margin, y_position, f"Рассчитанная скорость звука: {experiment.system_speed_stage2 or '-'} м/с")
    y_position -= line_height
    p.drawString(margin, y_position, f"Рассчитанное значение γ: {experiment.system_gamma_stage2 or '-'}")
    y_position -= line_height
    p.drawString(margin, y_position, f"Отклонения: Скорость: {experiment.error_percent_speed_stage2 or '-'}%, γ: {experiment.error_percent_gamma_stage2 or '-'}%")
    
    # 5. Этап 3
    y_position -= line_height * 1.5
    p.setFont("DejaVu", 14)
    p.drawString(margin, y_position, "Этап 3:")
    
    p.setFont("DejaVu", 12)
    y_position -= line_height
    p.drawString(margin, y_position, f"Введенная скорость звука: {experiment.student_speed_stage3 or '-'} м/с")
    y_position -= line_height
    p.drawString(margin, y_position, f"Введенное значение γ: {experiment.student_gamma_stage3 or '-'}")
    y_position -= line_height
    p.drawString(margin, y_position, f"Рассчитанная скорость звука: {experiment.system_speed_stage3 or '-'} м/с")
    y_position -= line_height
    p.drawString(margin, y_position, f"Рассчитанное значение γ: {experiment.system_gamma_stage3 or '-'}")
    y_position -= line_height
    p.drawString(margin, y_position, f"Отклонения: Скорость: {experiment.error_percent_speed_stage3 or '-'}%, γ: {experiment.error_percent_gamma_stage3 or '-'}%")
    
    # 6. Финальные результаты
    y_position -= line_height * 1.5
    p.setFont("DejaVu", 14)
    p.drawString(margin, y_position, "Финальные результаты:")
    
    p.setFont("DejaVu", 12)
    y_position -= line_height
    p.drawString(margin, y_position, f"Финальное значение γ (студент): {experiment.student_final_gamma or '-'}")
    y_position -= line_height
    p.drawString(margin, y_position, f"Финальное значение γ (система): {experiment.system_final_gamma or '-'}")
    y_position -= line_height
    p.drawString(margin, y_position, f"Финальное отклонение по γ: {experiment.error_percent_final_gamma or '-'}%")
    
    # 7. Итоговый результат
    y_position -= line_height * 1.5
    p.setFont("DejaVu", 14)
    p.drawString(margin, y_position, "Итоговый результат эксперимента:")
    
    p.setFont("DejaVu", 12)
    y_position -= line_height
    p.drawString(margin, y_position, f"Статус: {experiment.status}")
    
    # 8. Подпись и дата
    y_position -= line_height * 2
    p.line(margin, y_position, width - margin, y_position)
    y_position -= line_height
    p.drawString(margin, y_position, "Преподаватель: ___________________")
    y_position -= line_height
    p.drawString(margin, y_position, "Дата: ___________________")
    
    # Сохраняем PDF
    p.showPage()
    p.save()
    
    # Получаем содержимое PDF
    pdf = buffer.getvalue()
    buffer.close()
    return pdf

@login_required
@require_http_methods(["POST"])
def start_experiment_api(request):
    """API для создания нового эксперимента и возврата его ID"""
    try:
        experiment = Experiments.objects.create(
            user=request.user,
            temperature=0,  # Временные значения
            frequency=0,
            tube_length=0.5,
            status='started'
        )
        return JsonResponse({
            'status': 'success',
            'experiment_id': experiment.id
        })
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)
    
@login_required
def assistant_dashboard(request):
    if request.user.role != 'assistant':
        return HttpResponseForbidden()
    
    logger.info(f"Assistant {request.user.id} accessed dashboard")
    
    # Получаем активные эксперименты для текущего лаборанта
    active_experiments = Experiments.objects.filter(
        assistant=request.user,
        status__in=['preparing', 'stage_1', 'stage_2', 'stage_3']
    ).select_related('user')
    
    logger.info(f"Found {active_experiments.count()} experiments")
    
    return render(request, 'home.html', {
        'active_experiments': active_experiments,
        'students': User.objects.filter(role='student').order_by('full_name')
    })

@login_required
@require_http_methods(["POST"])
def assistant_start_experiment(request):
    """Создание эксперимента с начальными параметрами"""
    logger.info(f"Start experiment request from {request.user}")
    print(f"DEBUG: Start experiment request from {request.user}")

    try:
        if request.user.role != 'assistant':
            logger.warning(f"User {request.user} is not an assistant")
            return JsonResponse({'status': 'error', 'message': 'Только для лаборантов'}, status=403)

        data = json.loads(request.body)
        student_id = data.get('student_id')
        temperature = float(data.get('temperature', 20.0))

        logger.info(f"Creating experiment for student {student_id}")
        print(f"DEBUG: Creating experiment for student {student_id}")

        if not student_id:
            logger.error("No student_id provided")
            return JsonResponse({'status': 'error', 'message': 'Не указан студент'}, status=400)

        student = get_object_or_404(User, id=student_id, role='student')

        experiment = Experiments.objects.create(
            user=student,
            assistant=request.user,
            temperature=temperature,
            status='preparing',
            stages=[{"frequency": None, "data": []} for _ in range(3)]
        )

        logger.info(f"Experiment {experiment.id} created successfully")
        print(f"DEBUG: Experiment {experiment.id} created")

        return JsonResponse({
            'status': 'success',
            'experiment_id': experiment.id,
            'student_name': student.full_name,
            'temperature': temperature
        })
    except Exception as e:
        logger.error(f"Error creating experiment: {str(e)}")
        print(f"ERROR: {str(e)}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@login_required
def upload_experiment_data(request, experiment_id):
    experiment = get_object_or_404(Experiments, id=experiment_id)
    
    if request.user != experiment.assistant:
        return JsonResponse({'status': 'error', 'message': 'Доступ запрещен'}, status=403)
    
    try:
        data = json.loads(request.body)
        EquipmentData.objects.create(
            experiment=experiment,
            time_ms=data['time_ms'],
            microphone_signal=data['microphone_signal'],
            tube_position=data['tube_position'],
            voltage=data['voltage']
        )
        return JsonResponse({'status': 'success'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    

class AssistantLoginView(View):
    template_name = 'auth/assistant_login.html'
    
    def get(self, request):
        form = AssistantLoginForm()
        return render(request, self.template_name, {'form': form})

    def post(self, request):
        form = AssistantLoginForm(data=request.POST, request=request)
        
        if form.is_valid():
            user = form.get_user()
            auth_login(request, user)
            messages.success(request, f"Добро пожаловать, {user.full_name}!")
            return redirect('assistant_dashboard')
        
        # Логируем ошибки формы
        for field, errors in form.errors.items():
            for error in errors:
                logger.error(f"Login error - {field}: {error}")
        
        return render(request, self.template_name, {'form': form})

@login_required
def get_student_experiments(request):
    logger.info(f"Attempting to get experiments for student: {request.user.email} (ID: {request.user.id})")
    if request.user.role != 'student':
        logger.warning(f"Access denied for user {request.user.email} to get_student_experiments (not a student).")
        return JsonResponse({'status': 'error', 'message': 'Доступ запрещен'}, status=403)
    
    try:
        # Запрашиваем эксперименты и связанные с ними результаты
        experiments_with_results = Experiments.objects.filter(
            user=request.user  # ИСПРАВЛЕНО ЗДЕСЬ
        ).select_related('assistant', 'results').order_by('-created_at')
        
        logger.info(f"Found {experiments_with_results.count()} experiments for student {request.user.email} before processing statuses.")

        experiments_data = []
        for exp in experiments_with_results:
            student_facing_status = 'Неизвестно'
            results_status = exp.results.status if hasattr(exp, 'results') and exp.results else None
            exp_status_from_model = exp.status

            if results_status: # Если есть статус в Results
                if results_status == 'pending_student_input':
                    student_facing_status = 'в процессе выполнения'
                elif results_status == 'success' or results_status == 'final_completed':
                    student_facing_status = 'Завершен'
                elif results_status == 'fail':
                    student_facing_status = exp.results.get_status_display() # Должно быть 'Провальный'
                else: # Другие возможные статусы Results (например, completed_by_assistant)
                    student_facing_status = exp.results.get_status_display()
            elif exp_status_from_model == 'failed': # Обработка статуса Experiments.failed
                student_facing_status = exp.get_status_display() # Должно вернуть "Провальный"
            elif exp_status_from_model == 'completed':
                # Эксперимент завершен лаборантом, но студент еще не вводил данные, или Results еще не созданы/обновлены
                student_facing_status = 'Ожидает ваших результатов'
            else:
                # Статус из модели Experiment, если нет данных в Results и не 'failed'/'completed'
                student_facing_status = exp.get_status_display()

            experiments_data.append({
                'id': exp.id,
                'created_at': exp.created_at.strftime('%Y-%m-%d %H:%M:%S') if exp.created_at else None,
                'status_for_student': student_facing_status,
                'raw_experiment_status': exp.status,
                'results_status': results_status,
                'assistant_name': exp.assistant.full_name if exp.assistant else 'Нет данных'
            })
        
        logger.info(f"Returning {len(experiments_data)} experiments for student {request.user.email}. Data: {experiments_data}")
        return JsonResponse({'experiments': experiments_data, 'status': 'success'})
    except Exception as e:
        logger.error(f"Error in get_student_experiments for user {request.user.email}: {str(e)}", exc_info=True)
        return JsonResponse({'status': 'error', 'message': 'Внутренняя ошибка сервера при получении экспериментов'}, status=500)

@login_required
@require_http_methods(["POST"])
def add_experiment_stage(request, experiment_id):
    """Добавление этапа с частотой."""
    try:
        experiment = get_object_or_404(Experiments, id=experiment_id)
        if request.user != experiment.assistant:
            return JsonResponse({'status': 'error', 'message': 'Нет прав'}, status=403)

        data = json.loads(request.body)
        frequency = float(data.get('frequency'))

        if not (1000 <= frequency <= 6000):
            return JsonResponse({'status': 'error', 'message': 'Частота должна быть 1000-6000 Гц'}, status=400)

        experiment.stages.append({
            'frequency': frequency,
            'data': [],
            'created_at': timezone.now().isoformat()
        })
        
        # Обновляем статус
        if len(experiment.stages) == 1:
            experiment.status = 'stage_1'
        elif len(experiment.stages) == 2:
            experiment.status = 'stage_2'
        elif len(experiment.stages) >= 3:
            experiment.status = 'stage_3'

        experiment.save()

        return JsonResponse({
            'status': 'success',
            'stage_number': len(experiment.stages),
            'current_stage': experiment.status
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@login_required
@require_http_methods(["POST"])
def upload_experiment_data(request, experiment_id):
    """Загрузка данных с оборудования."""
    try:
        experiment = get_object_or_404(Experiments, id=experiment_id)
        if request.user != experiment.assistant:
            return JsonResponse({'status': 'error', 'message': 'Доступ запрещен'}, status=403)

        data = json.loads(request.body)
        current_stage = int(data.get('stage', 1)) - 1
        
        if current_stage >= len(experiment.stages):
            return JsonResponse({'status': 'error', 'message': 'Неверный номер этапа'}, status=400)

        # Добавляем данные в текущий этап
        experiment.stages[current_stage]['data'].append({
            'time_ms': data['time_ms'],
            'microphone_signal': data['microphone_signal'],
            'tube_position': data['tube_position'],
            'voltage': data['voltage']
        })
        experiment.save()

        return JsonResponse({'status': 'success'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

@login_required
def experiment_control_view(request, experiment_id):
    """Контрольная панель эксперимента для лаборанта"""
    experiment = get_object_or_404(Experiments, id=experiment_id)
    print(f"DEBUG: Opening experiment {experiment_id}")
    
    if request.user != experiment.assistant:
        raise PermissionDenied
    
    # Если этапов нет - инициализируем 3 пустых этапа
    if not experiment.stages:
        experiment.stages = [{"frequency": None, "data": []} for _ in range(3)]
        experiment.save()
    
    return render(request, 'experiment/control.html', {
        'experiment': experiment,
        'student': experiment.user
    })

@login_required
@require_http_methods(["POST"])
def save_experiment_params(request, experiment_id):
    """Сохранение параметров эксперимента"""
    try:
        experiment = get_object_or_404(Experiments, id=experiment_id)
        if request.user != experiment.assistant:
            return JsonResponse({'status': 'error', 'message': 'Нет прав'}, status=403)

        data = json.loads(request.body)
        experiment.temperature = float(data['temperature'])
        
        # Обновляем частоты для всех этапов
        for i, freq in enumerate(data['frequencies']):
            if i < len(experiment.stages):
                experiment.stages[i]['frequency'] = float(freq) if freq else None
                # Добавляем данные графиков, если они есть
                if 'charts_data' in data and f'step_{i+1}' in data['charts_data']:
                    experiment.stages[i]['chart_data'] = data['charts_data'][f'step_{i+1}']
        
        experiment.save()
        return JsonResponse({'status': 'success'})

    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@login_required
@require_http_methods(["POST"])
def complete_experiment(request, experiment_id):
    """Завершение эксперимента"""
    try:
        experiment = get_object_or_404(Experiments, id=experiment_id)
        if request.user != experiment.assistant:
            return JsonResponse({'status': 'error', 'message': 'Нет прав'}, status=403)

        data = json.loads(request.body)
        logger.info(f"complete_experiment called for experiment {experiment_id}. Received steps data: {data.get('steps')}")
        
        # Обновляем данные эксперимента
        experiment.temperature = float(data['temperature'])
        experiment.status = 'completed'
        
        # Обновляем данные этапов
        for step_data in data['steps']:
            step_index = step_data['step'] - 1
            if step_index < len(experiment.stages):
                experiment.stages[step_index].update({
                    'frequency': step_data['frequency'],
                    'data': step_data['data'],
                    'labels': step_data['labels']
                })
        
        # Сохраняем итоговые данные графиков
        if 'charts_data' in data:
            experiment.visualization_data = data['charts_data']
        
        experiment.save()

        # Расчет системных значений ПОЭТАПНО
        # system_avg_speed, system_avg_gamma = calculate_system_results(experiment.stages, experiment.temperature) # Старый вызов
        system_stage_results = calculate_system_results(experiment.stages, experiment.temperature) # Новый вызов, возвращает список словарей
        logger.info(f"Experiment {experiment_id}: Calculated system_stage_results={system_stage_results}")

        # Сохранение поэтапных системных результатов в модель Experiments
        if system_stage_results and len(system_stage_results) > 0:
            experiment.system_speed_stage1 = system_stage_results[0].get('speed') if len(system_stage_results) > 0 else None
            experiment.system_gamma_stage1 = system_stage_results[0].get('gamma') if len(system_stage_results) > 0 else None
        if system_stage_results and len(system_stage_results) > 1:
            experiment.system_speed_stage2 = system_stage_results[1].get('speed') if len(system_stage_results) > 1 else None
            experiment.system_gamma_stage2 = system_stage_results[1].get('gamma') if len(system_stage_results) > 1 else None
        if system_stage_results and len(system_stage_results) > 2:
            experiment.system_speed_stage3 = system_stage_results[2].get('speed') if len(system_stage_results) > 2 else None
            experiment.system_gamma_stage3 = system_stage_results[2].get('gamma') if len(system_stage_results) > 2 else None
        
        experiment.save() # Сохраняем обновленный experiment с поэтапными системными данными

        # Создание или обновление записи в Results
        # Поля gamma_calculated и speed_of_sound_calculated в Results теперь могут быть не нужны
        # или использоваться для каких-то общих/справочных значений, если это требуется.
        # На данном этапе я их закомментирую, предполагая, что основные данные теперь в Experiments.
        Results.objects.update_or_create(
            experiment=experiment,
            defaults={
                'visualization_data': data.get('charts_data', {}),
                'detailed_results': data.get('steps', []), # Это поле кажется важным, оставляем
                'status': 'pending_student_input', 
                # 'gamma_calculated': system_avg_gamma, # Устарело, данные теперь в Experiments
                # 'speed_of_sound_calculated': system_avg_speed # Устарело, данные теперь в Experiments
            }
        )

        return JsonResponse({'status': 'success'})

    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@login_required
def get_experiment_details_for_student(request, experiment_id):
    """API для получения студентом детальных данных эксперимента для расчетов."""
    if request.user.role != 'student':
        logger.warning(f"User {request.user.email} (not a student) tried to access student experiment data for {experiment_id}")
        return JsonResponse({'status': 'error', 'message': 'Доступ запрещен'}, status=403)

    try:
        experiment = get_object_or_404(Experiments, id=experiment_id, user=request.user)
        # Пытаемся получить связанную запись Results. Она может отсутствовать, если что-то пошло не так
        # или если эксперимент еще не был 'completed' лаборантом (хотя API вызывается студентом уже после этого).
        results_entry = Results.objects.filter(experiment=experiment).first()

        stages_data_for_student = []
        if isinstance(experiment.stages, list):
            for stage_index, stage_dict in enumerate(experiment.stages):
                if isinstance(stage_dict, dict):
                    raw_minima_data = stage_dict.get('minima', []) # Используем 'minima'
                    
                    minima_table_for_stage = []
                    l_values_for_delta_calc = [] # Для расчета delta_l

                    # >>> НАЧАЛО ИЗМЕНЕНИЙ ДЛЯ ПОЛНОГО СИГНАЛА
                    full_signal_data_for_stage = []
                    # ИЗМЕНЕНИЕ: Используем новые поля 'graph_distances_cm' и 'graph_amplitudes'
                    graph_distances_cm = stage_dict.get('graph_distances_cm', [])
                    graph_amplitudes = stage_dict.get('graph_amplitudes', [])
                    
                    logger.info(f"[Exp {experiment.id}, Stage {stage_index+1}] Data for graph: {len(graph_distances_cm)} distances, {len(graph_amplitudes)} amplitudes.")

                    temp_full_signal_data = [] # Временный список для накопления всех точек
                    if isinstance(graph_distances_cm, list) and isinstance(graph_amplitudes, list) and len(graph_distances_cm) == len(graph_amplitudes):
                        for i in range(len(graph_distances_cm)):
                            try:
                                pos_m = float(graph_distances_cm[i]) / 100.0 
                                amp = float(graph_amplitudes[i])
                                if not (np.isnan(pos_m) or np.isnan(amp)):
                                    temp_full_signal_data.append({'position': pos_m, 'amplitude': amp})
                            except (ValueError, TypeError) as e:
                                logger.warning(f"[Exp {experiment.id}, Stage {stage_index+1}] Error converting graph data point: dist={graph_distances_cm[i]}, amp={graph_amplitudes[i]}. Error: {e}")
                        
                        # Логика прореживания данных
                        MAX_POINTS_FULL_SIGNAL = 2000
                        TARGET_POINTS_AFTER_DECIMATION = 1000 # Целевое количество точек после прореживания
                        
                        if len(temp_full_signal_data) > MAX_POINTS_FULL_SIGNAL:
                            # Рассчитываем шаг так, чтобы получить примерно TARGET_POINTS_AFTER_DECIMATION точек
                            step = round(len(temp_full_signal_data) / TARGET_POINTS_AFTER_DECIMATION)
                            if step <= 0: step = 1 # Шаг не может быть 0 или отрицательным
                            
                            full_signal_data_for_stage = temp_full_signal_data[::step]
                            logger.info(f"[Exp {experiment.id}, Stage {stage_index+1}] Full signal data decimated from {len(temp_full_signal_data)} to {len(full_signal_data_for_stage)} points (step: {step}).")
                        else:
                            full_signal_data_for_stage = temp_full_signal_data

                        # logger.info(f"[Exp {experiment.id}, Stage {stage_index+1}] Processed full_signal_data_for_stage (first 5): {full_signal_data_for_stage[:5]}") # Заменено на лог ниже
                    elif len(graph_distances_cm) != len(graph_amplitudes):
                        logger.warning(f"[Exp {experiment.id}, Stage {stage_index+1}] Mismatch in lengths for graph data: {len(graph_distances_cm)} distances vs {len(graph_amplitudes)} amplitudes.")
                        full_signal_data_for_stage = [] # Инициализируем пустым списком в случае ошибки
                    else:
                        logger.warning(f"[Exp {experiment.id}, Stage {stage_index+1}] Graph data is not in list format or is missing. Distances type: {type(graph_distances_cm)}, Amplitudes type: {type(graph_amplitudes)}")
                        full_signal_data_for_stage = [] # Инициализируем пустым списком
                    
                    logger.info(f"[Exp {experiment.id}, Stage {stage_index+1}] Final full_signal_data_for_stage (first 5): {full_signal_data_for_stage[:5] if full_signal_data_for_stage else 'Empty'}")
                    # <<< КОНЕЦ ИЗМЕНЕНИЙ ДЛЯ ПОЛНОГО СИГНАЛА

                    if isinstance(raw_minima_data, list):
                        # Сортируем минимумы по 'distance_m' перед использованием, если они еще не отсортированы
                        # Это важно для корректного отображения и расчета delta_l.
                        # Предполагаем, что 'distance_m' всегда присутствует и является числом.
                        # Если 'distance_m' может отсутствовать или быть None, нужна доп. проверка.
                        try:
                            # Фильтруем элементы, где 'distance_m' может быть None или отсутствовать, перед сортировкой
                            valid_minima_for_sort = [m for m in raw_minima_data if isinstance(m, dict) and isinstance(m.get('distance_m'), (int, float))]
                            sorted_minima_data = sorted(valid_minima_for_sort, key=lambda x: x['distance_m'])
                        except TypeError:
                            # В случае ошибки сортировки (например, 'distance_m' - не число), используем исходный порядок
                            # или логируем ошибку и пропускаем. Пока используем исходный.
                            logger.warning(f"Ошибка сортировки минимумов для этапа {stage_index + 1} эксперимента {experiment.id}. Используется исходный порядок.")
                            sorted_minima_data = [m for m in raw_minima_data if isinstance(m, dict)]


                        for idx, minimum_item in enumerate(sorted_minima_data): # Используем отсортированные данные
                            if isinstance(minimum_item, dict) and 'distance_m' in minimum_item: # Эта проверка уже была частью valid_minima_for_sort
                                position = minimum_item.get('distance_m')
                                # Дополнительная проверка, что position это число (хотя sorted должен был это обеспечить)
                                if isinstance(position, (int, float)):
                                    minima_table_for_stage.append({
                                        'minimum_number': idx + 1, # Нумерация основана на отсортированном списке
                                        'position_m': round(position, 4) # Округляем для консистентности
                                    })
                                    l_values_for_delta_calc.append(position) # Собираем значения для delta_l
                    
                    # Расчет delta_l теперь на основе l_values_for_delta_calc
                    # l_values_for_delta_calc уже должны быть отсортированы по возрастанию distance_m
                    delta_l_values = []
                    if len(l_values_for_delta_calc) > 1:
                        for i in range(len(l_values_for_delta_calc) - 1):
                            try:
                                # Разность между соседними (уже отсортированными) позициями
                                diff = round(l_values_for_delta_calc[i+1] - l_values_for_delta_calc[i], 4) 
                                if diff > 0: # Убедимся, что разница положительная (на случай дубликатов или ошибок сортировки)
                                    delta_l_values.append(diff)
                                else:
                                    logger.warning(f"Получена не положительная разность delta_l ({diff}) для этапа {stage_index + 1}, exp {experiment.id}. Позиции: {l_values_for_delta_calc[i+1]}, {l_values_for_delta_calc[i]}. Пропускается.")

                            except (TypeError, IndexError): 
                                logger.warning(f"Ошибка при расчете delta_l для этапа {stage_index+1}, experiment {experiment.id}", exc_info=True)
                                pass
                    
                    average_delta_l = None
                    if delta_l_values:
                        try:
                            average_delta_l = round(sum(delta_l_values) / len(delta_l_values), 4)
                        except ZeroDivisionError:
                            average_delta_l = None

                    # --- ДОБАВЛЕНО ЛОГИРОВАНИЕ --- 
                    logger.info(f"Processing stage_dict for student view (exp {experiment.id}, stage index {stage_index}): {stage_dict}")
                    # --- КОНЕЦ ЛОГИРОВАНИЯ ---

                    stages_data_for_student.append({
                        'id': stage_index, # Добавляем ID на основе индекса
                        'stage_number': stage_index + 1,
                        'frequency_hz': stage_dict.get('frequency'),
                        #'temperature_celsius': stage_dict.get('temperature', experiment.temperature), // Если нужна температура этапа
                        'minima_table': minima_table_for_stage,
                        'delta_l_values_m': delta_l_values,
                        'average_delta_l_m': average_delta_l,
                        'full_signal_data': full_signal_data_for_stage # >>> ДОБАВЛЕНО НОВОЕ ПОЛЕ
                    })
                else:
                    logger.warning(f"Этап {stage_index+1} в эксперименте {experiment.id} не является словарем: {stage_dict}")
        else:
            logger.warning(f"experiment.stages для эксперимента {experiment.id} не является списком: {experiment.stages}")

        global_temp_celsius = experiment.temperature
        global_temp_kelvin = None
        if global_temp_celsius is not None:
            global_temp_kelvin = round(global_temp_celsius + 273.15, 2)

        results_status = None
        if results_entry:
            results_status = results_entry.status
            # Старые поля, такие как results_entry.gamma_calculated, results_entry.student_gamma и т.д. больше не используются здесь.

        # Формируем поэтапные системные расчеты для отладки на странице студента
        system_calculations_per_stage = []
        student_submitted_values_per_stage = [] # Для возможного отображения ранее введенных студентом значений

        for i in range(1, 4):
            system_calculations_per_stage.append({
                'stage': i,
                'speed': getattr(experiment, f'system_speed_stage{i}', None),
                'gamma': getattr(experiment, f'system_gamma_stage{i}', None)
            })
            # Также соберем данные, которые студент мог уже ввести для этого эксперимента
            student_submitted_values_per_stage.append({
                'stage': i,
                'speed': getattr(experiment, f'student_speed_stage{i}', None),
                'gamma': getattr(experiment, f'student_gamma_stage{i}', None),
                'error_speed': getattr(experiment, f'error_percent_speed_stage{i}', None),
                'error_gamma': getattr(experiment, f'error_percent_gamma_stage{i}', None)
            })

        # Принудительно отключаем отладочный режим для профиля студента (если это временная мера)
        DEBUG_MODE_FOR_STUDENT_PROFILE = False

        response_data = {
            'status': 'success',
            'experiment_id': experiment.id,
            'created_at': experiment.created_at.strftime('%Y-%m-%d %H:%M:%S') if experiment.created_at else None,
            'experiment_status_raw': experiment.status, # Статус из Experiments
            'global_temperature_celsius': global_temp_celsius,
            'global_temperature_kelvin': global_temp_kelvin,
            'molar_mass_air_kg_mol': 0.029, # кг/моль
            'stages': stages_data_for_student, # Данные для расчетов студента (минимумы, deltaL и т.д.)
            
            # Новые поля с поэтапными данными:
            'system_results_per_stage': system_calculations_per_stage, # Системные расчеты по этапам
            'student_submitted_values_per_stage': student_submitted_values_per_stage, # Что студент ввел по этапам (если вводил)
            'student_final_gamma_submitted': experiment.student_final_gamma, # Ранее введенная студентом финальная гамма
            
            'results_processing_status': results_status, # Статус из Results (pending_student_input, success, fail)
            'debug_mode_for_student_profile': DEBUG_MODE_FOR_STUDENT_PROFILE
        }

        logger.info(f"Student {request.user.email} accessed data for experiment {experiment_id}. Data sample (system_results_per_stage): {response_data.get('system_results_per_stage')}")
        return JsonResponse(response_data)

    except Http404:
        logger.warning(f"Student {request.user.email} - Experiment {experiment_id} not found or access denied (Http404).")
        return JsonResponse({'status': 'error', 'message': 'Эксперимент не найден или у вас нет к нему доступа'}, status=404)
    except Exception as e:
        logger.error(f"Error fetching experiment details for student {request.user.email}, experiment {experiment_id}: {str(e)}", exc_info=True)
        return JsonResponse({'status': 'error', 'message': f'Внутренняя ошибка сервера: {str(e)}'}, status=500)

@login_required
def student_experiment_detail_view(request, experiment_id):
    logger.info(f"Student {request.user.email} (ID: {request.user.id}) attempting to view experiment detail for ID: {experiment_id}")
    try:
        # Сначала получаем эксперимент только по ID
        experiment = get_object_or_404(Experiments, id=experiment_id)
        logger.info(f"Experiment {experiment_id} found. Owner User ID in DB: {experiment.user_id}. Current request.user ID: {request.user.id}")

        # Теперь проверяем, принадлежит ли он текущему пользователю
        if experiment.user != request.user:
            logger.warning(f"Access Denied: Experiment {experiment_id} (owner: {experiment.user_id}) does not belong to student {request.user.email} (ID: {request.user.id}).")
            # Выбрасываем Http404, если эксперимент не принадлежит пользователю
            # Это стандартное поведение, которое должно было быть и раньше, но теперь мы логируем причину точнее.
            raise Http404("Эксперимент не найден или у вас нет к нему доступа.")

        logger.info(f"Experiment {experiment_id} confirmed to belong to student {request.user.email}.")
        return render(request, 'lab_data/student_experiment_page.html', {'experiment_id': experiment_id})
    
    except Http404 as e:
        # Этот блок теперь будет ловить как Http404 от get_object_or_404(Experiments, id=experiment_id)
        # так и Http404, который мы выбрасываем при проверке experiment.user != request.user
        logger.warning(f"Http404 in student_experiment_detail_view for experiment {experiment_id}, user {request.user.email}: {str(e)}")
        # Перевыбрасываем оригинальную ошибку Http404 или кастомную, если необходимо
        # В данном случае, сообщение из raise выше будет более информативным, если проблема в доступе.
        # Если get_object_or_404 не нашел по ID, то будет его стандартное сообщение.
        raise # Перевыбрасываем оригинальную Http404

    except Exception as e:
        logger.error(f"Unexpected error in student_experiment_detail_view for user {request.user.email}, experiment {experiment_id}: {str(e)}", exc_info=True)
        # Для других непредвиденных ошибок можно вернуть более общее сообщение
        raise Http404("Произошла неожиданная ошибка при загрузке страницы эксперимента.")

# Вспомогательная функция для расчета системных значений
def calculate_system_results(stages_data, global_temperature_celsius):
    logger.info(f"Начало calculate_system_results. Температура: {global_temperature_celsius}°C. Этапы: {len(stages_data) if stages_data else 0}")
    # all_calculated_speeds = [] # Больше не нужны для усреднения здесь
    # all_calculated_gammas = [] # Больше не нужны для усреднения здесь
    per_stage_results = [] # Список для хранения результатов каждого этапа

    if not isinstance(stages_data, list):
        logger.error(f"Ошибка: stages_data не является списком: {stages_data}")
        # return None, None # Старый возврат
        return [] # Возвращаем пустой список в случае ошибки

    for i, stage in enumerate(stages_data):
        stage_result = {'speed': None, 'gamma': None} # Результат для текущего этапа
        if not isinstance(stage, dict):
            logger.warning(f"Этап {i+1} не является словарем, пропускается: {stage}")
            per_stage_results.append(stage_result) # Добавляем пустой результат
            continue

        frequency = stage.get('frequency')
        minima_data = stage.get('labels') 
        
        if not minima_data and 'minima' in stage:
             minima_data = stage.get('minima')
             logger.info(f"Этап {i+1}: минимумы взяты из stage.minima")
        elif minima_data:
             logger.info(f"Этап {i+1}: минимумы взяты из stage.labels")
        else:
            logger.warning(f"Этап {i+1}: данные о минимумах (ни labels, ни minima) не найдены. Частота: {frequency}. Данные этапа: {stage}")
            per_stage_results.append(stage_result)
            continue

        if not frequency or not isinstance(minima_data, list) or len(minima_data) < 2:
            logger.warning(f"Этап {i+1}: недостаточно данных (частота: {frequency}, минимумы: {len(minima_data) if minima_data else 0}). Пропускается.")
            per_stage_results.append(stage_result)
            continue
        
        valid_minima_distances = []
        for m_idx, m_val in enumerate(minima_data):
            if isinstance(m_val, dict) and isinstance(m_val.get('distance_m'), (int, float)):
                valid_minima_distances.append(float(m_val['distance_m']))
            else:
                logger.warning(f"Этап {i+1}, минимум {m_idx}: некорректный формат или отсутствует 'distance_m'. Данные: {m_val}")
        
        if len(valid_minima_distances) < 2:
            logger.warning(f"Этап {i+1}: недостаточно валидных минимумов с 'distance_m' ({len(valid_minima_distances)}). Расчет для этапа невозможен.")
            per_stage_results.append(stage_result)
            continue
        
        valid_minima_distances.sort()

        delta_l_values = [valid_minima_distances[k+1] - valid_minima_distances[k] for k in range(len(valid_minima_distances)-1)]
        delta_l_values = [d for d in delta_l_values if d > 1e-9] 

        if not delta_l_values:
            logger.warning(f"Этап {i+1}: не удалось рассчитать валидные delta_L. Пропускается.")
            per_stage_results.append(stage_result)
            continue

        avg_delta_l = sum(delta_l_values) / len(delta_l_values)
        stage_speed = 2 * avg_delta_l * float(frequency)
        stage_gamma = calculate_gamma_value(stage_speed, global_temperature_celsius)

        logger.info(f"Этап {i+1}: Расчет. Частота={frequency} Hz, AvgDeltaL={avg_delta_l:.4f} м, Скорость={stage_speed:.2f} м/с, Гамма={stage_gamma:.4f if stage_gamma is not None else 'N/A'}")

        if stage_speed is not None and stage_speed > 0:
            stage_result['speed'] = stage_speed
        if stage_gamma is not None:
            stage_result['gamma'] = stage_gamma
        
        per_stage_results.append(stage_result)

    # final_avg_speed = (sum(all_calculated_speeds) / len(all_calculated_speeds)) if all_calculated_speeds else None
    # final_avg_gamma = (sum(all_calculated_gammas) / len(all_calculated_gammas)) if all_calculated_gammas else None
    
    # logger.info(f"Итоговые системные расчеты: Средняя скорость={final_avg_speed}, Средняя гамма={final_avg_gamma}")
    # return final_avg_speed, final_avg_gamma # Старый возврат
    logger.info(f"Итоговые поэтапные системные расчеты: {per_stage_results}")
    return per_stage_results # Возвращаем список результатов по этапам

def calculate_gamma_value(v_sound, temperature_celsius):
    """Расчет коэффициента γ по скорости звука и температуре."""
    if v_sound is None or v_sound <= 0 or temperature_celsius is None:
        logger.warning(f"Некорректные входные данные для calculate_gamma_value: v={v_sound}, T={temperature_celsius}")
        return None
    R = 8.314  # Универсальная газовая постоянная Дж/(моль·К)
    mu = 0.029  # Молярная масса воздуха (кг/моль)
    T_kelvin = temperature_celsius + 273.15
    if T_kelvin <= 0:
        logger.warning(f"Некорректная температура в Кельвинах ({T_kelvin} K) для расчета γ.")
        return None
    try:
        gamma = (v_sound ** 2 * mu) / (R * T_kelvin)
        return float(gamma) if not np.isnan(gamma) else None
    except (OverflowError, ZeroDivisionError) as e:
        logger.error(f"Ошибка при расчете gamma: v={v_sound}, T_k={T_kelvin}, {e}")
        return None

@login_required
def protocol_detail_view(request, experiment_id):
    if not request.user.role == 'teacher':
        logger.warning(f"User {request.user.email} (role: {request.user.role}) "
                       f"attempted to access protocol for experiment {experiment_id} without teacher role.")
        return HttpResponseForbidden("Доступ запрещен: только преподаватели могут просматривать протоколы.")

    logger.info(f"Teacher {request.user.email} accessing protocol for experiment_id: {experiment_id}")
    
    try:
        experiment = Experiments.objects.select_related('user', 'results').get(id=experiment_id)
    except Experiments.DoesNotExist:
        logger.error(f"Experiment with id {experiment_id} not found for protocol view.")
        raise Http404("Эксперимент не найден.")

    student = experiment.user
    results = getattr(experiment, 'results', None)

    # Определение статуса для протокола
    protocol_status = "Статус не определен"
    if results:
        if results.status == 'success' or results.status == 'final_completed':
            protocol_status = "Завершен (успешно)"
        elif results.status == 'fail':
            protocol_status = "Провал"
        elif results.status == 'pending_student_input':
            protocol_status = "В процессе выполнения студентом"
        else:
            protocol_status = results.get_status_display() # Для других статусов Results
    elif experiment.status == 'failed':
        protocol_status = "Провал (завершено системой с ошибкой)"
    elif experiment.status == 'completed':
        # Эксперимент завершен лаборантом, но студент еще не предоставил данные
        protocol_status = "Ожидает ввода студента"
    else:
        protocol_status = experiment.get_status_display()


    context = {
        'experiment_id': experiment.id,
        'student_full_name': student.full_name,
        'student_group': student.group_name if student.group_name else "Не указана",
        # Данные по этапам
        'student_speed_stage1': experiment.student_speed_stage1 if experiment.student_speed_stage1 is not None else "Нет данных",
        'student_gamma_stage1': experiment.student_gamma_stage1 if experiment.student_gamma_stage1 is not None else "Нет данных",
        'system_speed_stage1': experiment.system_speed_stage1 if experiment.system_speed_stage1 is not None else "Нет данных",
        'system_gamma_stage1': experiment.system_gamma_stage1 if experiment.system_gamma_stage1 is not None else "Нет данных",
        'error_percent_speed_stage1': experiment.error_percent_speed_stage1 if experiment.error_percent_speed_stage1 is not None else "Нет данных",
        'error_percent_gamma_stage1': experiment.error_percent_gamma_stage1 if experiment.error_percent_gamma_stage1 is not None else "Нет данных",
        
        'student_speed_stage2': experiment.student_speed_stage2 if experiment.student_speed_stage2 is not None else "Нет данных",
        'student_gamma_stage2': experiment.student_gamma_stage2 if experiment.student_gamma_stage2 is not None else "Нет данных",
        'system_speed_stage2': experiment.system_speed_stage2 if experiment.system_speed_stage2 is not None else "Нет данных",
        'system_gamma_stage2': experiment.system_gamma_stage2 if experiment.system_gamma_stage2 is not None else "Нет данных",
        'error_percent_speed_stage2': experiment.error_percent_speed_stage2 if experiment.error_percent_speed_stage2 is not None else "Нет данных",
        'error_percent_gamma_stage2': experiment.error_percent_gamma_stage2 if experiment.error_percent_gamma_stage2 is not None else "Нет данных",
        
        'student_speed_stage3': experiment.student_speed_stage3 if experiment.student_speed_stage3 is not None else "Нет данных",
        'student_gamma_stage3': experiment.student_gamma_stage3 if experiment.student_gamma_stage3 is not None else "Нет данных",
        'system_speed_stage3': experiment.system_speed_stage3 if experiment.system_speed_stage3 is not None else "Нет данных",
        'system_gamma_stage3': experiment.system_gamma_stage3 if experiment.system_gamma_stage3 is not None else "Нет данных",
        'error_percent_speed_stage3': experiment.error_percent_speed_stage3 if experiment.error_percent_speed_stage3 is not None else "Нет данных",
        'error_percent_gamma_stage3': experiment.error_percent_gamma_stage3 if experiment.error_percent_gamma_stage3 is not None else "Нет данных",
        
        # Финальные результаты
        'student_final_gamma': experiment.student_final_gamma if experiment.student_final_gamma is not None else "Нет данных",
        'system_final_gamma': experiment.system_final_gamma if experiment.system_final_gamma is not None else "Нет данных",
        'error_percent_final_gamma': experiment.error_percent_final_gamma if experiment.error_percent_final_gamma is not None else "Нет данных",
        
        'experiment_status_protocol': protocol_status,
        'experiment_creation_date': experiment.created_at,
        'is_teacher': True # Для общего шаблона, если нужно
    }
    
    # Дополнительно передаем сами объекты, если нужны еще какие-то данные в шаблоне
    context['experiment_obj'] = experiment
    context['results_obj'] = results
    
    logger.debug(f"Context for protocol_detail_view (exp_id: {experiment_id}): {context}")

    return render(request, 'lab_data/protocol_detail.html', context)

def logout_view(request):
    """Обрабатывает выход пользователя из системы."""
    user_email = request.user.email if request.user.is_authenticated else 'AnonymousUser'
    auth_logout(request)
    messages.info(request, "Вы успешно вышли из системы.")
    logger.info(f"User {user_email} logged out successfully.")
    return redirect('login_choice') # Или другой URL для страницы входа, например, settings.LOGIN_URL

@login_required
def download_protocol_pdf(request, experiment_id):
    """Скачивание PDF протокола эксперимента"""
    experiment = get_object_or_404(Experiments, id=experiment_id)
    
    # Получаем данные студента из связанной модели User
    student_data = {
        'full_name': experiment.user.full_name,
        'group_name': experiment.user.group_name
    }
    
    # Генерируем PDF
    pdf_content = generate_protocol_pdf(experiment, student_data)
    
    # Создаем HTTP ответ с PDF
    response = HttpResponse(pdf_content, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="protocol_{experiment_id}.pdf"'
    
    return response