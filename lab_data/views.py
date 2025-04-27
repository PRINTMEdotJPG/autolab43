# views.py

from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.models import User
import logging
from .imitate_module.sensors_simulator import ExperimentSimulator
from .models import Experiments, EquipmentData, Results
from django.db import transaction
from django.core.validators import MinValueValidator, MaxValueValidator

# Настройка логирования
logger = logging.getLogger(__name__)

@require_POST
def run_simulation(request, user_id):
    """
    Обработчик API для запуска имитации эксперимента.
    URL: /experiment/<int:user_id>/
    """
    try:
        # Получаем пользователя или возвращаем 404
        user = get_object_or_404(User, pk=user_id)
    except Exception as e:
        logger.error(f"Пользователь с id {user_id} не найден")
        return JsonResponse({'status': 'error', 'message': 'Пользователь не найден'}, status=404)

    try:
        # Инициализируем симулятор эксперимента
        group_name = user.groups.first().name if user.groups.exists() else "DefaultGroup"
        simulator = ExperimentSimulator(user_id=user_id, group_name=group_name)
        result = simulator.run_experiment()

        # Начинаем транзакцию для сохранения данных
        with transaction.atomic():
            # Создаем запись эксперимента
            experiment = Experiments.objects.create(
                user=user,
                temperature=result['temperature'],
                tube_length=simulator.arduino.tube_length  # добавьте tube_length в VirtualArduino
            )

            # Сохраняем данные оборудования
            equipment_data_objects = []
            time_ms = 0  # Начальное время
            time_step = 10  # Шаг времени между измерениями в миллисекундах

            for data in result['sensor_data']:
                frequency = data['frequency']
                positions = data['positions'][:100]  # Берем первые 100 точек
                adc_values = data['adc_values'][:100]
                voltage = simulator.arduino.voltage  # Добавьте voltage в VirtualArduino

                for pos, adc in zip(positions, adc_values):
                    equipment_data = EquipmentData(
                        experiment=experiment,
                        time_ms=time_ms,
                        microphone_signal=int(adc),
                        tube_position=pos,
                        voltage=voltage
                    )
                    equipment_data_objects.append(equipment_data)
                    time_ms += time_step  # Увеличиваем время

            # Сохраняем данные в базу данных
            EquipmentData.objects.bulk_create(equipment_data_objects)

            # Сохраняем результаты эксперимента
            gamma_reference = 1.4  # Эталонное значение γ
            gamma_calculated = result['gamma_calculated']
            error_percent = result['error_percent']
            status = 'success' if error_percent <= 5 else 'fail'

            results = Results.objects.create(
                experiment=experiment,
                gamma_calculated=gamma_calculated,
                gamma_reference=gamma_reference,
                error_percent=error_percent,
                status=status,
                detailed_results=result
            )

        # Формируем ответ
        response_data = {
            'status': status,
            'experiment_id': experiment.id,
            'gamma': gamma_calculated,
            'error_percent': error_percent,
            'frequencies_used': simulator.frequencies_used,
            'temperature': result['temperature'],
            'resonance_positions': result['resonance_positions']
        }
        logger.info(f"Эксперимент {experiment.id} успешно сохранен")
        return JsonResponse(response_data, status=200)

    except Exception as e:
        logger.exception("Ошибка при запуске симуляции эксперимента")
        return JsonResponse({'status': 'error', 'message': 'Внутренняя ошибка сервера'}, status=500)