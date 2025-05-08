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
from django.views.decorators.http import require_http_methods
from django.core.exceptions import PermissionDenied
from typing import Dict, Any, Optional
import json
import logging
import os
from config import config

from .models import User, Experiments, EquipmentData, Results
from .imitate_module.sensors_simulator import ExperimentSimulator
from .forms import StudentLoginForm, TeacherLoginForm, StudentResultForm
from .generate_graphs import (
    generate_gamma_frequency_graph,
    generate_interference_graph,
    generate_signal_time_graph
)

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
    logger.info(f"User {request.user.email} accessed home page")
    context = {}

    if request.user.role == 'student':
        logger.debug("Building context for student view")
        context.update({
            'user': request.user,
            'full_name': request.user.full_name,
            'group_name': request.user.group_name,
            'role': request.user.get_role_display(),
        })
    elif request.user.role == 'teacher':
        logger.debug("Building context for teacher view")
        groups_with_students = []
        groups = User.objects.filter(role='student').values_list(
            'group_name', flat=True
        ).distinct()

        for group in groups:
            students = User.objects.filter(
                role='student',
                group_name=group
            ).order_by('full_name')
            groups_with_students.append({
                'name': group,
                'students': students
            })
            logger.debug(f"Added group {group} with {len(students)} students")

        context.update({
            'groups_with_students': groups_with_students,
            'is_teacher': True,
        })

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
@require_http_methods(["POST"])
def start_experiment(request) -> JsonResponse:
    """
    Запуск лабораторного эксперимента (только для студентов).

    Args:
        request: HttpRequest объект

    Returns:
        JsonResponse: Результат выполнения эксперимента
    """
    try:
        if request.user.role != 'student':
            logger.warning(
                f"User {request.user.email} tried to start experiment without permission"
            )
            return JsonResponse({
                'status': 'error',
                'message': 'Только студенты могут запускать эксперименты'
            }, status=403)

        logger.info(f"Starting experiment for student {request.user.email}")
        simulator = ExperimentSimulator()
        experiment_data = json.loads(simulator.run_experiment())
        logger.debug("Experiment data generated successfully")

        # Валидация данных
        if 'details' not in experiment_data or not isinstance(experiment_data['details'], list):
            error_msg = "Некорректная структура данных эксперимента"
            logger.error(error_msg)
            raise ValueError(error_msg)

        successful_experiment = next(
            (exp for exp in experiment_data['details'] if exp.get('status') == 'success'),
            None
        )

        if not successful_experiment:
            error_msg = "Не удалось получить успешные результаты эксперимента"
            logger.error(error_msg)
            raise ValueError(error_msg)

        if 'sensor_data' not in successful_experiment:
            error_msg = "Отсутствуют данные сенсоров"
            logger.error(error_msg)
            raise ValueError(error_msg)

        # Сохранение эксперимента
        experiment = Experiments.objects.create(
            user=request.user,
            temperature=experiment_data['temperature'],
            tube_length=0.5
        )
        logger.info(f"Experiment {experiment.id} created")

        # Сохранение данных оборудования
        equipment_data = []
        for data_point in successful_experiment['sensor_data'][:1000]:
            equipment_data.append(EquipmentData(
                experiment=experiment,
                time_ms=data_point.get('time_ms', 0),
                microphone_signal=int(data_point.get('microphone_signal', 0)),
                tube_position=data_point.get('tube_position', 0),
                voltage=data_point.get('voltage', 5.0)
            ))

        EquipmentData.objects.bulk_create(equipment_data)
        logger.debug(f"Saved {len(equipment_data)} equipment data points")

        # Сохранение результатов
        Results.objects.create(
            experiment=experiment,
            gamma_calculated=experiment_data['gamma_calculated'],
            gamma_reference=1.4,
            error_percent=experiment_data.get('error_percent', 0),
            status='pending',
            detailed_results=experiment_data
        )
        logger.info("Experiment results saved successfully")

        return JsonResponse({
            'status': 'success',
            'experiment_id': experiment.id,
            'gamma': experiment_data['gamma_calculated'],
            'error_percent': experiment_data.get('error_percent', 0)
        })

    except Exception as e:
        logger.error(
            f"Experiment error: {str(e)}\nData: {experiment_data if 'experiment_data' in locals() else 'N/A'}",
            exc_info=True
        )
        return JsonResponse({
            'status': 'error',
            'message': f'Ошибка проведения эксперимента: {str(e)}'
        }, status=500)


@login_required
def experiment_results(request, experiment_id: int) -> HttpResponse:
    """
    Отображение результатов эксперимента.

    Args:
        request: HttpRequest объект
        experiment_id: ID эксперимента

    Returns:
        HttpResponse: Отрендеренный шаблон results.html
    """
    logger.info(f"Accessing experiment {experiment_id} results")
    experiment = get_object_or_404(Experiments, id=experiment_id)
    
    if experiment.user != request.user and not request.user.is_staff:
        logger.warning(
            f"User {request.user.email} tried to access experiment {experiment_id} without permission"
        )
        raise PermissionDenied

    result = get_object_or_404(Results, experiment=experiment)
    data_points = EquipmentData.objects.filter(
        experiment=experiment
    ).order_by('time_ms')
    logger.debug(f"Retrieved {len(data_points)} data points for experiment")

    # Генерация графиков
    try:
        graphs = {
            'interference_pattern': generate_interference_graph(data_points),
        }
        logger.debug("Graphs generated successfully")
    except Exception as e:
        logger.error(f"Graph generation failed: {str(e)}", exc_info=True)
        graphs = None

    form = StudentResultForm(request.POST or None)
    needs_retry = False

    if request.method == 'POST' and form.is_valid():
        student_gamma = form.cleaned_data['gamma']
        result.student_gamma = student_gamma
        result.student_error = abs(student_gamma - 1.4) / 1.4 * 100
        logger.info(
            f"Student {request.user.email} submitted gamma: {student_gamma:.3f} "
            f"(error: {result.student_error:.2f}%)"
        )

        if result.student_error > 5:
            needs_retry = True
            logger.warning("Student result exceeds 5% error threshold")
            messages.warning(
                request,
                f"Отклонение {result.student_error:.2f}% > 5%. "
                "Пожалуйста, перепроверьте расчеты!"
            )
        else:
            result.status = 'success'
            result.save()
            logger.info("Student result accepted and saved")
            messages.success(request, "Результаты успешно сохранены!")
            return redirect('experiment_results', experiment_id=experiment_id)

    context = {
        'experiment': experiment,
        'result': result,
        'form': form,
        'needs_retry': needs_retry,
        'data_points': data_points[:100],
        'graphs': graphs
    }
    return render(request, 'experiment/results.html', context)


@login_required
def retry_experiment(request, experiment_id: int) -> HttpResponse:
    """
    Сброс эксперимента для повторного прохождения.

    Args:
        request: HttpRequest объект
        experiment_id: ID эксперимента

    Returns:
        HttpResponse: Редирект на home
    """
    experiment = get_object_or_404(Experiments, id=experiment_id)
    if experiment.user != request.user:
        logger.warning(
            f"User {request.user.email} tried to retry experiment {experiment_id} without permission"
        )
        raise PermissionDenied

    logger.info(f"Resetting experiment {experiment_id} by user {request.user.email}")
    experiment.results.delete()
    experiment.delete()
    
    messages.info(request, "Эксперимент сброшен. Можете начать заново.")
    return redirect('home')


class DownloadManualView(View):
    """Представление для скачивания методического пособия."""

    def get(self, request) -> FileResponse:
        """
        Обработка GET-запроса - возврат PDF-файла методички.

        Args:
            request: HttpRequest объект

        Returns:
            FileResponse: PDF файл или 404 ошибка
        """
        if not request.user.is_authenticated:
            logger.warning("Unauthorized manual download attempt")
            return HttpResponseForbidden()

        file_path = config.MANUAL_PDF_PATH
        if os.path.exists(file_path):
            logger.info(f"User {request.user.email} downloaded manual")
            return FileResponse(
                open(file_path, 'rb'),
                content_type='application/pdf'
            )
        
        logger.error(f"Manual not found at {file_path}")
        raise Http404("Методичка не найдена")
    
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