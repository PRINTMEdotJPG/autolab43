import json
import logging
import base64
import numpy as np
from channels.generic.websocket import AsyncWebsocketConsumer
from scipy.io import wavfile
from scipy.signal import hilbert, find_peaks, butter, filtfilt
import io
import os
from pydub import AudioSegment
import asyncio
import matplotlib.pyplot as plt
from channels.db import database_sync_to_async
from lab_data.models import Experiments, Results

# Настройка логгера
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

class AudioConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer для обработки аудиоданных и данных о расстояниях в реальном времени.
    
    Обрабатывает:
    - Параметры эксперимента (частота, температура)
    - Аудиоданные в формате WebM/Opus
    - Данные о расстоянии от датчика HC-SR04
    - Валидацию результатов эксперимента
    """

    def __init__(self):
        """Инициализация потребителя с параметрами по умолчанию."""
        super().__init__()
        
        logger.info("Инициализация AudioConsumer")
        
        # Параметры аудио обработки
        self.sample_rate = 48000
        self.experiment_steps = []
        self.current_step = 0
        self.max_steps = 3
        self.experiment_id = None
        self.experiment = None
        
        # Параметры поиска минимумов
        self.minima_params = {
            'min_amplitude': 0.3,       # Минимальная нормализованная амплитуда для пика в инвертированном сигнале (0-1)
            'min_distance_ratio': 0.03, # Минимальное относительное расстояние между пиками (доля от общего числа точек)
            'min_prominence': 0.15,     # Минимальная выраженность пика (насколько он выделяется)
            'min_width_ratio': 0.01,    # Минимальная относительная ширина пика
            'min_time_separation_s': 0.015 # Минимальное время между минимумами в секундах (для _find_minima_by_signal)
        }
        
        logger.debug(
            "Параметры инициализации:\\n"
            f"  Частота дискретизации: {self.sample_rate} Гц\\n"
            f"  Макс. шагов эксперимента: {self.max_steps}\\n"
            f"  Параметры поиска минимумов: {self.minima_params}"
        )
        
        self.connected = False
        self.lock = asyncio.Lock()
        
        # Данные о расстояниях - теперь будут храниться в self.experiment_steps для каждого шага
        
        logger.info("Запуск тестовой обработки аудио")
        asyncio.create_task(self.test_audio_processing())

    async def connect(self):
        """Обработчик установки WebSocket соединения."""
        self.experiment_id = self.scope['url_route']['kwargs']['experiment_id']
        try:
            self.experiment = await database_sync_to_async(Experiments.objects.select_related('user').get)(id=self.experiment_id)
            logger.info(f"Эксперимент {self.experiment_id} загружен для пользователя {self.experiment.user.full_name}")

            self.experiment_steps = self.experiment.stages if isinstance(self.experiment.stages, list) else []
            if not self.experiment_steps or len(self.experiment_steps) != self.max_steps:
                logger.warning(f"Данные этапов в БД для эксперимента {self.experiment_id} некорректны или отсутствуют. Инициализация {self.max_steps} пустыми этапами.")
                self.experiment_steps = [{"frequency": None, "temperature": self.experiment.temperature, "status": "pending", "minima": None, "audio_samples": None} for _ in range(self.max_steps)]
                if not self.experiment.stages: # Сохраняем только если stages был пуст
                    self.experiment.stages = self.experiment_steps
                    await database_sync_to_async(self.experiment.save)()
            else:
                for i in range(len(self.experiment_steps)):
                    if not isinstance(self.experiment_steps[i], dict):
                        self.experiment_steps[i] = {} 
                    self.experiment_steps[i].setdefault('frequency', None)
                    self.experiment_steps[i].setdefault('temperature', self.experiment.temperature)
                    self.experiment_steps[i].setdefault('status', 'pending')
                    self.experiment_steps[i].setdefault('minima', None)
                    self.experiment_steps[i].setdefault('audio_samples', None)


            self.current_step = self.experiment.step if self.experiment.step and 1 <= self.experiment.step <= self.max_steps else 1
            
            logger.info(f"Состояние из БД: current_step={self.current_step}, experiment_steps инициализированы ({len(self.experiment_steps)} этапов).")

        except Experiments.DoesNotExist:
            logger.error(f"Эксперимент с ID {self.experiment_id} не найден в БД.")
            await self.close()
            return
        except Exception as e:
            logger.error(f"Ошибка при загрузке эксперимента {self.experiment_id} из БД: {str(e)}", exc_info=True)
            await self.close()
            return

        await self.accept()
        self.connected = True
        logger.info(
            f"Установлено новое WebSocket соединение для эксперимента {self.experiment_id}\\n"
            f"  Текущее состояние: connected={self.connected}\\n"
            f"  Текущий шаг из БД: {self.current_step}")

    async def disconnect(self, close_code):
        """Обработчик закрытия соединения."""
        self.connected = False
        logger.info(
            "Соединение закрыто\\n"
            f"  Код закрытия: {close_code}\\n"
            f"  Текущее состояние: connected={self.connected}"
        )

    async def receive(self, text_data):
        """Основной обработчик входящих сообщений."""
        try:
            logger.info(
                "Получено новое сообщение\\n"
                f"  Длина сообщения: {len(text_data)} байт\\n"
                f"  Текущий шаг: {self.current_step}"
            )
            
            try:
                data = json.loads(text_data)
                logger.debug("Сообщение успешно декодировано из JSON")
            except json.JSONDecodeError as e:
                logger.error(
                    "Ошибка декодирования JSON\\n"
                    f"  Ошибка: {str(e)}\\n"
                    f"  Содержимое: {text_data[:100]}..."
                )
                await self.send_error("Неверный формат JSON")
                return

            if not isinstance(data, dict):
                logger.error(
                    "Некорректный формат данных\\n"
                    f"  Тип данных: {type(data)}\\n"
                    f"  Содержимое: {data}"
                )
                await self.send_error("Ожидается JSON объект")
                return

            message_type = data.get('type')
            if not message_type:
                logger.error(
                    "Отсутствует тип сообщения\\n"
                    f"  Доступные ключи: {list(data.keys())}"
                )
                await self.send_error("Требуется поле 'type'")
                return

            logger.info(
                f"Обработка сообщения типа '{message_type}'\\n"
                f"  Шаг эксперимента: {data.get('step', 'не указан')}"
            )

            handlers = {
                'complete_audio': self.process_complete_audio,
                'experiment_params': self.handle_experiment_params,
                'final_results': self.validate_final_results,
                # 'distance_data': self.handle_distance_data, # Удалено
                'start_recording': self.handle_start_recording,
                'stop_recording': self.handle_stop_recording,
                'finalize_experiment': self.handle_finalize_experiment, # Добавлено для кнопки "Завершить эксперимент"
                'update_all_params': self.handle_update_all_params, # Добавлено для кнопки "Сохранить параметры"
            }

            handler = handlers.get(message_type) # Не передаем self.handle_unknown_type как default
            
            if handler:
                async with self.lock:
                    logger.debug(f"Выполнение обработчика для типа '{message_type}'")
                    await handler(data)
            else: # Явно обрабатываем неизвестный тип
                await self.handle_unknown_type(data)


        except Exception as e:
            logger.error(
                "Критическая ошибка обработки сообщения\\n"
                f"  Тип ошибки: {type(e).__name__}\\n"
                f"  Сообщение: {str(e)}\\n"
                "  Трассировка:", exc_info=True
            )
            await self.send_error(f"Ошибка обработки: {str(e)}")

    async def handle_unknown_type(self, data):
        """Обработчик для неизвестных типов сообщений."""
        try:
            message_type = data.get('type', 'не указан')
            
            logger.warning(
                "Получено сообщение неизвестного типа\\n"
                f"  Полученный тип: '{message_type}'\\n"
                f"  Доступные ключи в сообщении: {list(data.keys())}\\n"
                f"  Текущий шаг эксперимента: {self.current_step}"
            )
            
            error_message = (
                f"Неизвестный тип сообщения: '{message_type}'. "
                f"Ожидается один из: 'experiment_params', 'complete_audio', "
                "'final_results', 'start_recording', 'stop_recording', 'finalize_experiment', 'update_all_params'"
            )
            
            await self.send_error(error_message)
            
        except Exception as e:
            logger.error(
                "Ошибка при обработке неизвестного типа сообщения\\n"
                f"  Тип ошибки: {type(e).__name__}\\n"
                f"  Сообщение: {str(e)}\\n"
                f"  Данные сообщения: {data}\\n"
                "  Трассировка:", exc_info=True
            )
            await self.send_error("Внутренняя ошибка при обработке сообщения")

    async def handle_experiment_params(self, data):
        """Обработчик параметров эксперимента."""
        try:
            logger.info("Начало обработки параметров эксперимента")
            
            step = data.get('step')
            frequency = data.get('frequency')
            temperature = data.get('temperature')
            
            logger.debug(
                "Полученные параметры:\\n"
                f"  Шаг: {step}\\n"
                f"  Частота: {frequency} Гц\\n"
                f"  Температура: {temperature}°C"
            )

            if None in (step, frequency, temperature) or not isinstance(step, int):
                logger.error(f"Отсутствуют или некорректные обязательные параметры: step={step}, frequency={frequency}, temperature={temperature}")
                await self.send_error("Требуются: step (int), frequency (float), temperature (float)")
                return

            if not isinstance(frequency, (int, float)) or frequency <= 0:
                logger.error(f"Некорректная частота: {frequency}")
                await self.send_error("Частота должна быть положительным числом")
                return

            if not isinstance(temperature, (int, float)): # Диапазон температур проверяется на клиенте
                logger.error(f"Некорректная температура: {temperature}")
                await self.send_error("Температура должна быть числом")
                return

            step_index = step - 1
            if not (0 <= step_index < len(self.experiment_steps)):
                logger.error(f"Некорректный номер шага {step}. Допустимо от 1 до {len(self.experiment_steps)}")
                await self.send_error(f"Некорректный номер шага. Доступно этапов: {len(self.experiment_steps)}")
                return

            self.experiment_steps[step_index].update({
                'frequency': float(frequency),
                'temperature': float(temperature),
                'status': 'params_received' # Статус обновлен
            })
            
            self.current_step = step # Обновляем текущий активный шаг
            logger.info(f"Текущий шаг обновлен (локально): {self.current_step}")

            self.experiment.temperature = float(temperature) # Общая температура эксперимента
            self.experiment.stages = self.experiment_steps # Обновляем все этапы
            self.experiment.step = self.current_step # Сохраняем активный шаг
            
            await database_sync_to_async(self.experiment.save)()
            logger.info(f"Параметры для шага {step} сохранены в БД для эксперимента {self.experiment_id}")

            confirmation = {
                'type': 'step_confirmation', # Тип подтверждения для клиента
                'step': step,
                'status': 'params_ok_ready_for_recording', # Более ясный статус
                'frequency': float(frequency),
                'temperature': float(temperature)
            }
            
            await self.send_json(confirmation)
            logger.info("Подтверждение получения параметров шага успешно отправлено клиенту.")

        except ValueError as e: # Ошибки преобразования float()
            logger.error(f"Ошибка формата параметров: {str(e)}\\nДанные: {data}", exc_info=True)
            await self.send_error("Ошибка формата числовых параметров (частота/температура).")
        except Exception as e:
            logger.error(f"Ошибка обработки параметров эксперимента: {type(e).__name__} - {str(e)}", exc_info=True)
            await self.send_error(f"Внутренняя ошибка обработки параметров: {str(e)}")


    async def process_complete_audio(self, data):
        """Модифицированный обработчик аудио с интеграцией данных о расстоянии."""
        try:
            step = data.get('step')
            audio_data_b64 = data.get('data')
            distances_cm = data.get('distances', []) 
            timestamps = data.get('timestamps', [])
            
            if not (step and isinstance(step, int) and 0 < step <= len(self.experiment_steps)):
                logger.error(f"Некорректный или отсутствующий номер шага: {step}. Доступно этапов: {len(self.experiment_steps)}")
                await self.send_error("Некорректный или отсутствующий номер шага")
                return
            
            if not audio_data_b64:
                logger.error("Отсутствуют аудио данные (data).")
                await self.send_error("Требуются аудио данные (data)")
                return

            step_index = step - 1
            logger.info(f"Обработка аудио для шага {step}")

            if not distances_cm or not timestamps:
                logger.warning(f"Шаг {step}: Отсутствуют данные о расстоянии (distances_cm или timestamps). Поиск минимумов будет выполнен только по аудиосигналу.")

            try:
                audio_bytes = base64.b64decode(audio_data_b64)
                logger.debug(f"Декодировано {len(audio_bytes)} байт аудио")
                
                samples, decoded_sample_rate = await self.decode_audio(audio_bytes, data.get('format', 'webm'))
                self.sample_rate = decoded_sample_rate 
                filtered_samples = self.apply_butterworth_filter(samples, self.sample_rate)
                
                minima = self.find_minima(filtered_samples, self.sample_rate, distances_cm, timestamps, step)
                
                if not isinstance(self.experiment_steps[step_index], dict):
                     self.experiment_steps[step_index] = {}

                self.experiment_steps[step_index].update({
                    'audio_samples': samples.tolist() if samples is not None else None, 
                    'minima': minima, 
                    'status': 'audio_processed',
                    'distance_samples_cm': distances_cm, 
                    'distance_timestamps': timestamps
                })

                current_step_params = self.experiment_steps[step_index]
                if current_step_params.get('status') not in ['params_received', 'audio_processed']:
                    fallback_frequency = data.get('frequency')
                    fallback_temperature = data.get('temperature')
                    if fallback_frequency is not None and fallback_temperature is not None:
                        logger.warning(f"Параметры для шага {step} не были предварительно установлены, используем из сообщения complete_audio: f={fallback_frequency}, t={fallback_temperature}")
                        current_step_params['frequency'] = float(fallback_frequency)
                        current_step_params['temperature'] = float(fallback_temperature)
                    else:
                        logger.error(f"Параметры для шага {step} не были установлены, и отсутствуют в сообщении complete_audio. Этап: {current_step_params}")
                        await self.send_error(f"Параметры для шага {step} не установлены.")
                        return
                
                if current_step_params.get('frequency') is None and data.get('frequency') is not None:
                    current_step_params['frequency'] = float(data.get('frequency'))
                if current_step_params.get('temperature') is None and data.get('temperature') is not None:
                     current_step_params['temperature'] = float(data.get('temperature'))

                if current_step_params.get('frequency') is None or current_step_params.get('temperature') is None:
                    logger.error(f"КРИТИЧЕСКИ: Частота или температура не установлены для шага {step} после всех проверок.")
                    await self.send_error(f"Не удалось определить частоту/температуру для шага {step}.")
                    return

                # Сохраняем обновленные этапы в БД
                self.experiment.stages = self.experiment_steps
                await database_sync_to_async(self.experiment.save)()
                logger.info(f"Данные шага {step} (включая аудио, минимумы, расстояния) сохранены в БД.")

                response = {
                    'type': 'minima_data',
                    'step': int(step),
                    'minima': minima, 
                    'frequency': float(current_step_params['frequency']),
                    'temperature': float(current_step_params['temperature'])
                }
                
                await self.send_json(response)

                all_steps_processed = all(
                    s_idx < len(self.experiment_steps) and 
                    isinstance(self.experiment_steps[s_idx], dict) and 
                    self.experiment_steps[s_idx].get('status') == 'audio_processed'
                    for s_idx in range(self.max_steps)
                )
                
                if step == self.max_steps and all_steps_processed:
                    logger.info(f"Все {self.max_steps} шагов обработаны. Запускаем расчет финальных результатов.")
                    await self.calculate_final_results()
                elif step == self.max_steps:
                    logger.info(f"Это был последний шаг ({step}), но не все предыдущие шаги имеют статус 'audio_processed'. Финальные результаты пока не рассчитываются.")
                    for s_idx, s_data_log in enumerate(self.experiment_steps):
                         logger.info(f"Статус шага {s_idx+1}: {s_data_log.get('status') if isinstance(s_data_log, dict) else 'Не словарь'}")


            except ValueError as e: 
                logger.error(f"Ошибка обработки аудио (ValueError): {str(e)}", exc_info=True)
                await self.send_error(f"Ошибка обработки аудио: {str(e)}")
            except Exception as e: 
                logger.error(f"Неожиданная ошибка при обработке аудио шага {step}: {type(e).__name__} - {str(e)}", exc_info=True)
                await self.send_error(f"Внутренняя ошибка обработки аудио: {str(e)}")

        except Exception as e: 
            logger.error(f"Критическая ошибка в process_complete_audio для шага {data.get('step', 'N/A')}: {type(e).__name__} - {str(e)}", exc_info=True)
            await self.send_error(f"Общая ошибка обработки аудио: {str(e)}")


    async def calculate_final_results(self):
        """Расчет и сохранение финальных результатов эксперимента."""
        try:
            logger.info("Начало расчета финальных результатов эксперимента...")
            
            results_summary = [] 
            all_steps_valid_for_calc = True

            for idx, step_data in enumerate(self.experiment_steps):
                step_num = idx + 1
                if not isinstance(step_data, dict) or step_data.get('status') != 'audio_processed':
                    logger.warning(f"Шаг {step_num} не готов для финального расчета (статус: {step_data.get('status', 'N/A') if isinstance(step_data, dict) else 'Не словарь'}).")
                    all_steps_valid_for_calc = False
                    continue # Пропускаем этот шаг, но не прерываем для других

                minima_for_step = step_data.get('minima')
                if not minima_for_step or len(minima_for_step) < 2:
                    logger.warning(f"Недостаточно минимумов для шага {step_num} ({len(minima_for_step) if minima_for_step else 0}). Расчет для этого шага невозможен.")
                    step_data.update({'system_speed': float('nan'), 'system_gamma': float('nan')}) # Помечаем как NaN
                    all_steps_valid_for_calc = False
                    continue

                frequency = step_data.get('frequency')
                temperature = step_data.get('temperature')

                if frequency is None or temperature is None:
                    logger.warning(f"Отсутствует частота или температура для шага {step_num}. Расчет невозможен.")
                    step_data.update({'system_speed': float('nan'), 'system_gamma': float('nan')})
                    all_steps_valid_for_calc = False
                    continue
                
                # `calculate_speed` ожидает список словарей минимумов, где каждый содержит `time_sec`
                # `calculate_gamma` ожидает скорость и температуру
                raw_speed = self.calculate_speed(minima_for_step, float(frequency))
                
                # Логика коррекции скорости на движение (avg_speed_movement_m_s) была сложной и не до конца ясной.
                # Пока упростим: corrected_speed = raw_speed. Если find_minima уже учитывает движение, это ОК.
                # Если нужна более сложная коррекция, ее нужно будет реализовать здесь.
                corrected_speed_m_s = raw_speed 
                
                gamma = self.calculate_gamma(corrected_speed_m_s, float(temperature))
                
                step_data.update({
                    'system_speed': corrected_speed_m_s,
                    'system_gamma': gamma,
                    'raw_speed': raw_speed, 
                })
                
                results_summary.append({
                    'step': step_num,
                    'speed': round(corrected_speed_m_s, 4) if not np.isnan(corrected_speed_m_s) else None,
                    'gamma': round(gamma, 4) if not np.isnan(gamma) else None,
                    'raw_speed': round(raw_speed, 4) if not np.isnan(raw_speed) else None,
                })

            if not all_steps_valid_for_calc:
                 logger.warning("Не все шаги были валидны для расчета. Финальные результаты могут быть неполными или отсутствовать.")
            
            # Обновляем stages в модели Experiment перед сохранением
            self.experiment.stages = self.experiment_steps 
            
            # Статус эксперимента и сохранение Results
            # Если хотя бы один шаг был успешно посчитан (не NaN)
            valid_gammas = [s.get('system_gamma') for s in self.experiment_steps if isinstance(s, dict) and s.get('system_gamma') is not None and not np.isnan(s.get('system_gamma'))]
            
            if valid_gammas:
                avg_system_gamma = np.mean(valid_gammas)
                self.experiment.status = 'completed' # Эксперимент считается завершенным лаборантом
                logger.info(f"Эксперимент {self.experiment.id} успешно завершен. Средний γ = {avg_system_gamma:.4f}")
                
                results_defaults = {
                    'detailed_results': self.experiment_steps, 
                    'status': 'pending_student_input', 
                    'gamma_calculated': float(avg_system_gamma), 
                    'student_gamma': None, 
                    'student_speed': None, 
                    'error_percent': None  
                }
                await database_sync_to_async(Results.objects.update_or_create)(
                    experiment=self.experiment,
                    defaults=results_defaults
                )
                logger.info(f"Запись в Results для эксперимента {self.experiment.id} создана/обновлена.")
            else:
                avg_system_gamma = float('nan') # Или 0.0, или None
                self.experiment.status = 'error_in_calculation' # Или другой статус, указывающий на проблему
                logger.error(f"Не удалось рассчитать γ ни для одного шага эксперимента {self.experiment.id}. Статус: {self.experiment.status}")
                 # Results можно не создавать или создать с ошибкой

            await database_sync_to_async(self.experiment.save)() # Сохраняем основной эксперимент с обновленным статусом и этапами
            logger.info(f"Финальный статус эксперимента {self.experiment.id} ({self.experiment.status}) и обновленные этапы сохранены в БД.")

            final_response_message = {
                'type': 'experiment_complete', # Сигнал клиенту, что все завершено со стороны сервера
                'message': f'Эксперимент завершен. Статус: {self.experiment.status}. Средний γ (расч.): {avg_system_gamma:.4f if not np.isnan(avg_system_gamma) else "N/A"}',
                'steps_results': results_summary, # Отправляем только сводку
                'average_gamma': float(avg_system_gamma) if not np.isnan(avg_system_gamma) else None
            }
            await self.send_json(final_response_message)

        except Exception as e:
            logger.error(f"Критическая ошибка при расчете финальных результатов: {type(e).__name__} - {str(e)}", exc_info=True)
            await self.send_error(f"Ошибка расчета финальных результатов: {str(e)}")


    async def handle_finalize_experiment(self, data):
        """Обработчик принудительного завершения эксперимента по команде от клиента."""
        try:
            logger.info(f"Получена команда finalize_experiment для эксперимента {self.experiment_id}")
            
            # Проверяем, есть ли уже результаты, которые можно считать финальными
            # Если нет, можно пометить эксперимент как "завершен принудительно" или "неполный"
            # и рассчитать то, что можно.

            # Попытаемся рассчитать финальные результаты из того, что есть
            await self.calculate_final_results() 
            # calculate_final_results сам отправит 'experiment_complete' или ошибку

            # Если calculate_final_results не отправил experiment_complete (например, из-за ошибок),
            # можно отправить кастомное сообщение здесь.
            # Но обычно calculate_final_results должен покрывать все случаи.

        except Exception as e:
            logger.error(f"Ошибка при обработке finalize_experiment: {type(e).__name__} - {str(e)}", exc_info=True)
            await self.send_error(f"Ошибка при завершении эксперимента: {str(e)}")


    async def handle_update_all_params(self, data):
        """Обработчик для сохранения всех параметров всех этапов."""
        try:
            logger.info(f"Получена команда update_all_params для эксперимента {self.experiment_id}")
            
            global_temperature = data.get('temperature')
            stages_data = data.get('stages') # Ожидается список словарей [{step: 1, frequency: X}, ...]

            if global_temperature is None or stages_data is None:
                await self.send_error("Для update_all_params требуются 'temperature' и 'stages'.")
                return
            
            try:
                self.experiment.temperature = float(global_temperature)
            except ValueError:
                await self.send_error("Некорректное значение общей температуры.")
                return

            updated_any_stage = False
            for stage_info in stages_data:
                step = stage_info.get('step')
                frequency = stage_info.get('frequency')
                
                if step is None or frequency is None:
                    logger.warning(f"Пропущен этап в update_all_params: отсутствует step или frequency. Данные: {stage_info}")
                    continue
                
                try:
                    step_idx = int(step) - 1
                    freq_val = float(frequency)
                except ValueError:
                    logger.warning(f"Некорректные данные для этапа в update_all_params: step={step}, freq={frequency}")
                    continue

                if 0 <= step_idx < len(self.experiment_steps):
                    if not isinstance(self.experiment_steps[step_idx], dict): # На всякий случай
                        self.experiment_steps[step_idx] = {}
                    
                    self.experiment_steps[step_idx]['frequency'] = freq_val
                    self.experiment_steps[step_idx]['temperature'] = self.experiment.temperature # Используем общую температуру
                    # Можно обновить и статус, если это необходимо, например, на 'params_received'
                    # if self.experiment_steps[step_idx].get('status') == 'pending':
                    # self.experiment_steps[step_idx]['status'] = 'params_received'
                    updated_any_stage = True
                else:
                    logger.warning(f"Некорректный номер этапа {step} в update_all_params.")
            
            if updated_any_stage:
                self.experiment.stages = self.experiment_steps
                await database_sync_to_async(self.experiment.save)()
                logger.info(f"Все параметры этапов обновлены и сохранены в БД для эксперимента {self.experiment_id}.")
                await self.send_json({
                    'type': 'parameters_updated_ack', # Подтверждение для клиента
                    'message': 'Параметры всех этапов успешно сохранены на сервере.'
                })
            else:
                logger.info(f"В update_all_params не было обновлено ни одного этапа.")
                await self.send_json({
                    'type': 'parameters_updated_ack',
                    'message': 'Нет данных для обновления параметров этапов.'
                })

        except Exception as e:
            logger.error(f"Ошибка при обработке update_all_params: {type(e).__name__} - {str(e)}", exc_info=True)
            await self.send_error(f"Ошибка при сохранении всех параметров: {str(e)}")


    async def validate_final_results(self, data):
        """Валидация результатов, введенных пользователем (студентом)."""
        try:
            student_speed_str = data.get('studentSpeed') # Обычно приходит как строка из JS
            student_gamma_str = data.get('studentGamma')
            
            if student_speed_str is None or student_gamma_str is None:
                await self.send_error("Требуются studentSpeed и studentGamma от студента.")
                return

            logger.info(f"Валидация студенческих результатов для эксперимента {self.experiment_id}: скорость={student_speed_str}, γ={student_gamma_str}")

            try:
                student_speed = float(student_speed_str)
                student_gamma = float(student_gamma_str)
            except (TypeError, ValueError) as e:
                await self.send_error(f"Результаты студента должны быть числами. Ошибка: {str(e)}")
                return

            # Получаем сохраненные результаты эксперимента из модели Results
            try:
                lab_results = await database_sync_to_async(Results.objects.get)(experiment=self.experiment)
            except Results.DoesNotExist:
                await self.send_error("Результаты лабораторной работы еще не рассчитаны или не сохранены сервером.")
                return
            
            system_calculated_gamma = lab_results.gamma_calculated # Это среднее γ, рассчитанное системой

            if system_calculated_gamma is None or np.isnan(system_calculated_gamma):
                await self.send_error("Системное значение γ не рассчитано. Невозможно провести валидацию.")
                return

            # Расчет погрешности относительно эталонного γ (1.4 для воздуха)
            # и относительно системного γ
            reference_gamma = 1.4 
            
            error_vs_reference = 0
            if reference_gamma != 0: # Избегаем деления на ноль
                error_vs_reference = abs((student_gamma - reference_gamma) / reference_gamma * 100)
            
            error_vs_system = 0
            if system_calculated_gamma != 0: # Избегаем деления на ноль
                error_vs_system = abs((student_gamma - system_calculated_gamma) / system_calculated_gamma * 100)

            # Предположим, что для скорости звука нет прямого системного аналога для сравнения на этом этапе,
            # так как student_speed может быть теоретическим значением или из другого источника.
            # Основная валидация по γ.

            # Определяем, пройдена ли валидация (например, погрешность < 5-10%)
            # Это пороговое значение должно быть настраиваемым или определено в требованиях.
            VALIDATION_THRESHOLD_PERCENT = 10.0 
            is_valid = error_vs_reference <= VALIDATION_THRESHOLD_PERCENT and \
                       error_vs_system <= VALIDATION_THRESHOLD_PERCENT
            
            # Обновляем запись Results данными студента и результатом валидации
            lab_results.student_gamma = student_gamma
            lab_results.student_speed = student_speed # Сохраняем введенную студентом скорость
            lab_results.error_percent = round(error_vs_reference, 2) # Сохраняем погрешность относительно эталона
            lab_results.status = 'validated_student_pass' if is_valid else 'validated_student_fail'
            
            await database_sync_to_async(lab_results.save)()
            logger.info(f"Результаты студента сохранены, валидация: {'пройдена' if is_valid else 'не пройдена'}. "
                        f"Погрешность (эталон): {error_vs_reference:.2f}%, (система): {error_vs_system:.2f}%")

            response = {
                'type': 'verification_result',
                'is_valid': is_valid,
                'student_gamma': student_gamma,
                'system_calculated_gamma': round(system_calculated_gamma, 4),
                'error_vs_reference_percent': round(error_vs_reference, 2),
                'error_vs_system_percent': round(error_vs_system, 2),
                'message': 'Результаты студента проверены.'
            }
            
            await self.send_json(response)

        except Exception as e:
            logger.error(f"Ошибка валидации результатов студента: {type(e).__name__} - {str(e)}", exc_info=True)
            await self.send_error("Ошибка при валидации результатов студента.")


    def calculate_speed(self, minima_list, frequency):
        """Расчет скорости звука по временам минимумов.
        Minima_list - список словарей, каждый из которых должен иметь ключ 'time_sec'.
        """
        if not minima_list or len(minima_list) < 2:
            logger.warning("Недостаточно минимумов для расчета скорости (нужно >= 2).")
            return float('nan') # Возвращаем NaN если не можем посчитать
            
        times_sec = sorted([m['time_sec'] for m in minima_list if 'time_sec' in m and m['time_sec'] is not None])
        
        if len(times_sec) < 2:
            logger.warning("Недостаточно валидных временных меток минимумов для расчета скорости.")
            return float('nan')

        avg_delta_t = np.mean(np.diff(times_sec))
        
        if avg_delta_t == 0: # Избегаем деления на ноль
            logger.warning("Среднее время между минимумами равно нулю. Невозможно рассчитать скорость.")
            return float('nan')
        
        # Формула скорости звука в трубе Кундта: v = 2 * L * f, где L - расстояние между минимумами.
        # Здесь L эквивалентно lambda/2. Время между минимумами t_delta = (lambda/2) / v = 1 / (2 * f_mod)
        # где f_mod - частота модуляции огибающей.
        # Если мы принимаем, что минимумы соответствуют полуволнам стоячей волны,
        # то расстояние между ними L = lambda / 2. Время прохождения этого расстояния звуком
        # (если мы не говорим о стоячей волне, а о бегущей, формирующей минимумы интерференции)
        # может быть связано с периодом модуляции.
        # Исходная формула была: 343 / (2 * frequency * avg_delta_t) * calibration_factor * 100
        # Эта формула требует пересмотра и калибровки под конкретную установку.
        # Пока что, для примера, если avg_delta_t - это период появления минимумов (1/f_mod),
        # и f_mod = 40 Гц (как в тесте), то v = lambda_mod * f_main.
        # lambda_mod - это "длина волны модуляции".
        # Это сложный вопрос, зависящий от физики установки.
        # Используем более простую интерпретацию: если минимумы - это узлы стоячей волны,
        # то расстояние между ними L = lambda_sound / 2.
        # И время между формированием этих узлов (если они сканируются) t_delta.
        # v_sound = lambda_sound * f_sound.
        # Здесь f_sound - это `frequency` (частота основного сигнала).
        # Если avg_delta_t - это время, за которое "пробегает" расстояние lambda_sound/2,
        # то v_sound = (lambda_sound/2) / avg_delta_t.
        # lambda_sound = v_sound / f_sound.
        # v_sound = (v_sound / (2*f_sound)) / avg_delta_t  => 1 = 1 / (2*f_sound*avg_delta_t) => 2*f_sound*avg_delta_t = 1.
        # Это означает, что avg_delta_t должно быть 1/(2*f_sound).

        # Формула для стоячей волны, где L - расстояние между узлами (минимумами), f - частота:
        # v = 2 * L * f.  Если мы можем измерить L.
        # Если у нас есть времена t1, t2, t3... минимумов, и они соответствуют позициям x1, x2, x3...
        # То v = (x2-x1)/(t2-t1) - это если мы отслеживаем движение одного минимума.
        # Если это разные минимумы стоячей волны, то L = x(n+1) - x(n).
        
        # Вернемся к предположению, что avg_delta_t - это время между последовательными минимумами.
        # В оригинальной задаче, скорость звука v = λf. Расстояние между минимумами L = λ/2.
        # Если мы знаем L (из данных расстояний) и f (частота источника).
        # Если avg_delta_t - это 1 / (2 * f_биения_или_модуляции), то
        # скорость = некоторая_длина_волны * частота_основная.
        # Пока что оставим простую формулу, которую нужно будет калибровать или заменить
        # на основе физики конкретной установки.
        # Пример: если f_mod = 1/avg_delta_t, то v = (lambda_sound_wave / 2) / avg_delta_t (неправильно)
        # v_sound = lambda_main * f_main.
        # Если минимумы возникают с частотой f_min_occurrence = 1/avg_delta_t,
        # и расстояние между ними L_min. То v_sound = 2 * L_min * f_main (если f_main - частота, образующая стоячую волну).
        # Либо, если L_min - это расстояние, которое звук проходит за avg_delta_t, то v = L_min / avg_delta_t.

        # Пока что используем базовую формулу, требующую калибровки:
        # v = C / (frequency * avg_delta_t), где C - калибровочный коэффициент.
        # Если предположить, что avg_delta_t соответствует половине периода основной волны (неверно для огибающей),
        # avg_delta_t = 1 / (2*frequency) => v = C * 2.
        # Если avg_delta_t - период модуляции, f_mod = 1/avg_delta_t.
        # Пусть скорость = 2 * "эффективное расстояние между минимумами" * "частота модуляции"
        # Это требует четкого определения "эффективного расстояния".

        # Формула из старого кода: 343 / (2 * frequency * avg_delta_t) * calibration_factor * 100
        # Упростим, убрав calibration_factor и *100, предполагая, что все в СИ.
        # И 343 - это ожидаемая скорость.
        # Если v = K / (frequency * avg_delta_t).
        # Пусть K - это константа, которую нужно определить.
        # Если avg_delta_t - это время, за которое проходится половина длины волны основного сигнала.
        # lambda_main / 2 = v * avg_delta_t.  lambda_main = v / frequency.
        # (v / (2*frequency)) = v * avg_delta_t  => 1 / (2*frequency) = avg_delta_t.
        # Это условие, когда формула имеет смысл.

        # В контексте трубы Кундта, если минимумы - это узлы стоячей волны, расстояние между ними L = v / (2*f).
        # Если мы определяем времена t_i минимумов, и они соответствуют движению поршня,
        # то скорость поршня dL/dt.
        # Скорость звука = 2 * (dL/dt) * f / (df/dt) - это для сложного случая.

        # Пока оставим как есть, но это место для улучшения/калибровки.
        # Если `minima_list` содержит 'distance_cm', можно попробовать использовать его.
        distances_of_minima_m = [m['distance_cm'] / 100.0 for m in minima_list if 'distance_cm' in m and m['distance_cm'] is not None]
        times_of_minima_s = [m['time_sec'] for m in minima_list if 'time_sec' in m and m['time_sec'] is not None]

        if len(distances_of_minima_m) >=2 and len(times_of_minima_s) == len(distances_of_minima_m):
            # Попробуем рассчитать скорость как d(расстояние_минимума)/d(время_минимума)
            # Это будет скорость движения структуры, на которой образуются минимумы.
            # Не скорость звука напрямую, а скорость, с которой сканируются минимумы.
            # Но если минимумы фиксированы, а трубка движется, то это скорость трубки.
            
            # Более подходящий подход: если минимумы - это узлы стоячей волны,
            # то расстояние между ними L_min = v_sound / (2 * frequency).
            # v_sound = 2 * L_min * frequency.
            # Мы можем найти L_min как среднее расстояние между последовательными минимумами по 'distance_cm'.
            
            # Сортируем по времени, чтобы найти последовательные минимумы
            sorted_minima_by_time = sorted([m for m in minima_list if m.get('distance_cm') is not None and m.get('time_sec') is not None], key=lambda x: x['time_sec'])
            
            delta_distances_m = []
            if len(sorted_minima_by_time) >= 2:
                # Расстояния между пространственными позициями минимумов
                # Предполагаем, что минимумы отсортированы по 'distance_cm' в find_minima
                # Если find_minima отсортировал их по расстоянию, то distances_of_minima_m уже отсортированы.
                 min_distances_sorted = sorted(list(set(d for d in distances_of_minima_m))) # Уникальные отсортированные расстояния
                 if len(min_distances_sorted) >=2:
                    avg_dist_between_minima_m = np.mean(np.diff(min_distances_sorted))
                    # Это среднее L (расстояние между узлами)
                    # Тогда v_sound = 2 * avg_dist_between_minima_m * frequency
                    calculated_v = 2 * avg_dist_between_minima_m * frequency
                    logger.info(f"Скорость звука рассчитана по среднему расстоянию между минимумами ({avg_dist_between_minima_m:.4f} м) и частоте ({frequency} Гц): {calculated_v:.2f} м/с")
                    return calculated_v

        # Если не удалось по расстояниям, используем старую формулу по времени (требует калибровки)
        # Эта формула предполагает, что avg_delta_t связано с половиной периода.
        # v = 1 / (frequency * avg_delta_t) * C - это более вероятно, если avg_delta_t - это период.
        # Если avg_delta_t - это время прохождения lambda/2, то v = (lambda/2)/avg_delta_t. lambda = v/f.
        # v = (v/(2f))/avg_delta_t  => 1 = 1/(2f*avg_delta_t) => avg_delta_t = 1/(2f).
        # Эта формула была бы: speed = (1.0 / (2 * avg_delta_t)) / frequency * НЕКАЯ_ДЛИНА (если 1/(2*avg_delta_t) это частота f_mod)
        # speed = "длина волны модуляции" * frequency (частота несущей).
        # Это очень зависит от физики.
        # Пока оставим placeholder, который явно неверен без калибровки.
        # Calibration_factor должен быть порядка (ожидаемая скорость * ожидаемая частота * ожидаемое время)
        calibration_placeholder = 343.0 # Заглушка, заменяющая сложную калибровку
        calculated_v_time_based = calibration_placeholder / (2 * frequency * avg_delta_t if frequency * avg_delta_t != 0 else float('inf'))
        logger.warning(f"Скорость звука рассчитана по временным интервалам минимумов (требует калибровки): {calculated_v_time_based:.2f} м/с. avg_delta_t={avg_delta_t}, freq={frequency}")
        return calculated_v_time_based # Вернем что-то, но это нужно будет править


    def calculate_gamma(self, v, temperature_celsius):
        """Расчет коэффициента γ (отношения теплоемкостей)."""
        if v is None or np.isnan(v) or v <= 0:
            logger.warning(f"Некорректная скорость ({v}) для расчета γ.")
            return float('nan')
            
        R = 8.314  # Универсальная газовая постоянная Дж/(моль·К)
        mu = 0.029  # Молярная масса воздуха (кг/моль)
        T_kelvin = temperature_celsius + 273.15  # Температура в Кельвинах
        
        if T_kelvin <=0:
            logger.warning(f"Некорректная температура ({T_kelvin} K) для расчета γ.")
            return float('nan')

        gamma = (v ** 2 * mu) / (R * T_kelvin)
        
        # Ограничиваем разумные значения для воздуха (обычно 1.0 до 1.67)
        # return max(1.0, min(1.7, gamma)) # Простое ограничение
        if 1.0 <= gamma <= 2.0: # Более широкий диапазон для фиксации аномалий
            return gamma
        else:
            logger.warning(f"Рассчитанное значение γ ({gamma:.4f}) выходит за пределы ожидаемого диапазона (1.0-2.0). Скорость: {v:.2f} м/с, Температура: {temperature_celsius}°C.")
            return float('nan') # Возвращаем NaN, если значение неправдоподобно


    async def decode_audio(self, audio_bytes, audio_format):
        """Декодирование аудиоданных из различных форматов."""
        try:
            logger.debug(f"Декодирование аудио: формат={audio_format}, размер={len(audio_bytes)} байт")
            
            if audio_format.lower() in ['webm', 'opus']:
                sound = AudioSegment.from_file(io.BytesIO(audio_bytes), format=audio_format.lower())
                # Экспортируем в WAV для дальнейшей обработки с scipy
                wav_io = io.BytesIO()
                sound.export(wav_io, format="wav")
                wav_io.seek(0) # Перематываем в начало для чтения
                sample_rate, data = wavfile.read(wav_io)
            elif audio_format.lower() == 'wav':
                sample_rate, data = wavfile.read(io.BytesIO(audio_bytes))
            else:
                raise ValueError(f"Неподдерживаемый формат аудио: {audio_format}")

            if data.ndim > 1: # Если стерео, берем один канал (например, левый или среднее)
                data = data[:, 0] 
            
            # Нормализация данных в диапазон [-1, 1]
            if np.issubdtype(data.dtype, np.integer):
                samples = data.astype(np.float32) / np.iinfo(data.dtype).max
            elif np.issubdtype(data.dtype, np.floating):
                samples = data.astype(np.float32) # Уже float, но убедимся что float32
                # Если данные уже float, они могут быть не в диапазоне iinfo.max.
                # Нормализуем по фактическому максимуму, если он есть.
                max_val = np.max(np.abs(samples))
                if max_val > 0:
                    samples = samples / max_val
            else:
                raise ValueError(f"Неподдерживаемый dtype аудиоданных: {data.dtype}")

            logger.debug(f"Декодировано: частота={sample_rate} Гц, сэмплов={len(samples)}")
            return samples, sample_rate

        except Exception as e:
            logger.error(f"Ошибка декодирования аудио: {type(e).__name__} - {str(e)}", exc_info=True)
            # Вместо выброса ValueError, который может остановить всю обработку,
            # вернем None, чтобы вызывающий код мог это обработать.
            return None, None


    def apply_butterworth_filter(self, data, sample_rate, cutoff=10000, order=4):
        """Применение фильтра Баттерворта нижних частот."""
        try:
            if data is None or len(data) == 0:
                logger.warning("Пустые данные для фильтрации.")
                return None

            if data.ndim > 1: # Обработка многоканального аудио
                logger.debug(f"Многоканальное аудио ({data.shape}), берем первый канал для фильтрации.")
                data = data[:, 0]
            
            # Минимальная длина сигнала для filtfilt: 3 * (max(len(b), len(a)) - 1), где len(a/b) = order+1
            min_len_filtfilt = 3 * order 
            if len(data) < min_len_filtfilt:
                logger.warning(f"Слишком короткий сигнал ({len(data)}) для фильтрации Баттерворта порядка {order}. Требуется минимум {min_len_filtfilt} сэмплов. Фильтрация пропущена.")
                return data # Возвращаем исходные данные, если они слишком коротки

            nyq = 0.5 * sample_rate
            if cutoff >= nyq:
                logger.warning(f"Частота среза ({cutoff} Гц) больше или равна частоте Найквиста ({nyq} Гц). Фильтрация не будет эффективной или вызовет ошибку. Пропускаем фильтрацию.")
                return data
            
            normal_cutoff = cutoff / nyq
            b, a = butter(order, normal_cutoff, btype='low', analog=False)
            filtered = filtfilt(b, a, data)
            
            logger.debug(f"Фильтрация Баттерворта успешна. Диапазон отфильтрованного сигнала: [{np.min(filtered):.3f}, {np.max(filtered):.3f}]")
            return filtered
        except Exception as e:
            logger.error(f"Ошибка применения фильтра Баттерворта: {type(e).__name__} - {str(e)}", exc_info=True)
            return data # В случае ошибки возвращаем исходные данные


    def find_minima(self, audio_samples, sample_rate, distances_cm, distance_timestamps, current_step_num):
        """
        Основной метод поиска минимумов амплитуды звука в зависимости от расстояния.
        Аудиоданные и данные о расстоянии должны быть синхронизированы по времени.
        Расстояния передаются в САНТИМЕТРАХ.
        """
        try:
            logger.info(f"[Step {current_step_num}] Начало поиска минимумов по амплитуде и расстоянию.")
            # Логирование входных данных
            audio_len = len(audio_samples) if audio_samples is not None else 0
            dist_len = len(distances_cm) if distances_cm is not None else 0
            ts_len = len(distance_timestamps) if distance_timestamps is not None else 0
            logger.debug(f"[Step {current_step_num}] Аудио: {audio_len} сэмплов @ {sample_rate} Гц. Расстояния: {dist_len} точек. Врем. метки: {ts_len} точек.")

            if distances_cm and ts_len == dist_len and dist_len > 0:
                 logger.debug(f"[Step {current_step_num}] Диапазон расстояний (см): [{min(distances_cm):.1f} - {max(distances_cm):.1f}]")
                 logger.debug(f"[Step {current_step_num}] Диапазон временных меток расстояний (с): [{min(distance_timestamps):.3f} - {max(distance_timestamps):.3f}]")
            
            if audio_samples is None or audio_len < 100:
                logger.warning(f"[Step {current_step_num}] Слишком короткий или отсутствующий аудиосигнал ({audio_len}) для анализа минимумов.")
                return []
            
            if distances_cm is None or not distances_cm or distance_timestamps is None or not distance_timestamps or dist_len != ts_len:
                logger.warning(f"[Step {current_step_num}] Отсутствуют, неполные или несогласованные данные о расстоянии. dist_len={dist_len}, ts_len={ts_len}. Вызов резервного метода.")
                return self._find_minima_by_signal(audio_samples, sample_rate, distances_cm, distance_timestamps, current_step_num)

            # 1. Предобработка аудио
            # Канал должен быть один (моно). Если стерео, усредняем или берем один канал.
            audio_mono = audio_samples
            if audio_samples.ndim > 1:
                audio_mono = np.mean(audio_samples, axis=1) if audio_samples.shape[1] > 0 else audio_samples[:,0]
            
            logger.debug(f"[Step {current_step_num}] audio_mono stats: Min={np.min(audio_mono):.4f}, Max={np.max(audio_mono):.4f}, Mean={np.mean(audio_mono):.4f}")

            analytic_signal = hilbert(audio_mono)
            amplitude_envelope = np.abs(analytic_signal)
            
            logger.debug(f"[Step {current_step_num}] amplitude_envelope stats before norm: Min={np.min(amplitude_envelope):.4f}, Max={np.max(amplitude_envelope):.4f}, Mean={np.mean(amplitude_envelope):.4f}, Median={np.median(amplitude_envelope):.4f}, 95th Pctl={np.percentile(amplitude_envelope, 95):.4f}, 99th Pctl={np.percentile(amplitude_envelope, 99):.4f}")
            
            # Используем 99-й процентиль для устойчивости к выбросам
            max_amp_robust = np.percentile(amplitude_envelope, 99)
            if max_amp_robust == 0: # Если и 99-й процентиль 0, возможно, весь сигнал нулевой
                max_amp_robust = np.max(amplitude_envelope) # Попробуем абсолютный максимум в этом случае
                if max_amp_robust == 0:
                    logger.warning(f"[Step {current_step_num}] Максимальная амплитуда огибающей (и 99-й процентиль) равна нулю. Невозможно нормализовать.")
                    return []
                else:
                    logger.warning(f"[Step {current_step_num}] 99-й процентиль амплитуды огибающей равен 0, используется абсолютный максимум: {max_amp_robust:.4f}")
            else:
                logger.debug(f"[Step {current_step_num}] Для нормализации используется 99-й процентиль амплитуды огибающей: {max_amp_robust:.4f} (Абс. макс: {np.max(amplitude_envelope):.4f})")

            normalized_envelope = amplitude_envelope / max_amp_robust
            # Опционально: ограничить сверху, чтобы избежать значений > 1 из-за процентиля
            normalized_envelope = np.clip(normalized_envelope, 0, 1.0) # Клиппинг от 0 до 1

            # 2. Временные шкалы
            audio_duration_sec = audio_len / sample_rate
            audio_time_axis_sec = np.linspace(0, audio_duration_sec, audio_len, endpoint=False)

            # Логирование для проверки normalized_envelope в районе distance_timestamps
            if len(distance_timestamps) > 0:
                min_dist_time = min(distance_timestamps)
                max_dist_time = max(distance_timestamps)
                logger.debug(f"[Step {current_step_num}] Диапазон distance_timestamps: [{min_dist_time:.3f}с - {max_dist_time:.3f}с]")
                
                # Найдем индексы в audio_time_axis_sec, близкие к диапазону distance_timestamps
                start_audio_idx = np.searchsorted(audio_time_axis_sec, min_dist_time, side='left')
                end_audio_idx = np.searchsorted(audio_time_axis_sec, max_dist_time, side='right')
                
                # Ограничим количество выводимых точек для лога
                num_log_points = 10
                step_log = max(1, (end_audio_idx - start_audio_idx) // num_log_points)
                
                logger.debug(f"[Step {current_step_num}] Проверка normalized_envelope и audio_time_axis_sec в диапазоне [{min_dist_time:.3f}с - {max_dist_time:.3f}с]. Индексы аудио: [{start_audio_idx} - {end_audio_idx-1}], шаг лога: {step_log}")
                if start_audio_idx < end_audio_idx:
                    for i in range(start_audio_idx, end_audio_idx, step_log):
                        if i < len(normalized_envelope):
                            logger.debug(f"  AudioTime: {audio_time_axis_sec[i]:.3f}с, NormalizedEnvelope: {normalized_envelope[i]:.4f}")
                else:
                    logger.warning(f"[Step {current_step_num}] Диапазон distance_timestamps не пересекается с audio_time_axis_sec или слишком мал.")
            
            # 3. Интерполяция
            # Убедимся, что target_interpolation_times_sec (т.е. distance_timestamps) отсортированы для interp1d
            # и что они находятся в пределах audio_time_axis_sec.
            
            # Создаем копии и проверяем сортировку distance_timestamps
            dist_ts_np = np.array(distance_timestamps)
            dist_cm_np = np.array(distances_cm)

            sort_indices = np.argsort(dist_ts_np)
            sorted_dist_ts = dist_ts_np[sort_indices]
            sorted_dist_cm = dist_cm_np[sort_indices]

            # Обрезаем временные метки расстояний, чтобы они строго попадали в диапазон аудио
            # (interp1d не любит, когда точки выходят за пределы, даже с fill_value)
            valid_interp_indices = (sorted_dist_ts >= audio_time_axis_sec[0]) & \
                                   (sorted_dist_ts <= audio_time_axis_sec[-1])
            
            target_interp_times = sorted_dist_ts[valid_interp_indices]
            target_interp_distances = sorted_dist_cm[valid_interp_indices]

            if len(target_interp_times) < 2: # Нужно хотя бы 2 точки для интерполяции и find_peaks
                logger.warning(f"[Step {current_step_num}] Недостаточно валидных точек ({len(target_interp_times)}) для интерполяции после обрезки по времени аудио. Вызов резервного метода.")
                return self._find_minima_by_signal(audio_samples, sample_rate, distances_cm, distance_timestamps, current_step_num)

            from scipy.interpolate import interp1d
            try:
                amplitude_interpolator = interp1d(audio_time_axis_sec, normalized_envelope,
                                                  kind='linear', bounds_error=False, 
                                                  fill_value=(normalized_envelope[0], normalized_envelope[-1]))
                amplitude_at_distance_times = amplitude_interpolator(target_interp_times)
            except ValueError as ve:
                logger.error(f"[Step {current_step_num}] Ошибка интерполяции: {ve}", exc_info=True)
                return self._find_minima_by_signal(audio_samples, sample_rate, distances_cm, distance_timestamps, current_step_num)

            # 4. Поиск пиков (минимумов в исходной амплитуде)
            inverted_amplitude = 1.0 - amplitude_at_distance_times 
            
            # Более подробное логирование данных перед find_peaks
            if len(target_interp_distances) > 0:
                logger.debug(f"[Step {current_step_num}] Пример данных для find_peaks (первые 5 и последние 5 точек из {len(target_interp_distances)} всего):")
                indices_to_log = list(range(min(5, len(target_interp_distances)))) + list(range(max(0, len(target_interp_distances) - 5), len(target_interp_distances)))
                indices_to_log = sorted(list(set(indices_to_log))) # Убираем дубликаты и сортируем, если диапазоны пересеклись
                for i in indices_to_log:
                    logger.debug(f"  Idx: {i}, Dist: {target_interp_distances[i]:.2f} cm, InterpAmp: {amplitude_at_distance_times[i]:.3f}, InvertedAmp: {inverted_amplitude[i]:.3f}")

            num_interp_samples = len(amplitude_at_distance_times)
            
            # Исходные параметры из self.minima_params
            original_peak_min_dist_samples = max(1, int(num_interp_samples * self.minima_params.get('min_distance_ratio', 0.03)))
            original_peak_min_prominence = self.minima_params.get('min_prominence', 0.15) 
            original_peak_min_height = self.minima_params.get('min_amplitude', 0.2) 
            original_peak_min_width_samples = max(1, int(num_interp_samples * self.minima_params.get('min_width_ratio', 0.01)))

            logger.debug(f"[Step {current_step_num}] ОРИГИНАЛЬНЫЕ Параметры find_peaks: num_interp_samples={num_interp_samples}, height={original_peak_min_height}, distance={original_peak_min_dist_samples}, prominence={original_peak_min_prominence}, width={original_peak_min_width_samples}")

            peak_indices, properties = find_peaks(
                inverted_amplitude,
                height=original_peak_min_height, # Используем оригинальные параметры
                distance=original_peak_min_dist_samples, # Используем оригинальные параметры
                prominence=original_peak_min_prominence, # Используем оригинальные параметры
                width=original_peak_min_width_samples # Используем оригинальные параметры
            )
            
            logger.info(f"[Step {current_step_num}] Найдено {len(peak_indices)} потенциальных минимумов после find_peaks (с оригинальными параметрами).")

            # 5. Формирование списка
            minima_list = []
            for peak_idx in peak_indices:
                original_amplitude_val = 1.0 - inverted_amplitude[peak_idx]
                time_sec_val = target_interp_times[peak_idx]
                distance_cm_val = target_interp_distances[peak_idx]
                
                # Примерная позиция в исходном аудиофайле (может быть неточной из-за интерполяции)
                # Важнее 'time_sec', которое точно соответствует моменту измерения расстояния.
                approx_orig_audio_pos = int(time_sec_val * sample_rate)

                # Дополнительная фильтрация по диапазону расстояний, если это имеет смысл для эксперимента
                # if not (1 <= distance_cm_val <= 50): 
                #     logger.debug(f"[Step {current_step_num}] Минимум на расстоянии {distance_cm_val:.1f} см отфильтрован.")
                #     continue

                minima_list.append({
                    'position_orig_audio': approx_orig_audio_pos, 
                    'amplitude': float(original_amplitude_val), 
                    'time_sec': float(time_sec_val),        
                    'distance_cm': float(distance_cm_val)   
                })

            minima_list.sort(key=lambda m: m['distance_cm']) # Сортировка по расстоянию для анализа
            
            logger.info(f"[Step {current_step_num}] Итого найдено и отфильтровано {len(minima_list)} минимумов.")
            if minima_list:
                for m_log in minima_list[:5]: # Логируем первые 5 для краткости
                    logger.debug(f"  - Минимум: время={m_log['time_sec']:.3f}с, расстояние={m_log['distance_cm']:.1f}см, амплитуда={m_log['amplitude']:.3f}")
            
            # 6. График
            self._plot_amplitude_vs_distance(
                amplitude_at_distance_times, 
                target_interp_distances, # Используем расстояния, соответствующие точкам amplitude_at_distance_times
                minima_list,
                current_step_num
            )
            
            return minima_list
        
        except ImportError:
            logger.error("Не удалось импортировать scipy.interpolate.interp1d. Убедитесь, что SciPy установлен.")
            return [] # Возвращаем пустой список в случае ошибки импорта
        except Exception as e:
            logger.error(f"[Step {current_step_num}] Критическая ошибка в find_minima: {type(e).__name__} - {str(e)}", exc_info=True)
            return self._find_minima_by_signal(audio_samples, sample_rate, distances_cm, distance_timestamps, current_step_num)


    def _find_minima_by_signal(self, audio_samples, sample_rate, distances_cm=None, distance_timestamps=None, current_step_num="N/A"):
        """Резервный метод: поиск минимумов только по аудиосигналу."""
        try:
            logger.warning(f"[Step {current_step_num}] Запуск резервного метода _find_minima_by_signal.")
            if audio_samples is None or len(audio_samples) < 100:
                 logger.warning(f"[Step {current_step_num}, Fallback] Слишком короткий аудиосигнал.")
                 return []

            audio_mono = audio_samples
            if audio_samples.ndim > 1:
                 audio_mono = np.mean(audio_samples, axis=1) if audio_samples.shape[1] > 0 else audio_samples[:,0]
            
            analytic_signal = hilbert(audio_mono)
            amplitude_envelope = np.abs(analytic_signal)
            
            max_amp_env = np.max(amplitude_envelope)
            if max_amp_env == 0: 
                logger.warning(f"[Step {current_step_num}, Fallback] Макс. амплитуда огибающей 0.")
                return []
            normalized_envelope = amplitude_envelope / max_amp_env
            
            inverted_envelope = 1.0 - normalized_envelope
            
            min_dist_audio_samples = int(sample_rate * self.minima_params.get('min_time_separation_s', 0.015))

            logger.debug(f"[Step {current_step_num}, Fallback] Params for find_peaks (audio envelope): height={self.minima_params.get('min_amplitude', 0.2)}, distance={min_dist_audio_samples}, prominence={self.minima_params.get('min_prominence', 0.15)}")

            peak_indices, _ = find_peaks(
                inverted_envelope,
                height=self.minima_params.get('min_amplitude', 0.2),
                distance=min_dist_audio_samples, 
                prominence=self.minima_params.get('min_prominence', 0.15)
            )
            
            minima_list = []
            for p_idx in peak_indices:
                time_at_minima_sec = p_idx / sample_rate
                amp_at_minima = normalized_envelope[p_idx]
                
                distance_cm_val = None
                if distances_cm and distance_timestamps and len(distances_cm) == len(distance_timestamps) and len(distances_cm) > 0:
                    try:
                        closest_dist_time_idx = np.argmin(np.abs(np.array(distance_timestamps) - time_at_minima_sec))
                        avg_dist_interval = np.mean(np.diff(np.sort(distance_timestamps))) if len(distance_timestamps) > 1 else float('inf')
                        
                        if abs(distance_timestamps[closest_dist_time_idx] - time_at_minima_sec) < avg_dist_interval : 
                             distance_cm_val = distances_cm[closest_dist_time_idx]
                    except Exception as e_dist_fb:
                        logger.warning(f"[Step {current_step_num}, Fallback] Ошибка при поиске расстояния для минимума: {e_dist_fb}")
                
                minima_list.append({
                    'position_orig_audio': int(p_idx),
                    'amplitude': float(amp_at_minima),
                    'time_sec': float(time_at_minima_sec),
                    'distance_cm': float(distance_cm_val) if distance_cm_val is not None else None
                })

            minima_list.sort(key=lambda x: x['time_sec'])
            logger.info(f"[Step {current_step_num}, Fallback] Найдено {len(minima_list)} минимумов по аудиосигналу.")
            return minima_list
        
        except Exception as e:
            logger.error(f"[Step {current_step_num}, Fallback] Ошибка в _find_minima_by_signal: {type(e).__name__} - {str(e)}", exc_info=True)
            return []


    def _plot_amplitude_vs_distance(self, amplitudes_at_dist_times, distances_cm_for_plot, found_minima_list, current_step_num):
        """Построение графика зависимости амплитуды от расстояния."""
        try:
            if not os.path.exists('plots'):
                os.makedirs('plots')
            
            plt.figure(figsize=(12, 8))
            
            # График 1: Амплитуда звука (интерполированная) vs Расстояние
            plt.subplot(2, 1, 1)
            if distances_cm_for_plot is not None and amplitudes_at_dist_times is not None and \
               len(distances_cm_for_plot) == len(amplitudes_at_dist_times) and len(distances_cm_for_plot) > 0:
                # Сортируем для корректного отображения линии
                sort_plot_indices = np.argsort(distances_cm_for_plot)
                plt.plot(distances_cm_for_plot[sort_plot_indices], amplitudes_at_dist_times[sort_plot_indices], 
                         'b-', label='Амплитуда звука (норм., интерп.)', alpha=0.6)
            else:
                 logger.warning(f"[Plot {current_step_num}] Невозможно построить основной график: нет данных или несоответствие длин.")

            minima_plot_distances = [m['distance_cm'] for m in found_minima_list if m.get('distance_cm') is not None]
            minima_plot_amplitudes = [m['amplitude'] for m in found_minima_list if m.get('distance_cm') is not None]
            
            if minima_plot_distances and minima_plot_amplitudes:
                 plt.plot(minima_plot_distances, minima_plot_amplitudes, 'ro', markersize=7, label='Найденные минимумы')
                 for m_plot in found_minima_list:
                     if m_plot.get('distance_cm') is not None:
                        plt.text(m_plot['distance_cm'], m_plot['amplitude'] + 0.02, 
                                 f"{m_plot['distance_cm']:.1f}см", fontsize=8, ha='center', color='red')

            plt.title(f"Шаг {current_step_num}: Зависимость амплитуды звука от расстояния")
            plt.xlabel('Расстояние (см)')
            plt.ylabel('Нормализованная амплитуда огибающей')
            plt.grid(True, linestyle='--', alpha=0.7)
            plt.legend()
            # Динамическое масштабирование оси Y для графика "Зависимость амплитуды звука от расстояния".
            # Это позволяет лучше рассмотреть сигнал, если его амплитуда мала.
            if amplitudes_at_dist_times is not None and len(amplitudes_at_dist_times) > 0:
                plot_max_amp = np.max(amplitudes_at_dist_times)
                plot_min_amp = np.min(amplitudes_at_dist_times)
                # Рассчитываем верхний и нижний пределы для оси Y с небольшим запасом.
                upper_ylim = max(plot_max_amp * 1.1 if plot_max_amp > 0 else 0.05, 0.05) 
                lower_ylim = min(plot_min_amp * 1.1 if plot_min_amp < 0 else -0.05, -0.05) 
                if plot_min_amp >= 0: lower_ylim = -0.05 
                
                # Гарантируем минимальный видимый диапазон, если сигнал очень слабый или плоский.
                if upper_ylim <= lower_ylim + 0.01 : upper_ylim = lower_ylim + 0.1 
                if upper_ylim < 0.1: upper_ylim = 0.1 

                plt.ylim(lower_ylim, upper_ylim)
                logger.debug(f"[Plot {current_step_num}] Динамический Y-лим для графика амплитуды: [{lower_ylim:.2f}, {upper_ylim:.2f}] (на основе данных min={plot_min_amp:.3f}, max={plot_max_amp:.3f})")
            else:
                plt.ylim(-0.05, 1.05) # Fallback, если нет данных для построения

            # График 2: Исходные данные о расстоянии (если доступны)
            plt.subplot(2, 1, 2)
            step_idx_plot = -1
            if isinstance(current_step_num, str) and current_step_num.isdigit(): step_idx_plot = int(current_step_num) - 1
            elif isinstance(current_step_num, int): step_idx_plot = current_step_num - 1
            
            step_data_plot = None
            if 0 <= step_idx_plot < len(self.experiment_steps) and isinstance(self.experiment_steps[step_idx_plot], dict):
                 step_data_plot = self.experiment_steps[step_idx_plot]
            
            if step_data_plot:
                original_dist_ts_plot = step_data_plot.get('distance_timestamps')
                original_dist_cm_plot = step_data_plot.get('distance_samples_cm')
                if original_dist_ts_plot and original_dist_cm_plot and \
                   len(original_dist_ts_plot) == len(original_dist_cm_plot) and len(original_dist_ts_plot) > 0:
                    plt.plot(original_dist_ts_plot, original_dist_cm_plot, 'g.-', label='Исходные данные расстояния (из experiment_steps)', alpha=0.7)
                    plt.xlabel('Время записи шага (с)')
                    plt.ylabel('Расстояние (см)')
                    plt.title('Динамика изменения расстояния во времени (исходные данные)')
                    plt.grid(True, linestyle='--', alpha=0.5)
                    plt.legend()
                else:
                    logger.warning(f"[Plot {current_step_num}] Не удалось построить график динамики расстояния: данные в experiment_steps отсутствуют/неполны.")
            else:
                logger.warning(f"[Plot {current_step_num}] Данные шага ({current_step_num}) не найдены в experiment_steps для графика динамики.")

            plt.tight_layout()
            plot_filename = f'plots/step_{current_step_num}_amplitude_vs_distance.png'
            plt.savefig(plot_filename, dpi=150)
            plt.close()
            logger.info(f"График амплитуда-расстояние сохранен: {plot_filename}")
        except Exception as e:
            logger.error(f"Ошибка при построении графика амплитуда-расстояние для шага {current_step_num}: {type(e).__name__} - {str(e)}", exc_info=True)

    async def send_json(self, data):
        """Отправка данных в формате JSON через WebSocket."""
        try:
            if not self.connected:
                logger.warning(
                    "Попытка отправки при разорванном соединении\\n"
                    f"  Текущее состояние: connected={self.connected}"
                )
                return False
                
            def convert_numpy_types(obj):
                """Рекурсивная конвертация numpy типов в Python типы для JSON."""
                if isinstance(obj, (np.integer, np.int64)):
                    return int(obj)
                elif isinstance(obj, np.floating): 
                    if np.isnan(obj): return None 
                    elif np.isinf(obj): return None 
                    return float(obj)
                elif isinstance(obj, np.ndarray):
                    return [convert_numpy_types(x) for x in obj] 
                elif isinstance(obj, dict):
                    return {k: convert_numpy_types(v) for k, v in obj.items()}
                elif isinstance(obj, list):
                    return [convert_numpy_types(i) for i in obj]
                return obj
                
            converted_data = convert_numpy_types(data)
            message = json.dumps(converted_data)
            await self.send(text_data=message)
            
            logger.debug(
                "Данные успешно отправлены\\n"
                f"  Тип сообщения: {data.get('type')}\\n"
                f"  Размер сообщения: {len(message)} байт"
            )
            return True
        except Exception as e:
            logger.error(
                "Ошибка при отправке JSON\\n"
                f"  Тип ошибки: {type(e).__name__}\\n"
                f"  Сообщение: {str(e)}\\n"
                "  Трассировка:", exc_info=True
            )
            self.connected = False 
            return False

    async def handle_start_recording(self, data):
        """Обработчик начала записи."""
        try:
            step = data.get('step')
            if not step or not isinstance(step, int):
                await self.send_error("Не указан или некорректный номер шага")
                return
                
            logger.info(
                "Начало записи\\n"
                f"  Шаг: {step}\\n"
                f"  Текущий шаг: {self.current_step}"
            )
            
            await self.send_json({
                'type': 'recording_started',
                'step': step,
                'status': 'recording'
            })
            
        except Exception as e:
            logger.error(
                "Ошибка при начале записи\\n"
                f"  Тип ошибки: {type(e).__name__}\\n"
                f"  Сообщение: {str(e)}\\n"
                "  Трассировка:", exc_info=True
            )
            await self.send_error(f"Ошибка начала записи: {str(e)}")

    async def handle_stop_recording(self, data):
        """Обработчик остановки записи."""
        try:
            step = data.get('step')
            if not step or not isinstance(step, int):
                await self.send_error("Не указан или некорректный номер шага")
                return
                
            logger.info(
                "Остановка записи\\n"
                f"  Шаг: {step}\\n"
                f"  Текущий шаг: {self.current_step}"
            )
            
            await self.send_json({
                'type': 'recording_stopped',
                'step': step,
                'status': 'stopped'
            })
            
        except Exception as e:
            logger.error(
                "Ошибка при остановке записи\\n"
                f"  Тип ошибки: {type(e).__name__}\\n"
                f"  Сообщение: {str(e)}\\n"
                "  Трассировка:", exc_info=True
            )
            await self.send_error(f"Ошибка остановки записи: {str(e)}")

    async def test_audio_processing(self):
        """Тестовая обработка сгенерированного аудиосигнала."""
        try:
            logger.info("Запуск тестовой обработки аудио...")
            
            sample_rate = 48000
            duration = 0.5 
            t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
            
            main_freq = 2000 
            mod_freq = 40  
            mod_depth = 0.7
            
            carrier = np.sin(2 * np.pi * main_freq * t)
            modulator = 1 + mod_depth * np.sin(2 * np.pi * mod_freq * t)
            signal = carrier * modulator
            
            noise = np.random.normal(0, 0.05 * mod_depth, len(t))
            samples = signal + noise
            
            logger.debug(
                f"Тестовый сигнал: частота={main_freq}Гц, мод.частота={mod_freq}Гц, глубина={mod_depth}, длительность={duration}с, сэмплов={len(samples)}"
            )

            filtered = self.apply_butterworth_filter(samples, sample_rate)
            if filtered is None or len(filtered) == 0:
                logger.error("Тестовая обработка: фильтрация вернула пустой или None результат.")
                return

            # Мок-данные для find_minima
            # Для этого теста find_minima должен вызвать _find_minima_by_signal, так как distances/timestamps пустые
            mock_distances_cm = [] 
            mock_distance_timestamps = []
            mock_current_step_num = "test_step" # Используем строку, чтобы избежать конфликта с индексами experiment_steps
            
            original_experiment_steps = [dict(s) if isinstance(s, dict) else s for s in self.experiment_steps] # Глубокое копирование, если нужно
            original_current_step = self.current_step
            
            # Для _plot_amplitude_vs_distance, который МОЖЕТ вызываться из find_minima,
            # нужно, чтобы self.experiment_steps[step_idx_for_lookup] существовал, ЕСЛИ current_step_num числовой.
            # Если current_step_num - строка (как "test_step"), то график динамики расстояний не будет строиться по данным из experiment_steps.
            # В данном случае, поскольку mock_distances_cm пуст, основной find_minima вызовет _find_minima_by_signal,
            # а _plot_amplitude_vs_distance не будет вызван с этими мок-данными из основного find_minima,
            # т.к. amplitude_at_distance_times будет пуст.
            
            self.current_step = mock_current_step_num # Устанавливаем current_step для контекста find_minima

            minima = self.find_minima(filtered, sample_rate, 
                                      distances_cm=mock_distances_cm, 
                                      distance_timestamps=mock_distance_timestamps, 
                                      current_step_num=mock_current_step_num)
            
            self.experiment_steps = original_experiment_steps
            self.current_step = original_current_step

            if minima is not None and len(minima) >= 2:
                speed = self.calculate_speed(minima, main_freq) # Передаем список минимумов и частоту
                gamma = self.calculate_gamma(speed, 20.0) # Передаем скорость и температуру
                
                minima_times_sec = sorted([m['time_sec'] for m in minima if 'time_sec' in m and m['time_sec'] is not None])
                avg_delta_t = 0.0
                calculated_mod_freq = float('inf')

                if len(minima_times_sec) >= 2:
                    delta_times = np.diff(minima_times_sec)
                    if len(delta_times) > 0:
                         avg_delta_t = np.mean(delta_times)
                         if avg_delta_t > 1e-9: # Избегаем деления на ноль или очень малое число
                            calculated_mod_freq = 1.0 / avg_delta_t
                
                logger.info(f"""
                ТЕСТОВЫЕ РЕЗУЛЬТАТЫ (после вызова find_minima):
                Найдено минимумов: {len(minima)}
                Средний интервал по времени между минимумами: {avg_delta_t:.6f} сек
                Расчетная частота модуляции по минимумам: {calculated_mod_freq:.2f} Гц (Ожидаемая: {mod_freq} Гц)
                Рассчитанная скорость звука (по временам минимумов): {speed if speed is not None else 'N/A'} м/с (Ожидаемая: ~343 м/с)
                Рассчитанный γ: {gamma if gamma is not None else 'N/A'} (Ожидаемый: ~1.4)
                """)
            elif minima is not None:
                logger.warning(f"Тестовая обработка: Найдено {len(minima)} минимумов, но нужно хотя бы 2 для анализа скорости.")
            else:
                logger.warning("Тестовая обработка: find_minima вернул None или пустой список.")

        except Exception as e:
            logger.error(f"Ошибка тестовой обработки: {type(e).__name__} - {str(e)}", exc_info=True)

# Конец класса AudioConsumer