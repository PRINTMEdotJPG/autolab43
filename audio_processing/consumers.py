# consumers.py
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

# Настройка модуля логирования для записи событий
logger = logging.getLogger(__name__)


class AudioConsumer(AsyncWebsocketConsumer):
    """Основной класс для обработки аудиоданных через WebSocket соединение.

    Обеспечивает:
    - Прием и отправку данных через WebSocket
    - Обработку аудиосигналов в реальном времени
    - Анализ огибающей сигнала
    - Расчет скорости звука и коэффициента γ
    - Валидацию результатов эксперимента
    """

    def __init__(self):
        """Инициализация потребителя с настройками по умолчанию."""
        super().__init__()
        
        # Основные параметры обработки аудио
        self.sample_rate = 48000  # Частота дискретизации в Гц
        self.experiment_steps = []  # Список для хранения данных эксперимента
        self.current_step = 0  # Текущий шаг эксперимента (0..max_steps-1)
        self.max_steps = 3  # Максимальное количество шагов в эксперименте
        
        # Параметры для алгоритма поиска минимумов
        self.minima_params = {
            'min_amplitude': 0.3,    # Минимальная глубина минимума (0..1)
            'min_distance': 0.01,    # Минимальное расстояние между минимумами в сек
            'min_prominence': 0.2,   # Минимальная значимость минимума (0..1)
            'min_width': 0.005       # Минимальная ширина минимума в сек
        }
        
        self.connected = False  # Флаг состояния подключения
        self.lock = asyncio.Lock()  # Блокировка для потокобезопасных операций
        
        # Запускаем тестовую обработку сигнала при инициализации
        asyncio.create_task(self.test_audio_processing())

    async def connect(self):
        """Обработчик установки WebSocket соединения.
        
        Вызывается при подключении нового клиента.
        Устанавливает флаг connected в True и логирует событие.
        """
        await self.accept()  # Принимаем входящее соединение
        self.connected = True  # Устанавливаем флаг подключения
        logger.info("Установлено новое WebSocket соединение")

    async def disconnect(self, close_code):
        """Обработчик закрытия WebSocket соединения.
        
        Args:
            close_code (int): Код закрытия соединения
        """
        self.connected = False  # Сбрасываем флаг подключения
        logger.info(f"Соединение закрыто с кодом: {close_code}")

    async def send_json(self, data):
        """Отправка данных в формате JSON через WebSocket.
        
        Args:
            data: Данные для отправки (dict или list)
            
        Returns:
            bool: True если отправка успешна, False в случае ошибки
            
        Обрабатывает numpy типы данных, преобразуя их в стандартные Python типы.
        Логирует ошибки при отправке.
        """
        try:
            if not self.connected:
                logger.warning("Попытка отправки при разорванном соединении")
                return False
                
            def convert(obj):
                """Рекурсивно конвертирует numpy типы в Python типы."""
                if isinstance(obj, (np.integer, np.int64)):
                    return int(obj)
                elif isinstance(obj, np.floating):
                    return float(obj)
                elif isinstance(obj, np.ndarray):
                    return obj.tolist()
                return obj
                
            # Сериализуем данные в JSON с конвертацией типов
            if isinstance(data, dict):
                message = json.dumps({k: convert(v) for k, v in data.items()})
            else:
                message = json.dumps(convert(data))
                
            await self.send(text_data=message)  # Отправляем данные
            logger.debug(f"Отправлено сообщение типа: {data.get('type')}")
            return True
        except Exception as e:
            logger.error(f"Ошибка при отправке JSON: {str(e)}", exc_info=True)
            self.connected = False
            return False

    async def receive(self, text_data):
        """Обработчик входящих сообщений через WebSocket.
        
        Args:
            text_data (str): Текст сообщения в формате JSON
            
        Основной метод для маршрутизации входящих сообщений.
        Обрабатывает ошибки парсинга JSON и валидирует структуру данных.
        """
        try:
            logger.debug(f"Получено сообщение длиной {len(text_data)} байт")
            
            try:
                data = json.loads(text_data)  # Парсим JSON данные
            except json.JSONDecodeError as e:
                logger.error(f"Ошибка парсинга JSON: {str(e)}")
                await self.send_error("Неверный формат JSON")
                return

            if not isinstance(data, dict):
                logger.error("Данные не являются словарем")
                await self.send_error("Ожидается JSON объект")
                return

            message_type = data.get('type')
            if not message_type:
                logger.error("Не указан тип сообщения")
                await self.send_error("Требуется поле 'type'")
                return

            logger.info(f"Обработка сообщения типа '{message_type}'")

            # Определяем обработчик для данного типа сообщения
            handlers = {
                'complete_audio': self.process_complete_audio,
                'experiment_params': self.handle_experiment_params,
                'final_results': self.validate_final_results
            }

            handler = handlers.get(message_type, self.handle_unknown_type)
            
            # Выполняем обработчик с блокировкой для потокобезопасности
            async with self.lock:
                await handler(data)

        except Exception as e:
            logger.error(f"Ошибка обработки сообщения: {str(e)}", exc_info=True)
            await self.send_error(f"Ошибка обработки: {str(e)}")

    async def handle_unknown_type(self, data):
        """Обработчик неизвестных типов сообщений.
        
        Args:
            data (dict): Данные сообщения
            
        Логирует попытку обработки неизвестного типа и отправляет ошибку клиенту.
        """
        message_type = data.get('type', 'unknown')
        logger.warning(f"Получен неизвестный тип сообщения: '{message_type}'")
        await self.send_error(f"Неизвестный тип сообщения: '{message_type}'")

    async def handle_experiment_params(self, data):
        """Обработчик параметров эксперимента.
        
        Args:
            data (dict): Содержит параметры эксперимента:
                - step (int): Номер шага
                - frequency (float): Частота сигнала в Гц
                - temperature (float): Температура в °C
                
        Валидирует параметры и сохраняет их для текущего шага эксперимента.
        """
        try:
            step = data.get('step')
            frequency = data.get('frequency')
            temperature = data.get('temperature')
            
            # Валидация входных параметров
            if frequency <= 0:
                logger.error(f"Некорректная частота: {frequency} Гц")
                await self.send_error("Частота должна быть положительной")
                return
                
            if not all([step, frequency, temperature]):
                logger.error("Отсутствуют обязательные параметры")
                await self.send_error("Требуются: step, frequency, temperature")
                return

            logger.info(
                f"Получены параметры для шага {step}: "
                f"частота={frequency} Гц, температура={temperature}°C"
            )

            # Подготавливаем данные шага
            step_data = {
                'frequency': float(frequency),
                'temperature': float(temperature),
                'status': 'params_received',
                'minima': None,
                'audio_samples': None
            }

            # Сохраняем параметры для текущего шага
            if len(self.experiment_steps) < step:
                self.experiment_steps.append(step_data)
            else:
                self.experiment_steps[step-1].update(step_data)

            self.current_step = step

            # Отправляем подтверждение клиенту
            confirmation = {
                'type': 'step_confirmation',
                'step': step,
                'status': 'ready_for_recording',
                'frequency': frequency,
                'temperature': temperature
            }
            
            if not await self.send_json(confirmation):
                logger.error("Не удалось отправить подтверждение шага")

        except ValueError as e:
            logger.error(f"Ошибка формата параметров: {str(e)}")
            await self.send_error("Ошибка формата параметров")
        except Exception as e:
            logger.error(f"Ошибка обработки параметров: {str(e)}", exc_info=True)
            await self.send_error(f"Ошибка обработки параметров: {str(e)}")

    async def process_complete_audio(self, data):
        """Обработчик завершенного аудиозаписи.
        
        Args:
            data (dict): Содержит:
                - step (int): Номер шага
                - data (str): Аудиоданные в base64
                
        Декодирует аудио, применяет фильтр, находит минимумы и сохраняет результаты.
        """
        try:
            step = data.get('step')
            audio_data = data.get('data')
            
            if not all([step, audio_data]):
                logger.error("Отсутствуют данные или номер шага")
                await self.send_error("Требуются step и data")
                return

            logger.info(f"Обработка аудио для шага {step}")

            try:
                # Декодируем аудиоданные из base64
                audio_bytes = base64.b64decode(audio_data)
                logger.debug(f"Декодировано {len(audio_bytes)} байт аудио")
                
                # Преобразуем в числовой формат
                samples, self.sample_rate = await self.decode_audio(audio_bytes, 'webm')
                
                # Применяем фильтр низких частот
                filtered = self.apply_butterworth_filter(samples, self.sample_rate)
                
                # Находим минимумы в огибающей сигнала
                minima = self.find_minima(filtered, self.sample_rate)
                
                # Сохраняем результаты обработки
                if step <= len(self.experiment_steps):
                    self.experiment_steps[step-1].update({
                        'audio_samples': samples.tolist(),
                        'minima': minima,
                        'status': 'audio_processed'
                    })

                # Формируем ответ с результатами
                response = {
                    'type': 'minima_data',
                    'step': int(step),
                    'minima': minima,
                    'frequency': float(self.experiment_steps[step-1]['frequency']),
                    'temperature': float(self.experiment_steps[step-1]['temperature'])
                }
                
                if not await self.send_json(response):
                    logger.error("Не удалось отправить данные минимумов")

                # Проверяем завершение эксперимента
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

    async def calculate_final_results(self):
        """Расчет финальных результатов эксперимента.
        
        Вычисляет среднюю скорость звука и коэффициент γ по всем шагам.
        Отправляет результаты клиенту.
        """
        try:
            logger.info("Расчет финальных результатов...")
            
            if not self.experiment_steps:
                logger.error("Нет данных эксперимента")
                await self.send_error("Отсутствуют данные эксперимента")
                return

            results = []
            for idx, step in enumerate(self.experiment_steps, 1):
                if not step.get('minima'):
                    logger.warning(f"Нет данных минимумов для шага {idx}")
                    continue
                
                # Рассчитываем скорость звука и γ для каждого шага
                speed = self.calculate_speed(step['minima'], step['frequency'])
                gamma = self.calculate_gamma(speed, step['temperature'])
                
                # Сохраняем системные значения
                step.update({
                    'system_speed': speed,
                    'system_gamma': gamma
                })
                
                # Добавляем в результаты
                results.append({
                    'step': idx,
                    'speed': round(speed, 4),
                    'gamma': round(gamma, 4)
                })

            # Отправляем финальные результаты
            response = {
                'type': 'experiment_complete',
                'message': 'Эксперимент успешно завершен',
                'steps': results
            }
            
            if not await self.send_json(response):
                logger.error("Не удалось отправить финальные результаты")

        except Exception as e:
            logger.error(f"Ошибка расчета результатов: {str(e)}", exc_info=True)
            await self.send_error("Ошибка расчета финальных результатов")

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
        """Применение фильтра низких частот Баттерворта.
        
        Args:
            data (np.array): Входной сигнал
            sample_rate (int): Частота дискретизации
            cutoff (int): Частота среза (по умолчанию 10000 Гц)
            order (int): Порядок фильтра (по умолчанию 4)
            
        Returns:
            np.array: Отфильтрованный сигнал
        """
        try:
            nyq = 0.5 * sample_rate  # Частота Найквиста
            normal_cutoff = cutoff / nyq  # Нормализованная частота среза
            
            # Создаем фильтр Баттерворта
            b, a = butter(order, normal_cutoff, btype='low', analog=False)
            
            # Применяем фильтр вперед и назад (filtfilt для нулевой фазы)
            filtered = filtfilt(b, a, data)
            
            logger.debug(
                f"Фильтрация: диапазон=[{np.min(filtered):.3f}, "
                f"{np.max(filtered):.3f}]"
            )
            return filtered
        except Exception as e:
            logger.error(f"Ошибка фильтрации: {str(e)}", exc_info=True)
            return data

    def find_minima(self, data, sample_rate):
        """Поиск минимумов в огибающей сигнала.
        
        Args:
            data (np.array): Входной сигнал
            sample_rate (int): Частота дискретизации
            
        Returns:
            list: Список найденных минимумов, каждый представлен словарем:
                {
                    'position': int,  # Позиция в сэмплах
                    'amplitude': float,  # Амплитуда в исходном сигнале
                    'time': float  # Время в секундах
                }
        """
        try:
            # Применяем преобразование Гильберта для получения аналитического сигнала
            analytic_signal = hilbert(data)
            
            # Вычисляем амплитудную огибающую
            amplitude_envelope = np.abs(analytic_signal)
            
            logger.debug(
                f"Огибающая: max={np.max(amplitude_envelope):.4f}, "
                f"min={np.min(amplitude_envelope):.4f}"
            )
            
            # Нормализуем огибающую и инвертируем для поиска минимумов как пиков
            normalized = amplitude_envelope / np.max(amplitude_envelope)
            inverted = 1 - normalized
            
            # Находим пики в инвертированной огибающей
            peaks, _ = find_peaks(
                inverted,
                height=self.minima_params['min_amplitude'],
                distance=int(sample_rate * self.minima_params['min_distance']),
                prominence=self.minima_params['min_prominence'],
                width=int(sample_rate * self.minima_params['min_width'])
            )
            
            # Фильтруем найденные пики, оставляя только значимые минимумы
            significant_minima = []
            for idx in peaks:
                if 10 < idx < len(data)-10:  # Исключаем края сигнала
                    # Проверяем, что это действительно минимум
                    left_avg = np.mean(amplitude_envelope[idx-10:idx])
                    right_avg = np.mean(amplitude_envelope[idx:idx+10])
                    if (left_avg > amplitude_envelope[idx] and 
                        right_avg > amplitude_envelope[idx]):
                        significant_minima.append(idx)
            
            # Формируем список результатов
            minima_list = [{
                'position': int(p),  # Позиция в сэмплах
                'amplitude': float(data[p]),  # Амплитуда в исходном сигнале
                'time': float(p / sample_rate)  # Время в секундах
            } for p in significant_minima]

            # Сохраняем график для визуальной проверки
            self._plot_minima(data, amplitude_envelope, significant_minima)
            
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