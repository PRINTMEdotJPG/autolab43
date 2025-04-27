from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from .models import Users, Experiments, EquipmentData, Results
from .imitate_module.sensors_simulator import ExperimentSimulator
import json
import logging
import random
from typing import Dict, Any

logger = logging.getLogger(__name__)

# Глобальный флаг для переключения режима
USE_SIMULATION = True

def run_simulation(request, user_id: int) -> JsonResponse:
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
            return JsonResponse(
                {'status': 'error', 'message': 'Режим реальных данных не реализован'},
                status=501
            )

        # Сохранение результатов
        experiment = save_experiment_data(user, experiment_data)
        
        # Явное указание типа для response_data
        response_data: Dict[str, Any] = {
            'status': 'success',
            'user_id': user_id,
            'experiment_id': experiment.id,  # Теперь Pylance знает, что experiment имеет атрибут id
            'gamma': experiment_data['gamma_calculated'],
            'error_percent': experiment_data['error_percent'],
            'simulation_used': simulate
        }
        
        return JsonResponse(response_data)

    except Exception as e:
        logger.error(f"Ошибка в run_simulation: {str(e)}", exc_info=True)
        return JsonResponse(
            {'status': 'error', 'message': str(e)},
            status=400
        )

def simulate_experiment(user: Users) -> Dict[str, Any]:
    """Запуск имитации эксперимента с проверкой структуры"""
    simulator = ExperimentSimulator(
        user_id=user.id,
        group_name=user.group_name
    )
    
    experiment_data = simulator.run_experiment()
    
    # Проверка структуры данных
    required_sensor_fields = ['time_ms', 'temperature', 'microphone_signal',
                             'tube_position', 'voltage', 'frequency']
    for item in experiment_data['sensor_data']:
        for field in required_sensor_fields:
            if field not in item:
                raise ValueError(f"Отсутствует поле {field} в sensor_data")
    
    return experiment_data

def save_experiment_data(user: Users, experiment_data: Dict[str, Any]) -> Experiments:
    """Сохранение данных эксперимента в БД"""
    # Проверка наличия обязательных полей
    required_fields = ['temperature', 'gamma_calculated', 'gamma_reference', 
                      'error_percent', 'status', 'sensor_data']
    for field in required_fields:
        if field not in experiment_data:
            raise ValueError(f"Отсутствует обязательное поле: {field}")

    # Проверка структуры sensor_data
    for item in experiment_data['sensor_data']:
        if 'microphone_signal' not in item:
            raise ValueError("Некорректная структура sensor_data: отсутствует microphone_signal")

    # Создание основного объекта эксперимента
    experiment = Experiments.objects.create(
        user=user,
        temperature=experiment_data['temperature'],
        tube_length=1.0
    )
    
    # Пакетное сохранение данных оборудования с проверкой
    equipment_records = []
    for item in experiment_data['sensor_data'][:100]:  # Ограничиваем 100 точками
        try:
            record = EquipmentData(
                experiment=experiment,
                time_ms=item['time_ms'],
                microphone_signal=item['microphone_signal'],
                tube_position=item['tube_position'],
                voltage=item.get('voltage', 5.0)  # Значение по умолчанию
            )
            equipment_records.append(record)
        except KeyError as e:
            logger.warning(f"Пропущена точка данных из-за ошибки: {str(e)}")
            continue
    
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