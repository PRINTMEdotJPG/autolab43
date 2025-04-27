# views.py

from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.models import User
import logging
from .imitate_module.sensors_simulator import ExperimentSimulator
from .models import Experiment, SensorData
from django.db import transaction

# Настройка логирования
logger = logging.getLogger(__name__)

@require_POST
def run_simulation(request, user_id):
    """
    Обработчик API для запуска имитации эксперимента.
    URL: /experiment/<int:user_id>/
    """
    try:
        user = get_object_or_404(User, pk=user_id)
    except Exception as e:
        logger.error(f"Пользователь с id {user_id} не найден")
        return JsonResponse({'status': 'error', 'message': 'Пользователь не найден'}, status=404)

    try:
        # Генерируем случайное имя группы для примера
        group_name = f"Group_{user_id}"

        # Инициализируем симулятор
        simulator = ExperimentSimulator(user_id=user_id, group_name=group_name)
        result = simulator.run_experiment()

        # Сохраняем результаты в БД
        with transaction.atomic():
            experiment = Experiment.objects.create(
                user=user,
                gamma_calculated=result['gamma_calculated'],
                error_percent=result['error_percent'],
                temperature=simulator.temperature,
                frequencies_used=simulator.frequencies_used,
                resonance_positions=result['resonance_positions']
            )

            # Сохраняем первые 100 точек данных для каждого датчика
            sensor_data_objects = []
            for data in result['sensor_data']:
                positions = data['positions'][:100]
                adc_values = data['adc_values'][:100]
                for pos, adc in zip(positions, adc_values):
                    sensor_data = SensorData(
                        experiment=experiment,
                        frequency=data['frequency'],
                        position=pos,
                        adc_value=adc
                    )
                    sensor_data_objects.append(sensor_data)

            SensorData.objects.bulk_create(sensor_data_objects)

        # Формируем ответ
        response_data = {
            'status': 'success',
            'experiment_id': experiment.id,
            'gamma': experiment.gamma_calculated,
            'error_percent': experiment.error_percent,
            'frequencies_used': experiment.frequencies_used,
            'temperature': experiment.temperature,
            'resonance_positions': experiment.resonance_positions
        }
        logger.info(f"Эксперимент {experiment.id} успешно сохранен")
        return JsonResponse(response_data, status=200)

    except Exception as e:
        logger.exception("Ошибка при запуске симуляции эксперимента")
        return JsonResponse({'status': 'error', 'message': 'Внутренняя ошибка сервера'}, status=500)