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
from django.contrib.auth import login as authenticate
from django.contrib.auth import get_user_model
from typing import Dict, Any, Optional
import json
import logging
import os
from config import config


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

@login_required
@require_http_methods(["POST"])
def save_experiment_results(request, experiment_id):
    try:
        experiment = Experiments.objects.get(id=experiment_id, user=request.user)
        data = json.loads(request.body)
        
        # Проверка обязательных полей
        final_results = data.get('final_results', {})
        if not all(k in final_results for k in ['system_speed', 'system_gamma', 'student_speed', 'student_gamma']):
            return JsonResponse({
                'status': 'error',
                'message': 'Missing required fields in final_results'
            }, status=400)

        # Обновляем эксперимент
        experiment.student_speed = float(final_results['student_speed'])
        experiment.student_gamma = float(final_results['student_gamma'])
        experiment.system_gamma = float(final_results['system_gamma'])
        experiment.error_percent = float(final_results.get('error_percent', 0))
        experiment.status = 'completed'
        experiment.save()

        # Обновляем или создаем результаты
        Results.objects.update_or_create(
            experiment=experiment,
            defaults={
                'gamma_calculated': float(final_results['system_gamma']),
                'gamma_reference': 1.4,
                'student_gamma': float(final_results['student_gamma']),
                'error_percent': float(final_results.get('error_percent', 0)),
                'status': 'completed',
                'detailed_results': data.get('steps', []),
                'visualization_data': data.get('charts_data', {})
            }
        )
        
        return JsonResponse({'status': 'success'})
    
    except Exception as e:
        logger.error(f"Error saving results: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)
    
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

def generate_protocol_pdf(experiment, student):
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
    p.drawString(margin, y_position, f"Студент: {student.full_name}")
    y_position -= line_height
    p.drawString(margin, y_position, f"Группа: {student.group_name}")
    
    # 3. Параметры эксперимента
    y_position -= line_height * 1.5
    p.setFont("DejaVu", 14)
    p.drawString(margin, y_position, "Параметры эксперимента:")
    
    p.setFont("DejaVu", 12)
    y_position -= line_height
    p.drawString(margin, y_position, f"Температура: {experiment.temperature} °C")
    y_position -= line_height
    p.drawString(margin, y_position, f"Частота: {experiment.frequency} Гц")
    
    # 4. Результаты эксперимента
    y_position -= line_height * 1.5
    p.setFont("DejaVu", 14)
    p.drawString(margin, y_position, "Результаты:")
    
    # Таблица результатов
    results = [
        ("Параметр", "Значение"),
        ("Скорость звука", f"{experiment.student_speed or '-'} м/с"),
        ("Коэффициент γ", f"{experiment.student_gamma or '-'}"),
        ("Ошибка", f"{experiment.error_percent or '-'}%")
    ]
    
    p.setFont("DejaVu", 12)
    for row in results:
        y_position -= line_height
        p.drawString(margin, y_position, row[0])
        p.drawString(margin + 6*cm, y_position, row[1])
    
    # 5. Подпись и дата
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
    if request.user.role != 'student':
        return JsonResponse({'status': 'error', 'message': 'Доступ запрещен'}, status=403)
    
    experiments = Experiments.objects.filter(user=request.user).values(
        'id', 'created_at', 'status', 'assistant__full_name'
    )
    return JsonResponse({'experiments': list(experiments)})



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
def home_view(request):
    context = {}
    
    if request.user.role == 'assistant':
        logger.info(f"Assistant {request.user.email} accessed home page")
        context['active_experiments'] = Experiments.objects.filter(
            assistant=request.user,
            status__in=['preparing', 'stage_1', 'stage_2', 'stage_3']
        ).select_related('user')
        context['students'] = User.objects.filter(role='student').order_by('full_name')
        logger.info(f"Found {len(context['active_experiments'])} active experiments")

    return render(request, 'home.html', context)

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

        experiment.status = 'completed'
        experiment.save()
        return JsonResponse({'status': 'success'})

    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)