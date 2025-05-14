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
            'min_amplitude': 0.3,
            'min_distance': 0.01,
            'min_prominence': 0.2,
            'min_width': 0.005
        }
        
        logger.debug(
            "Параметры инициализации:\n"
            f"  Частота дискретизации: {self.sample_rate} Гц\n"
            f"  Макс. шагов эксперимента: {self.max_steps}\n"
            f"  Параметры поиска минимумов: {self.minima_params}"
        )
        
        self.connected = False
        self.lock = asyncio.Lock()
        
        # Данные о расстояниях
        self.distance_samples = []
        self.distance_timestamps = []
        
        logger.info("Запуск тестовой обработки аудио")
        asyncio.create_task(self.test_audio_processing())

    async def connect(self):
        """Обработчик установки WebSocket соединения."""
        self.experiment_id = self.scope['url_route']['kwargs']['experiment_id']
        try:
            self.experiment = await database_sync_to_async(Experiments.objects.select_related('user').get)(id=self.experiment_id)
            logger.info(f"Эксперимент {self.experiment_id} загружен для пользователя {self.experiment.user.full_name}")

            # Инициализация experiment_steps и current_step из БД
            self.experiment_steps = self.experiment.stages if isinstance(self.experiment.stages, list) else []
            # Убедимся, что experiment_steps - это список словарей нужной длины
            if not self.experiment_steps or len(self.experiment_steps) != self.max_steps:
                logger.warning(f"Данные этапов в БД для эксперимента {self.experiment_id} некорректны или отсутствуют. Инициализация {self.max_steps} пустыми этапами.")
                self.experiment_steps = [{"frequency": None, "temperature": self.experiment.temperature, "status": "pending", "minima": None, "audio_samples": None} for _ in range(self.max_steps)]
                # Если этапы были пустыми, сразу сохраняем инициализированную структуру
                if not self.experiment.stages:
                    self.experiment.stages = self.experiment_steps
                    await database_sync_to_async(self.experiment.save)()
            else:
                # Проверим, что у каждого этапа есть необходимые ключи
                for i in range(len(self.experiment_steps)):
                    if not isinstance(self.experiment_steps[i], dict):
                        self.experiment_steps[i] = {} # Замена на пустой словарь если не словарь
                    self.experiment_steps[i].setdefault('frequency', None)
                    self.experiment_steps[i].setdefault('temperature', self.experiment.temperature)
                    self.experiment_steps[i].setdefault('status', 'pending')
                    self.experiment_steps[i].setdefault('minima', None)
                    self.experiment_steps[i].setdefault('audio_samples', None)


            self.current_step = self.experiment.step if self.experiment.step and self.experiment.step <= self.max_steps else 1
            
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
            f"Установлено новое WebSocket соединение для эксперимента {self.experiment_id}"
            f"  Текущее состояние: connected={self.connected}"
            f"  Текущий шаг из БД: {self.current_step}")

    async def disconnect(self, close_code):
        """Обработчик закрытия соединения.
        
        Args:
            close_code (int): Код закрытия соединения
        """
        self.connected = False
        logger.info(
            "Соединение закрыто\n"
            f"  Код закрытия: {close_code}\n"
            f"  Текущее состояние: connected={self.connected}"
        )

    async def receive(self, text_data):
        """Основной обработчик входящих сообщений.
        
        Args:
            text_data (str): Текст сообщения в формате JSON
        """
        try:
            logger.info(
                "Получено новое сообщение\n"
                f"  Длина сообщения: {len(text_data)} байт\n"
                f"  Текущий шаг: {self.current_step}"
            )
            
            try:
                data = json.loads(text_data)
                logger.debug("Сообщение успешно декодировано из JSON")
            except json.JSONDecodeError as e:
                logger.error(
                    "Ошибка декодирования JSON\n"
                    f"  Ошибка: {str(e)}\n"
                    f"  Содержимое: {text_data[:100]}..."
                )
                await self.send_error("Неверный формат JSON")
                return

            if not isinstance(data, dict):
                logger.error(
                    "Некорректный формат данных\n"
                    f"  Тип данных: {type(data)}\n"
                    f"  Содержимое: {data}"
                )
                await self.send_error("Ожидается JSON объект")
                return

            message_type = data.get('type')
            if not message_type:
                logger.error(
                    "Отсутствует тип сообщения\n"
                    f"  Доступные ключи: {list(data.keys())}"
                )
                await self.send_error("Требуется поле 'type'")
                return

            logger.info(
                f"Обработка сообщения типа '{message_type}'\n"
                f"  Шаг эксперимента: {data.get('step', 'не указан')}"
            )

            # Выбор обработчика сообщения
            handlers = {
                'complete_audio': self.process_complete_audio,
                'experiment_params': self.handle_experiment_params,
                'final_results': self.validate_final_results,
                'distance_data': self.handle_distance_data,
                'start_recording': self.handle_start_recording,
                'stop_recording': self.handle_stop_recording
            }

            handler = handlers.get(message_type, self.handle_unknown_type)
            
            async with self.lock:
                logger.debug(f"Выполнение обработчика для типа '{message_type}'")
                await handler(data)

        except Exception as e:
            logger.error(
                "Критическая ошибка обработки сообщения\n"
                f"  Тип ошибки: {type(e).__name__}\n"
                f"  Сообщение: {str(e)}\n"
                "  Трассировка:", exc_info=True
            )
            await self.send_error(f"Ошибка обработки: {str(e)}")

    async def handle_unknown_type(self, data):
        """Обработчик для неизвестных типов сообщений.
        
        Args:
            data (dict): Входящее сообщение с неизвестным типом
            
        Логирует предупреждение и отправляет клиенту сообщение об ошибке
        с информацией о полученном типе сообщения.
        """
        try:
            message_type = data.get('type', 'не указан')
            
            logger.warning(
                "Получено сообщение неизвестного типа\n"
                f"  Полученный тип: '{message_type}'\n"
                f"  Доступные ключи в сообщении: {list(data.keys())}\n"
                f"  Текущий шаг эксперимента: {self.current_step}"
            )
            
            error_message = (
                f"Неизвестный тип сообщения: '{message_type}'. "
                f"Ожидается один из: 'experiment_params', 'complete_audio', "
                "'final_results', 'distance_data', 'start_recording', 'stop_recording'"
            )
            
            await self.send_error(error_message)
            
            logger.debug(
                "Сообщение об ошибке отправлено клиенту\n"
                f"  Содержание ошибки: '{error_message}'\n"
                f"  Полное сообщение: {data}"
            )
            
        except Exception as e:
            logger.error(
                "Ошибка при обработке неизвестного типа сообщения\n"
                f"  Тип ошибки: {type(e).__name__}\n"
                f"  Сообщение: {str(e)}\n"
                f"  Данные сообщения: {data}\n"
                "  Трассировка:", exc_info=True
            )
            await self.send_error("Внутренняя ошибка при обработке сообщения")

    async def handle_experiment_params(self, data):
        """Обработчик параметров эксперимента.
        
        Args:
            data (dict): Содержит:
                - step (int): Номер шага
                - frequency (float): Частота сигнала в Гц
                - temperature (float): Температура в °C
        """
        try:
            logger.info("Начало обработки параметров эксперимента")
            
            step = data.get('step')
            frequency = data.get('frequency')
            temperature = data.get('temperature')
            
            logger.debug(
                "Полученные параметры:\n"
                f"  Шаг: {step}\n"
                f"  Частота: {frequency} Гц\n"
                f"  Температура: {temperature}°C"
            )

            # Валидация параметров
            if None in (step, frequency, temperature):
                logger.error(f"Отсутствуют обязательные параметры: step={step}, frequency={frequency}, temperature={temperature}")
                await self.send_error("Требуются: step, frequency, temperature")
                return

            if not isinstance(frequency, (int, float)) or frequency <= 0:
                logger.error(f"Некорректная частота: {frequency}")
                await self.send_error("Частота должна быть положительным числом")
                return

            if not isinstance(temperature, (int, float)):
                logger.error(f"Некорректная температура: {temperature}")
                await self.send_error("Температура должна быть числом")
                return

            logger.info(
                "Параметры эксперимента получены\n"
                f"  Шаг {step}: частота={frequency} Гц, температура={temperature}°C"
            )

            step_index = step - 1
            if not (0 <= step_index < len(self.experiment_steps)):
                logger.error(f"Некорректный номер шага {step}. Допустимо от 1 до {len(self.experiment_steps)}")
                await self.send_error(f"Некорректный номер шага. Доступно этапов: {len(self.experiment_steps)}")
                return

            # Обновление данных шага в self.experiment_steps
            self.experiment_steps[step_index].update({
                'frequency': float(frequency),
                'temperature': float(temperature),
                'status': 'params_received'
            })
            
            self.current_step = step
            logger.info(f"Текущий шаг обновлен (локально): {self.current_step}")

            # Обновляем модель Experiments в БД
            self.experiment.temperature = float(temperature)
            self.experiment.stages = self.experiment_steps
            self.experiment.step = self.current_step
            
            await database_sync_to_async(self.experiment.save)()
            logger.info(f"Параметры для шага {step} (частота, температура, текущий шаг эксперимента) сохранены в БД для эксперимента {self.experiment_id}")

            # Подготовка подтверждения
            confirmation = {
                'type': 'step_confirmation',
                'step': step,
                'status': 'ready_for_recording',
                'frequency': float(frequency),
                'temperature': float(temperature)
            }
            
            if not await self.send_json(confirmation):
                logger.error("Не удалось отправить подтверждение шага")
            else:
                logger.info("Подтверждение шага успешно отправлено")

        except ValueError as e:
            logger.error(
                "Ошибка формата параметров\n"
                f"  Ошибка: {str(e)}\n"
                f"  Данные: {data}"
            )
            await self.send_error("Ошибка формата параметров")
        except Exception as e:
            logger.error(
                "Ошибка обработки параметров\n"
                f"  Тип ошибки: {type(e).__name__}\n"
                f"  Сообщение: {str(e)}\n"
                "  Трассировка:", exc_info=True
            )
            await self.send_error(f"Ошибка обработки параметров: {str(e)}")

    async def handle_distance_data(self, data):
        """Обработчик данных о расстоянии от датчика HC-SR04.
        
        Args:
            data (dict): Содержит:
                - distances (list): Список измерений расстояния
                - timestamps (list): Соответствующие временные метки
        """
        try:
            logger.info("[AudioConsumer] Начало обработки сообщения 'distance_data'.")
            
            distances = data.get('distances', [])
            timestamps = data.get('timestamps', [])
            
            logger.debug(
                f"[AudioConsumer] Получены данные о расстоянии: "
                f"Количество измерений: {len(distances)}, "
                f"Количество временных меток: {len(timestamps)}. "
                f"Пример данных: distances[:5]={distances[:5]}, timestamps[:5]={timestamps[:5]}"
            )

            if not distances or not timestamps:
                logger.warning(
                    f"[AudioConsumer] Получены пустые или неполные данные о расстоянии. "
                    f"distances: {len(distances)} элементов, timestamps: {len(timestamps)} элементов. Данные не будут сохранены."
                )
                # Не сбрасываем существующие self.distance_samples, если пришли пустые данные
                return
                
            if len(distances) != len(timestamps):
                logger.warning(
                    f"[AudioConsumer] Несоответствие количества измерений и временных меток. "
                    f"distances: {len(distances)}, timestamps: {len(timestamps)}. Данные не будут сохранены."
                )
                # Не сбрасываем существующие self.distance_samples
                return

            # Сохранение данных
            self.distance_samples = distances
            self.distance_timestamps = timestamps
            
            logger.info(
                f"[AudioConsumer] Данные о расстоянии успешно сохранены в экземпляре AudioConsumer. "
                f"Общее количество измерений: {len(self.distance_samples)}. "
                f"Временной диапазон: {min(self.distance_timestamps):.3f}-{max(self.distance_timestamps):.3f} сек (если не пусто)"
            )
            
        except Exception as e:
            logger.error(
                f"[AudioConsumer] Ошибка обработки данных о расстоянии: {type(e).__name__} - {str(e)}", 
                exc_info=True
            )
            await self.send_error("Ошибка обработки данных о расстоянии на сервере")


    async def process_complete_audio(self, data):
        """Модифицированный обработчик аудио с интеграцией данных о расстоянии."""
        try:
            step = data.get('step')
            audio_data = data.get('data')
            
            if not (step and isinstance(step, int) and 0 < step <= len(self.experiment_steps)):
                logger.error(f"Некорректный или отсутствующий номер шага: {step}. Доступно этапов: {len(self.experiment_steps)}")
                await self.send_error("Некорректный или отсутствующий номер шага")
                return
            
            if not audio_data:
                logger.error("Отсутствуют аудио данные (data).")
                await self.send_error("Требуются аудио данные (data)")
                return

            step_index = step - 1
            logger.info(f"Обработка аудио для шага {step}")
            logger.debug(f"Текущие шаги эксперимента: {self.experiment_steps}")

            try:
                audio_bytes = base64.b64decode(audio_data)
                logger.debug(f"Декодировано {len(audio_bytes)} байт аудио")
                
                samples, decoded_sample_rate = await self.decode_audio(audio_bytes, data.get('format', 'webm'))
                self.sample_rate = decoded_sample_rate
                filtered = self.apply_butterworth_filter(samples, self.sample_rate)
                
                # Находим минимумы и сопоставляем с расстояниями
                minima = self.find_minima(filtered, self.sample_rate)
                
                # Проверяем наличие данных для текущего шага
                if step > len(self.experiment_steps):
                    logger.error(f"Шаг {step} не инициализирован. Доступные шаги: {len(self.experiment_steps)}")
                    await self.send_error(f"Параметры для шага {step} не были установлены")
                    return

                if step <= len(self.experiment_steps):
                    self.experiment_steps[step_index].update({
                        'audio_samples': samples.tolist(),
                        'minima': minima,
                        'status': 'audio_processed',
                        'distance_samples': self.distance_samples,
                        'distance_timestamps': self.distance_timestamps
                    })

                # Убедимся, что параметры для шага были установлены
                current_step_params = self.experiment_steps[step_index]
                if current_step_params.get('status') != 'params_received' and current_step_params.get('status') != 'audio_processed':
                    # Если параметры не были установлены ранее через experiment_params, 
                    # попробуем взять их из data, если они там есть (как fallback)
                    fallback_frequency = data.get('frequency')
                    fallback_temperature = data.get('temperature')
                    if fallback_frequency and fallback_temperature :
                        logger.warning(f"Параметры для шага {step} не были предварительно установлены, используем из сообщения complete_audio: f={fallback_frequency}, t={fallback_temperature}")
                        current_step_params['frequency'] = float(fallback_frequency)
                        current_step_params['temperature'] = float(fallback_temperature)
                    else:
                        logger.error(f"Параметры для шага {step} не были установлены, и отсутствуют в сообщении complete_audio. Этап: {current_step_params}")
                        await self.send_error(f"Параметры для шага {step} не установлены.")
                        return

                response = {
                    'type': 'minima_data',
                    'step': int(step),
                    'minima': minima,
                    'frequency': float(self.experiment_steps[step_index]['frequency']),
                    'temperature': float(self.experiment_steps[step_index]['temperature'])
                }
                
                if not await self.send_json(response):
                    logger.error("Не удалось отправить данные минимумов")

                if (step == self.max_steps and 
                    all(s.get('status') == 'audio_processed' for s in self.experiment_steps)):
                    await self.calculate_final_results()

            except ValueError as e:
                logger.error(f"Ошибка обработки аудио: {str(e)}")
                await self.send_error(f"Ошибка обработки аудио: {str(e)}")
            except Exception as e:
                logger.error(f"Неожиданная ошибка обработки: {str(e)}", exc_info=True)
                await self.send_error(f"Ошибка обработки аудио: {str(e)}")

        except Exception as e:
            logger.error(f"Ошибка обработки аудиоданных: {str(e)}", exc_info=True)
            await self.send_error(f"Ошибка обработки аудио: {str(e)}")

    def _plot_minima_with_distances(self, data, envelope, minima):
        """Сохранение графика с отмеченными минимумами и расстояниями."""
        try:
            os.makedirs('plots', exist_ok=True)
            
            plt.figure(figsize=(12, 6))
            
            # Основной график сигнала
            plt.subplot(2, 1, 1)
            plt.plot(data, label='Сигнал', alpha=0.5)
            plt.plot(envelope, label='Огибающая', alpha=0.7)
            
            # Отмечаем минимумы с подписями расстояний
            for m in minima:
                plt.plot(m['position'], envelope[m['position']], 
                        'rx', markersize=8)
                plt.text(m['position'], envelope[m['position']], 
                        f"{m['distance']:.1f} мм", fontsize=8)
            
            plt.title(f"Шаг {self.current_step}: {len(minima)} минимумов")
            plt.legend()
            
            # График расстояний
            plt.subplot(2, 1, 2)
            if self.distance_timestamps and self.distance_samples:
                plt.plot(self.distance_timestamps, self.distance_samples, 
                        'g-', label='Расстояние (мм)')
                plt.xlabel('Время (с)')
                plt.ylabel('Расстояние (мм)')
                plt.legend()
            
            plt.tight_layout()
            plt.savefig(f'plots/step_{self.current_step}_minima_distances.png', dpi=100)
            plt.close()
            
            logger.info(f"График сохранен: plots/step_{self.current_step}_minima_distances.png")
        except Exception as e:
            logger.error(f"Ошибка сохранения графика: {str(e)}")

    async def calculate_final_results(self):
        """Модифицированный расчет результатов с использованием расстояний."""
        try:
            logger.info("Расчет финальных результатов с учетом расстояний...")
            
            results_summary = [] 
            for idx, step_data in enumerate(self.experiment_steps, 1):
                if not step_data.get('minima'):
                    logger.warning(f"Нет данных минимумов для шага {idx}")
                    continue
                
                minima_with_distances = step_data['minima']
                if not minima_with_distances or len(minima_with_distances) < 2:
                    logger.warning(f"Недостаточно минимумов с расстояниями для шага {idx}")
                    continue
                
                distances = [m['distance'] for m in minima_with_distances]
                times = [m['time'] for m in minima_with_distances]
                
                delta_distances = np.diff(distances)
                delta_times = np.diff(times)
                
                avg_speed_movement = np.mean(np.abs(delta_distances) / delta_times) if np.any(delta_times) else 0
                
                frequency = step_data.get('frequency')
                if not frequency:
                    logger.warning(f"Отсутствует частота для шага {idx}, пропускаем расчет скорости/гаммы.")
                    continue

                raw_speed = self.calculate_speed(minima_with_distances, frequency)
                corrected_speed = raw_speed + avg_speed_movement 
                gamma = self.calculate_gamma(corrected_speed, step_data.get('temperature', 20.0))
                
                step_data.update({
                    'system_speed': corrected_speed,
                    'system_gamma': gamma,
                    'raw_speed': raw_speed,
                    'movement_speed': avg_speed_movement
                })
                
                results_summary.append({
                    'step': idx,
                    'speed': round(corrected_speed, 4),
                    'gamma': round(gamma, 4),
                    'raw_speed': round(raw_speed, 4),
                    'movement_speed': round(avg_speed_movement, 4)
                })

            if not results_summary:
                logger.error("Не удалось рассчитать результаты ни для одного шага.")
                await self.send_error("Не удалось рассчитать финальные результаты.")
                return

            self.experiment.status = 'completed' # Статус основного эксперимента
            self.experiment.stages = self.experiment_steps
            await database_sync_to_async(self.experiment.save)()
            logger.info(f"Эксперимент {self.experiment.id} помечен как 'completed' в БД, результаты этапов обновлены.")

            avg_system_gamma = np.mean([s.get('system_gamma') for s in self.experiment_steps if s.get('system_gamma') is not None])
            if np.isnan(avg_system_gamma):
                avg_system_gamma = 0.0

            # Создаем или обновляем запись в Results со статусом 'pending_student_input'
            # Явно устанавливаем None для полей студента, чтобы очистить их, если они были заполнены ранее
            # и чтобы соответствовать null=True в модели, если БД требует явного None, а не отсутствия ключа.
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
            logger.info(f"Запись в Results для эксперимента {self.experiment.id} создана/обновлена со статусом 'pending_student_input'.")

            final_response_message = {
                'type': 'experiment_complete',
                'message': 'Эксперимент успешно завершен лаборантом и данные сохранены. Ожидается ввод от студента.',
                'steps': results_summary 
            }
            if not await self.send_json(final_response_message):
                logger.error("Не удалось отправить финальные результаты (после сохранения в БД)")

        except Exception as e:
            logger.error(f"Ошибка расчета финальных результатов: {str(e)}", exc_info=True)
            await self.send_error(f"Ошибка расчета финальных результатов: {str(e)}")

    async def validate_final_results(self, data):
        """Валидация результатов, введенных пользователем.
        
        Args:
            data (dict): Содержит:
                - studentSpeed (float): Введенная скорость звука
                - studentGamma (float): Введенный коэффициент γ
                
        Сравнивает с системными результатами и эталонными значениями.
        """
        try:
            student_speed = data.get('studentSpeed')
            student_gamma = data.get('studentGamma')
            
            if None in (student_speed, student_gamma):
                logger.error("Отсутствуют результаты студента")
                await self.send_error("Требуются studentSpeed и studentGamma")
                return

            logger.info(
                f"Валидация результатов: "
                f"скорость={student_speed}, γ={student_gamma}"
            )

            try:
                # Преобразуем в числа
                student_speed = float(student_speed)
                student_gamma = float(student_gamma)
            except (TypeError, ValueError) as e:
                logger.error(f"Неверный формат результатов: {str(e)}")
                await self.send_error("Результаты должны быть числами")
                return

            # Получаем валидные шаги с расчетами
            valid_steps = [s for s in self.experiment_steps 
                        if s.get('system_speed') is not None and 
                           s.get('system_gamma') is not None]
            
            if not valid_steps:
                logger.error("Нет валидных данных для сравнения")
                await self.send_error("Нет данных для валидации")
                return

            # Рассчитываем средние системные значения
            system_speed = np.mean([s['system_speed'] for s in valid_steps])
            system_gamma = np.mean([s['system_gamma'] for s in valid_steps])

            logger.debug(
                f"Сравнение: система(скорость={system_speed}, γ={system_gamma}) "
                f"vs студент(скорость={student_speed}, γ={student_gamma})"
            )
            
            # Вычисляем процентные ошибки
            speed_error = 0
            gamma_error_system = 0
            gamma_error_reference = 0
            
            if system_speed != 0:
                speed_error = abs((student_speed - system_speed) / system_speed * 100)
            
            if system_gamma != 0:
                gamma_error_system = abs((student_gamma - system_gamma) / system_gamma * 100)
            
            gamma_error_reference = abs((student_gamma - 1.4) / 1.4 * 100)
            
            # Проверяем соответствие допустимым погрешностям
            is_valid = bool(
                speed_error <= 5 and 
                gamma_error_system <= 5 and 
                gamma_error_reference <= 5
            )
            
            # Формируем ответ
            response = {
                'type': 'verification_result',
                'is_valid': is_valid,
                'system_speed': float(round(system_speed, 4)),
                'system_gamma': float(round(system_gamma, 4)),
                'student_speed': float(round(student_speed, 4)),
                'student_gamma': float(round(student_gamma, 4)),
                'speed_error': float(round(speed_error, 2)),
                'gamma_error_system': float(round(gamma_error_system, 2)),
                'gamma_error_reference': float(round(gamma_error_reference, 2))
            }
            
            logger.debug(f"Результат валидации: {response}")
            
            if not await self.send_json(response):
                logger.error("Не удалось отправить результат валидации")
            else:
                logger.info("Результаты валидации отправлены")

        except Exception as e:
            logger.error(f"Ошибка валидации: {str(e)}", exc_info=True)
            await self.send_error("Ошибка при валидации результатов")

    async def send_error(self, message):
        """Отправка сообщения об ошибке клиенту.
        
        Args:
            message (str): Текст сообщения об ошибке
        """
        error_data = {
            'type': 'error',
            'message': message,
            'step': self.current_step
        }
        await self.send_json(error_data)
        logger.error(f"Отправлена ошибка клиенту: {message}")

    def calculate_speed(self, minima, frequency):
        """Расчет скорости звука по временам минимумов.
        
        Args:
            minima (list): Список найденных минимумов
            frequency (float): Частота сигнала в Гц
            
        Returns:
            float: Рассчитанная скорость звука в м/с
        """
        if len(minima) < 2:
            logger.warning("Недостаточно минимумов для расчета")
            return 0
            
        # Вычисляем среднее время между минимумами
        times = [m['time'] for m in minima]
        avg_delta_t = np.mean(np.diff(times))
        
        # Частота появления минимумов
        mod_freq = 1 / avg_delta_t  
        
        # Калибровочный коэффициент (40 Гц - эталон)
        calibration_factor = mod_freq / 40  
        
        # Основная формула расчета
        return 343 / (2 * frequency * avg_delta_t) * calibration_factor * 100

    def calculate_gamma(self, v, temperature):
        """Расчет коэффициента γ (отношения теплоемкостей).
        
        Args:
            v (float): Скорость звука в м/с
            temperature (float): Температура воздуха в °C
            
        Returns:
            float: Значение коэффициента γ
            
        Формула: γ = (v² * μ) / (R * T)
        где:
        μ - молярная масса воздуха (0.029 кг/моль)
        R - универсальная газовая постоянная (8.314 Дж/(моль·К))
        T - температура в Кельвинах
        """
        if v <= 0:
            logger.warning(f"Некорректная скорость: {v} м/с")
            return 0
            
        R = 8.314  # Универсальная газовая постоянная
        mu = 0.029  # Молярная масса воздуха (кг/моль)
        T = temperature + 273.15  # Температура в Кельвинах
        
        gamma = (v ** 2 * mu) / (R * T)
        
        # Ограничиваем разумные значения для воздуха
        return max(1.0, min(1.7, gamma))

    async def decode_audio(self, audio_bytes, audio_format):
        """Декодирование аудиоданных из различных форматов.
        
        Args:
            audio_bytes (bytes): Бинарные аудиоданные
            audio_format (str): Формат аудио ('webm', 'opus', 'wav')
            
        Returns:
            tuple: (samples, sample_rate)
                samples (np.array): Нормализованные аудиоданные (-1..1)
                sample_rate (int): Частота дискретизации
            
        Raises:
            ValueError: Если формат не поддерживается
        """
        try:
            logger.debug(
                f"Декодирование аудио: формат={audio_format}, "
                f"размер={len(audio_bytes)} байт"
            )
            
            if audio_format in ['webm', 'opus']:
                # Декодирование через pydub для webm/opus
                sound = AudioSegment.from_file(
                    io.BytesIO(audio_bytes), 
                    format="webm",
                    codec="opus"
                )
                wav_io = io.BytesIO()
                sound.export(wav_io, format="wav")
                sample_rate, data = wavfile.read(wav_io)
            else:
                # Прямое чтение WAV файлов
                sample_rate, data = wavfile.read(io.BytesIO(audio_bytes))

            # Нормализация данных в диапазон [-1, 1]
            samples = data.astype(np.float32) / np.iinfo(data.dtype).max
            logger.debug(
                f"Декодировано: частота={sample_rate} Гц, "
                f"сэмплов={len(samples)}"
            )
            return samples, sample_rate

        except Exception as e:
            logger.error(f"Ошибка декодирования аудио: {str(e)}", exc_info=True)
            raise ValueError(f"Неподдерживаемый формат: {audio_format}")

    def apply_butterworth_filter(self, data, sample_rate, cutoff=10000, order=4):
        """Улучшенная версия фильтра с обработкой всех ошибок."""
        try:
            # Преобразуем в 1-D массив если нужно
            if data.ndim > 1:
                data = np.mean(data, axis=1) if data.shape[1] > 1 else data[:, 0]
            
            # Минимальная длина для filtfilt (3 * (max(len(a), len(b)) - 1)
            min_length = 3 * (2 * order + 1) - 1
            if len(data) < min_length:
                logger.warning(f"Слишком короткий сигнал ({len(data)}) для фильтрации. Требуется минимум {min_length} сэмплов")
                return data

            nyq = 0.5 * sample_rate
            normal_cutoff = cutoff / nyq
            
            b, a = butter(order, normal_cutoff, btype='low', analog=False)
            filtered = filtfilt(b, a, data)
            
            logger.debug(f"Фильтрация успешна. Диапазон: [{np.min(filtered):.3f}, {np.max(filtered):.3f}]")
            return filtered
        except Exception as e:
            logger.error(f"Ошибка фильтрации: {str(e)}", exc_info=True)
            return data

    def find_minima(self, data, sample_rate):
        """Поиск минимумов с защитой от пустых данных о расстояниях."""
        try:
            # Конвертируем в 1-D массив
            if data.ndim > 1:
                data = np.mean(data, axis=1) if data.shape[1] > 1 else data[:, 0]
            
            if len(data) < 100:
                logger.warning("Слишком короткий сигнал для анализа минимумов")
                return []

            analytic_signal = hilbert(data)
            amplitude_envelope = np.abs(analytic_signal)
            normalized = amplitude_envelope / np.max(amplitude_envelope)
            inverted = 1 - normalized
            
            peaks, _ = find_peaks(
                inverted,
                height=self.minima_params['min_amplitude'],
                distance=int(sample_rate * self.minima_params['min_distance']),
                prominence=self.minima_params['min_prominence'],
                width=int(sample_rate * self.minima_params['min_width'])
            )
            
            significant_minima = []
            for idx in peaks:
                if 10 < idx < len(data)-10:
                    left_avg = np.mean(amplitude_envelope[idx-10:idx])
                    right_avg = np.mean(amplitude_envelope[idx:idx+10])
                    if left_avg > amplitude_envelope[idx] and right_avg > amplitude_envelope[idx]:
                        significant_minima.append(idx)
            
            minima_list = []
            for p in significant_minima:
                time_at_minima = p / sample_rate
                distance = 0  # Значение по умолчанию
                
                # Обработка случая когда нет данных о расстояниях
                if self.distance_timestamps and self.distance_samples:
                    try:
                        closest_idx = np.argmin(np.abs(np.array(self.distance_timestamps) - time_at_minima))
                        
                        distance = self.distance_samples[closest_idx] if closest_idx < len(self.distance_samples) else 0
                        logger.info("Дистанция минимума = ", distance)                    
                    except ValueError:
                        logger.warning("Не удалось найти ближайшее расстояние")
                
                minima_list.append({
                    'position': int(p),
                    'amplitude': float(data[p]),
                    'time': float(time_at_minima),
                    'distance': float(distance)
                })

            self._plot_minima_with_distances(data, amplitude_envelope, minima_list)
            logger.debug(f"Найдено {len(minima_list)} минимумов")
            return minima_list
        
        except Exception as e:
            logger.error(f"Ошибка поиска минимумов: {str(e)}", exc_info=True)
            return []

    def _plot_minima(self, data, envelope, minima_indices):
        """Сохранение графика сигнала с отмеченными минимумами.
        
        Args:
            data (np.array): Исходный сигнал
            envelope (np.array): Амплитудная огибающая
            minima_indices (list): Индексы найденных минимумов
            
        Сохраняет график в папку plots/ для визуальной проверки.
        """
        try:
            os.makedirs('plots', exist_ok=True)  # Создаем папку если нужно
            
            plt.figure(figsize=(12, 6))  # Создаем фигуру
            
            # Рисуем исходный сигнал и огибающую
            plt.plot(data, label='Сигнал', alpha=0.5)
            plt.plot(envelope, label='Огибающая', alpha=0.7)
            
            # Отмечаем минимумы красными крестами
            plt.plot(minima_indices, envelope[minima_indices], 
                    'rx', label='Минимумы', markersize=8)
            
            plt.title(f"Шаг {self.current_step}: {len(minima_indices)} минимумов")
            plt.legend()
            
            # Сохраняем в файл
            plt.savefig(f'plots/step_{self.current_step}_minima.png', dpi=100)
            plt.close()  # Закрываем фигуру
            
            logger.info(f"График сохранен: plots/step_{self.current_step}_minima.png")
        except Exception as e:
            logger.error(f"Ошибка сохранения графика: {str(e)}")

    async def send_json(self, data):
        """Отправка данных в формате JSON через WebSocket.
        
        Args:
            data: Данные для отправки (dict или list)
            
        Returns:
            bool: True если отправка успешна, False в случае ошибки
        """
        try:
            if not self.connected:
                logger.warning(
                    "Попытка отправки при разорванном соединении\n"
                    f"  Текущее состояние: connected={self.connected}"
                )
                return False
                
            def convert(obj):
                """Рекурсивная конвертация numpy типов в Python типы."""
                if isinstance(obj, (np.integer, np.int64)):
                    return int(obj)
                elif isinstance(obj, np.floating):
                    return float(obj)
                elif isinstance(obj, np.ndarray):
                    return obj.tolist()
                return obj
                
            message = json.dumps({k: convert(v) for k, v in data.items()})
            await self.send(text_data=message)
            
            logger.debug(
                "Данные успешно отправлены\n"
                f"  Тип сообщения: {data.get('type')}\n"
                f"  Размер сообщения: {len(message)} байт"
            )
            return True
        except Exception as e:
            logger.error(
                "Ошибка при отправке JSON\n"
                f"  Тип ошибки: {type(e).__name__}\n"
                f"  Сообщение: {str(e)}\n"
                "  Трассировка:", exc_info=True
            )
            self.connected = False
            return False

    async def handle_start_recording(self, data):
        """Обработчик начала записи.
        
        Args:
            data (dict): Входящее сообщение с параметрами записи
        """
        try:
            step = data.get('step')
            if not step or not isinstance(step, int):
                await self.send_error("Не указан или некорректный номер шага")
                return
                
            logger.info(
                "Начало записи\n"
                f"  Шаг: {step}\n"
                f"  Текущий шаг: {self.current_step}"
            )
            
            # Отправляем подтверждение начала записи
            await self.send_json({
                'type': 'recording_started',
                'step': step,
                'status': 'recording'
            })
            
        except Exception as e:
            logger.error(
                "Ошибка при начале записи\n"
                f"  Тип ошибки: {type(e).__name__}\n"
                f"  Сообщение: {str(e)}\n"
                "  Трассировка:", exc_info=True
            )
            await self.send_error(f"Ошибка начала записи: {str(e)}")

    async def handle_stop_recording(self, data):
        """Обработчик остановки записи.
        
        Args:
            data (dict): Входящее сообщение с параметрами записи
        """
        try:
            step = data.get('step')
            if not step or not isinstance(step, int):
                await self.send_error("Не указан или некорректный номер шага")
                return
                
            logger.info(
                "Остановка записи\n"
                f"  Шаг: {step}\n"
                f"  Текущий шаг: {self.current_step}"
            )
            
            # Отправляем подтверждение остановки записи
            await self.send_json({
                'type': 'recording_stopped',
                'step': step,
                'status': 'stopped'
            })
            
        except Exception as e:
            logger.error(
                "Ошибка при остановке записи\n"
                f"  Тип ошибки: {type(e).__name__}\n"
                f"  Сообщение: {str(e)}\n"
                "  Трассировка:", exc_info=True
            )
            await self.send_error(f"Ошибка остановки записи: {str(e)}")

    async def test_audio_processing(self):
        """Тестовая обработка сгенерированного аудиосигнала.
        
        Генерирует сигнал с известными параметрами, обрабатывает его
        и проверяет корректность работы алгоритмов.
        """
        try:
            logger.info("Запуск тестовой обработки аудио...")
            
            # Параметры тестового сигнала
            sample_rate = 48000  # Частота дискретизации
            duration = 0.5  # Длительность сигнала в секундах
            t = np.linspace(0, duration, int(sample_rate * duration))  # Временная шкала
            
            # Параметры модуляции
            main_freq = 2000  # Частота несущего сигнала (Гц)
            mod_freq = 40  # Частота модуляции (Гц)
            mod_depth = 0.7  # Глубина модуляции (0..1)
            
            # Генерация сигнала с амплитудной модуляцией
            carrier = np.sin(2 * np.pi * main_freq * t)  # Несущий сигнал
            modulator = 1 + mod_depth * np.sin(2 * np.pi * mod_freq * t)  # Огибающая
            signal = carrier * modulator  # Модулированный сигнал
            
            # Добавляем шум для реалистичности
            noise = np.random.normal(0, 0.05 * mod_depth, len(t))
            samples = signal + noise
            
            logger.debug(
                f"Тестовый сигнал: частота={main_freq}Гц, "
                f"мод.частота={mod_freq}Гц, "
                f"глубина={mod_depth}, длительность={duration}с"
            )

            # Обработка сигнала
            filtered = self.apply_butterworth_filter(samples, sample_rate)
            minima = self.find_minima(filtered, sample_rate)
            
            if len(minima) >= 2:
                # Расчет физических параметров
                speed = self.calculate_speed(minima, main_freq)
                gamma = self.calculate_gamma(speed, 20)  # Для 20°C
                
                # Анализ результатов
                delta_times = np.diff([m['time'] for m in minima])
                avg_delta_t = np.mean(delta_times)
                
                logger.info(f"""
                ТЕСТОВЫЕ РЕЗУЛЬТАТЫ:
                Найдено минимумов: {len(minima)}
                Средний интервал: {avg_delta_t:.6f} сек
                Частота минимумов: {1/avg_delta_t:.2f} Гц
                Рассчитанная скорость: {speed:.2f} м/с
                Рассчитанный γ: {gamma:.4f}
                Ожидаемая скорость: ~343 м/с
                Ожидаемый γ: ~1.4
                """)
            else:
                logger.warning("Недостаточно минимумов для анализа")

        except Exception as e:
            logger.error(f"Ошибка тестовой обработки: {str(e)}", exc_info=True)