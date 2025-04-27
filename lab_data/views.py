from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from .models import Users, Experiments, EquipmentData, Results
from .imitate_module.sensors_simulator import ExperimentSimulator  # Импорт модуля симуляции
import json
import logging

logger = logging.getLogger(__name__)

# Глобальный флаг для переключения режима
USE_SIMULATION = True  # Переключение между реальными и имитированными данными

def run_simulation(request, user_id):
    """
    Обработчик эксперимента с поддержкой переключения режимов
    GET /simexp/<user_id>/?simulate=false для отключения симуляции
    """
    try:
        # Проверка и парсинг параметров
        simulate = request.GET.get('simulate', str(USE_SIMULATION)).lower() == 'true'
        user = get_object_or_404(Users, id=user_id)
        
        # Генерация или получение данных
        if simulate:
            experiment_data = simulate_experiment(user)
        else:
            # Здесь можно добавить логику для реальных данных
            return JsonResponse(
                {'status': 'error', 'message': 'Режим реальных данных не реализован'},
                status=501
            )

        # Сохранение результатов
        experiment = save_experiment_data(user, experiment_data)
        
        return JsonResponse({
            'status': 'success',
            'user_id': user.id,
            'experiment_id': experiment.id,
            'gamma': experiment_data['gamma_calculated'],
            'error_percent': experiment_data['error_percent'],
            'simulation_used': simulate
        })

    except Exception as e:
        logger.error(f"Ошибка в run_simulation: {str(e)}", exc_info=True)
        return JsonResponse(
            {'status': 'error', 'message': str(e)},
            status=400
        )

def simulate_experiment(user):
    """Запуск имитации эксперимента с реалистичными параметрами"""
    simulator = ExperimentSimulator(
        user_id=user.id,
        group_name=user.group_name
    )
    
    # Генерация случайных но реалистичных частот
    base_freq = random.choice([1500, 2000, 2500, 3000])
    frequencies = [
        base_freq,
        base_freq + random.randint(500, 1000),
        base_freq + random.randint(1000, 2000)
    ]
    
    return simulator.run_experiment(frequencies=frequencies)

def save_experiment_data(user, experiment_data):
    """Сохранение данных эксперимента в БД"""
    # Создание основного объекта эксперимента
    experiment = Experiments.objects.create(
        user=user,
        temperature=experiment_data['temperature'],
        tube_length=1.0
    )
    
    # Пакетное сохранение данных оборудования
    equipment_records = [
        EquipmentData(
            experiment=experiment,
            time_ms=item['time_ms'],
            microphone_signal=item['microphone_signal'],
            tube_position=item['tube_position'],
            voltage=item.get('voltage', 5.0)
        ) for item in experiment_data['sensor_data'][:100]  # Сохраняем первые 100 точек
    ]
    EquipmentData.objects.bulk_create(equipment_records)
    
    # Сохранение результатов
    Results.objects.create(
        experiment=experiment,
        gamma_calculated=experiment_data['gamma_calculated'],
        gamma_reference=experiment_data['gamma_reference'],
        error_percent=experiment_data['error_percent'],
        status=experiment_data['status'],
        detailed_results=experiment_data
    )
    
    return experiment