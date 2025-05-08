# consumers.py
import json
import logging
import base64
import numpy as np
from channels.generic.websocket import AsyncWebsocketConsumer
from scipy.io import wavfile
from scipy.signal import hilbert, find_peaks, butter, filtfilt
import io
from pydub import AudioSegment
import asyncio

logger = logging.getLogger(__name__)

class AudioConsumer(AsyncWebsocketConsumer):
    def __init__(self):
        super().__init__()
        self.sample_rate = 44100
        self.movement_speed = 0.01  # м/с (калибровать под установку)
        self.experiment_steps = []
        self.current_step = 0
        self.max_steps = 3
        self.minima_params = {
            'min_amplitude': 0.2,
            'min_distance': 0.3,
            'min_prominence': 0.1,
            'min_width': 0.1
        }
        self.connected = False
        self.lock = asyncio.Lock()  # Для потокобезопасности

    async def connect(self):
        await self.accept()
        self.connected = True
        logger.info("WebSocket connection established")

    async def disconnect(self, close_code):
        self.connected = False
        logger.info(f"WebSocket disconnected with code: {close_code}")

    async def send_json(self, data):
        """Универсальный метод отправки JSON данных"""
        try:
            if not self.connected:
                logger.warning("Attempt to send data while disconnected")
                return False
                
            message = json.dumps(data)
            await self.send(text_data=message)
            logger.debug(f"Sent message: {data.get('type')}")
            return True
        except Exception as e:
            logger.error(f"Failed to send JSON: {str(e)}", exc_info=True)
            self.connected = False
            return False

    async def receive(self, text_data):
        """Основной обработчик входящих сообщений"""
        try:
            logger.debug(f"Received message length: {len(text_data)} bytes")
            
            try:
                data = json.loads(text_data)
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON received: {str(e)}")
                await self.send_error("Invalid JSON format")
                return

            if not isinstance(data, dict):
                logger.error("Received data is not a dictionary")
                await self.send_error("Message must be a JSON object")
                return

            message_type = data.get('type')
            if not message_type:
                logger.error("Message type not specified")
                await self.send_error("Message type is required")
                return

            logger.info(f"Processing message type: {message_type}")

            handlers = {
                'complete_audio': self.process_complete_audio,
                'experiment_params': self.handle_experiment_params,
                'final_results': self.validate_final_results
            }

            handler = handlers.get(message_type, self.handle_unknown_type)
            async with self.lock:
                await handler(data)

        except Exception as e:
            logger.error(f"Error in receive: {str(e)}", exc_info=True)
            await self.send_error(f"Processing error: {str(e)}")

    async def handle_unknown_type(self, data):
        """Обработка неизвестного типа сообщения"""
        message_type = data.get('type', 'unknown')
        logger.warning(f"Unknown message type: {message_type}")
        await self.send_error(f"Unknown message type: {message_type}")

    async def handle_experiment_params(self, data):
        """Обработка параметров эксперимента"""
        try:
            step = data.get('step')
            frequency = data.get('frequency')
            temperature = data.get('temperature')
            
            if not all([step, frequency, temperature]):
                logger.error("Missing required parameters in experiment params")
                await self.send_error("Missing required parameters: step, frequency, temperature")
                return

            logger.info(f"Received params for step {step}: freq={frequency}, temp={temperature}")

            step_data = {
                'frequency': float(frequency),
                'temperature': float(temperature),
                'status': 'params_received',
                'minima': None,
                'audio_samples': None
            }

            # Потокобезопасное обновление шагов
            if len(self.experiment_steps) < step:
                self.experiment_steps.append(step_data)
            else:
                self.experiment_steps[step-1].update(step_data)

            self.current_step = step

            confirmation = {
                'type': 'step_confirmation',
                'step': step,
                'status': 'ready_for_recording',
                'frequency': frequency,
                'temperature': temperature
            }
            
            if not await self.send_json(confirmation):
                logger.error("Failed to send step confirmation")

        except ValueError as e:
            logger.error(f"Invalid parameter format: {str(e)}")
            await self.send_error("Invalid parameter format")
        except Exception as e:
            logger.error(f"Error in handle_experiment_params: {str(e)}", exc_info=True)
            await self.send_error(f"Parameters processing error: {str(e)}")

    async def process_complete_audio(self, data):
        """Обработка полной аудиозаписи"""
        try:
            step = data.get('step')
            audio_data = data.get('data')
            
            if not all([step, audio_data]):
                logger.error("Missing audio data or step number")
                await self.send_error("Missing audio data or step number")
                return

            logger.info(f"Processing complete audio for step {step}")

            try:
                audio_bytes = base64.b64decode(audio_data)
                logger.debug(f"Decoded audio size: {len(audio_bytes)} bytes")
                
                samples, self.sample_rate = await self.decode_audio(audio_bytes, 'webm')
                
                filtered = self.apply_butterworth_filter(samples, self.sample_rate)
                minima = self.find_minima(filtered, self.sample_rate)
                
                if step <= len(self.experiment_steps):
                    self.experiment_steps[step-1].update({
                        'audio_samples': samples.tolist(),
                        'minima': minima,
                        'status': 'audio_processed'
                    })

                response = {
                    'type': 'minima_data',
                    'step': step,
                    'minima': minima,
                    'frequency': self.experiment_steps[step-1]['frequency'],
                    'temperature': self.experiment_steps[step-1]['temperature']
                }
                
                if not await self.send_json(response):
                    logger.error("Failed to send minima data")

                if (step == self.max_steps and 
                    all(s.get('status') == 'audio_processed' for s in self.experiment_steps)):
                    await self.calculate_final_results()

            except ValueError as e:
                logger.error(f"Audio processing failed: {str(e)}")
                await self.send_error(f"Audio processing error: {str(e)}")
            except Exception as e:
                logger.error(f"Unexpected error in audio processing: {str(e)}", exc_info=True)
                await self.send_error(f"Audio processing error: {str(e)}")

        except Exception as e:
            logger.error(f"Complete audio processing failed: {str(e)}", exc_info=True)
            await self.send_error(f"Audio processing error: {str(e)}")

    async def calculate_final_results(self):
        """Расчет финальных результатов"""
        try:
            logger.info("Calculating final results for all steps")
            
            if not self.experiment_steps:
                logger.error("No experiment data available")
                await self.send_error("No experiment data available")
                return

            results = []
            for idx, step in enumerate(self.experiment_steps, 1):
                if not step.get('minima'):
                    logger.warning(f"No minima data for step {idx}")
                    continue
                
                speed = self.calculate_speed(step['minima'], step['frequency'])
                gamma = self.calculate_gamma(speed, step['temperature'])
                
                step.update({
                    'system_speed': speed,
                    'system_gamma': gamma
                })
                
                results.append({
                    'step': idx,
                    'speed': round(speed, 4),
                    'gamma': round(gamma, 4)
                })

            response = {
                'type': 'experiment_complete',
                'message': 'Experiment completed successfully',
                'steps': results
            }
            
            if not await self.send_json(response):
                logger.error("Failed to send final results")

        except Exception as e:
            logger.error(f"Final calculation error: {str(e)}", exc_info=True)
            await self.send_error("Error in final calculations")

    async def validate_final_results(self, data):
        """Валидация результатов студента"""
        try:
            student_speed = data.get('studentSpeed')
            student_gamma = data.get('studentGamma')
            
            if None in (student_speed, student_gamma):
                logger.error("Missing student results data")
                await self.send_error("Missing studentSpeed or studentGamma")
                return

            logger.info(f"Validating student results: speed={student_speed}, gamma={student_gamma}")

            try:
                student_speed = float(student_speed)
                student_gamma = float(student_gamma)
            except (TypeError, ValueError) as e:
                logger.error(f"Invalid student results format: {str(e)}")
                await self.send_error("Invalid results format")
                return

            # Расчет системных значений
            valid_steps = [s for s in self.experiment_steps if s.get('system_speed') is not None]
            if not valid_steps:
                logger.error("No valid experiment steps for validation")
                await self.send_error("No valid experiment data")
                return

            system_speed = sum(s['system_speed'] for s in valid_steps) / len(valid_steps)
            system_gamma = sum(s['system_gamma'] for s in valid_steps) / len(valid_steps)
            
            # Расчет ошибок
            speed_error = abs((student_speed - system_speed) / system_speed * 100) if system_speed else 100
            gamma_error_system = abs((student_gamma - system_gamma) / system_gamma * 100) if system_gamma else 100
            gamma_error_reference = abs((student_gamma - 1.4) / 1.4 * 100)
            
            is_valid = (
                speed_error <= 5 and 
                gamma_error_system <= 5 and 
                gamma_error_reference <= 5
            )
            
            response = {
                'type': 'verification_result',
                'is_valid': is_valid,
                'system_speed': round(system_speed, 4),
                'system_gamma': round(system_gamma, 4),
                'student_speed': round(student_speed, 4),
                'student_gamma': round(student_gamma, 4),
                'speed_error': round(speed_error, 2),
                'gamma_error_system': round(gamma_error_system, 2),
                'gamma_error_reference': round(gamma_error_reference, 2)
            }
            
            if not await self.send_json(response):
                logger.error("Failed to send validation results")

        except Exception as e:
            logger.error(f"Validation error: {str(e)}", exc_info=True)
            await self.send_error("Results validation failed")

    async def send_error(self, message):
        """Отправка сообщения об ошибке"""
        error_data = {
            'type': 'error',
            'message': message,
            'step': self.current_step
        }
        await self.send_json(error_data)
        logger.error(f"Error sent to client: {message}")

    def calculate_speed(self, minima, frequency):
        """Расчет скорости звука"""
        if len(minima) < 2:
            logger.warning("Not enough minima points for speed calculation")
            return 0
            
        delta_positions = [minima[i]['position'] - minima[i-1]['position'] 
                        for i in range(1, len(minima))]
        
        if not delta_positions:
            logger.warning("Empty delta positions array")
            return 0
            
        avg_delta_L = sum(delta_positions) / len(delta_positions)
        wavelength = 2 * avg_delta_L
        return wavelength * frequency

    def calculate_gamma(self, v, temperature):
        """Расчет коэффициента адиабаты"""
        if v <= 0:
            logger.warning(f"Invalid speed value for gamma calculation: {v}")
            return 0
            
        R = 8.314  # Универсальная газовая постоянная [Дж/(моль·К)]
        mu = 0.029  # Молярная масса воздуха [кг/моль]
        T = temperature + 273.15  # Переводим в Кельвины
        return (v ** 2 * mu) / (R * T)

    async def decode_audio(self, audio_bytes, audio_format):
        """Декодирование аудио из различных форматов"""
        try:
            logger.debug(f"Decoding audio format: {audio_format}, size: {len(audio_bytes)} bytes")
            
            if audio_format in ['webm', 'opus']:
                sound = AudioSegment.from_file(
                    io.BytesIO(audio_bytes), 
                    format="webm",
                    codec="opus"
                )
                wav_io = io.BytesIO()
                sound.export(wav_io, format="wav")
                sample_rate, data = wavfile.read(wav_io)
            else:
                sample_rate, data = wavfile.read(io.BytesIO(audio_bytes))

            samples = data.astype(np.float32) / np.iinfo(data.dtype).max
            logger.debug(f"Decoded audio: sample_rate={sample_rate}, samples={len(samples)}")
            return samples, sample_rate

        except Exception as e:
            logger.error(f"Audio decoding failed: {str(e)}", exc_info=True)
            raise ValueError(f"Unsupported audio format: {audio_format}")

    def apply_butterworth_filter(self, data, sample_rate, cutoff=5000, order=4):
        """Применение фильтра Баттерворта"""
        try:
            nyq = 0.5 * sample_rate
            normal_cutoff = cutoff / nyq
            b, a = butter(order, normal_cutoff, btype='low', analog=False)
            return filtfilt(b, a, data)
        except Exception as e:
            logger.error(f"Butterworth filter failed: {str(e)}", exc_info=True)
            return data  # Возвращаем исходные данные при ошибке фильтрации

    def find_minima(self, data, sample_rate):
        """Поиск минимумов в аудиосигнале"""
        try:
            analytic_signal = hilbert(data)
            amplitude_envelope = np.abs(analytic_signal)
            normalized = 1 - (amplitude_envelope / np.max(amplitude_envelope))
            
            peaks, _ = find_peaks(
                normalized,
                height=1-self.minima_params['min_amplitude'],
                distance=int(sample_rate * self.minima_params['min_distance']),
                prominence=self.minima_params['min_prominence'],
                width=int(sample_rate * self.minima_params['min_width']))
            
            significant_minima = []
            for i in range(len(peaks)):
                idx = peaks[i]
                if idx > 10 and idx < len(data)-10:
                    left_avg = np.mean(amplitude_envelope[idx-10:idx])
                    right_avg = np.mean(amplitude_envelope[idx:idx+10])
                    if left_avg > amplitude_envelope[idx] and right_avg > amplitude_envelope[idx]:
                        significant_minima.append(idx)
            
            minima_list = [{
                'position': round(p * self.movement_speed / sample_rate, 4),
                'amplitude': float(data[p]),
                'time': round(p/sample_rate, 2)
            } for p in significant_minima]
            
            logger.debug(f"Found {len(minima_list)} minima points")
            return minima_list
        
        except Exception as e:
            logger.error(f"Error in find_minima: {str(e)}", exc_info=True)
            return []