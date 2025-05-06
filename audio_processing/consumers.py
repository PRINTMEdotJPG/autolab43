import json
import logging
import base64
import numpy as np
from channels.generic.websocket import AsyncWebsocketConsumer
from scipy.io import wavfile
from scipy.signal import hilbert, find_peaks, butter, filtfilt
import io
from datetime import datetime
from pydub import AudioSegment

logger = logging.getLogger(__name__)

class AudioConsumer(AsyncWebsocketConsumer):
    def __init__(self):
        super().__init__()
        self.sample_rate = None
        self.movement_speed = 0.01  # м/с (калибровать под установку)
        self.minima_params = {
            'min_amplitude': 0.05,  # 5% от макс. амплитуды
            'min_distance': 0.3,    # мин. расстояние между минимумами (с)
            'min_prominence': 0.1,  # мин. "выраженность" минимума
            'min_width': 0.1        # мин. длительность минимума (с)
        }

    async def connect(self):
        await self.accept()
        logger.info("🟢 WebSocket connection established | Client: %s", self.scope["client"])

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            logger.debug("📥 Received message type: %s", data.get('type'))
            
            if data.get('type') == 'audio_data':
                await self.process_audio(data)
                
        except json.JSONDecodeError as e:
            error_msg = f"JSON decode error: {str(e)}"
            logger.error("🔴 %s | Data: %s", error_msg, text_data[:100])
            await self.send_error("Invalid JSON format")
            
        except Exception as e:
            logger.exception("🔴 Critical error in receive")
            await self.send_error("Internal server error")

    async def process_audio(self, data):
        try:
            logger.info("🔵 Starting audio processing")
            audio_bytes = base64.b64decode(data['data'])
            logger.debug("Decoded audio size: %s KB", len(audio_bytes)//1024)

            samples, self.sample_rate = await self.decode_audio(audio_bytes, data.get('format'))
            logger.info("🔵 Audio decoded | SR: %s Hz | Duration: %.2f s", 
                       self.sample_rate, len(samples)/self.sample_rate)

            filtered = self.apply_butterworth_filter(samples, self.sample_rate)
            minima = self.find_minima(filtered, self.sample_rate)
            logger.info("🔵 Found %d minima | First: %.2fs", len(minima), minima[0]['time'] if minima else 0)

            # Генерация позиций для графика
            positions = np.arange(len(filtered)) * self.movement_speed / self.sample_rate
            await self.send_results(minima, filtered, positions)
            logger.info("🟢 Successfully sent results")

        except Exception as e:
            logger.error("🔴 Audio processing failed: %s", str(e))
            await self.send_error(f"Audio processing error: {str(e)}")

    async def decode_audio(self, audio_bytes, format):
        try:
            logger.debug("🔍 Decoding %s audio", format)
            
            if format == 'webm':
                sound = AudioSegment.from_file(io.BytesIO(audio_bytes), format="webm")
                wav_io = io.BytesIO()
                sound.export(wav_io, format="wav")
                sample_rate, data = wavfile.read(wav_io)
            else:
                sample_rate, data = wavfile.read(io.BytesIO(audio_bytes))

            samples = data.astype(np.float32) / np.iinfo(data.dtype).max
            return samples, sample_rate

        except Exception as e:
            logger.error("🔴 Decoding failed: %s", str(e))
            raise ValueError(f"Unsupported audio format: {format}")

    def apply_butterworth_filter(self, data, sample_rate, cutoff=5000, order=4):
        nyq = 0.5 * sample_rate
        normal_cutoff = cutoff / nyq
        b, a = butter(order, normal_cutoff, btype='low', analog=False)
        return filtfilt(b, a, data)

    def find_minima(self, data, sample_rate, min_amplitude=0.2, min_distance=0.3):
        """
        Улучшенный поиск интерференционных минимумов.
        Возвращает список словарей с позицией (м), амплитудой и временем.
        """
        try:
            # Применяем преобразование Гильберта для получения огибающей
            analytic_signal = hilbert(data)
            amplitude_envelope = np.abs(analytic_signal)
            
            # Нормализация и инверсия для поиска минимумов как пиков
            normalized = 1 - (amplitude_envelope / np.max(amplitude_envelope))
            
            # Находим все кандидаты в минимумы
            peaks, properties = find_peaks(
                normalized,
                height=1-min_amplitude,
                distance=int(sample_rate * min_distance),
                prominence=0.15,
                width=int(sample_rate * 0.1))  # минимальная длительность 100 мс
            
            # Фильтрация по "значимости" минимума
            significant_minima = []
            for i in range(len(peaks)):
                idx = peaks[i]
                # Проверяем, что это действительно минимум (окружающие точки выше)
                if idx > 10 and idx < len(data)-10:  # проверяем границы
                    left_avg = np.mean(amplitude_envelope[idx-10:idx])
                    right_avg = np.mean(amplitude_envelope[idx:idx+10])
                    if left_avg > amplitude_envelope[idx] and right_avg > amplitude_envelope[idx]:
                        significant_minima.append(idx)
            
            return [{
                'position': round(p * self.movement_speed / sample_rate, 4),
                'amplitude': float(data[p]),
                'time': round(p/sample_rate, 2),
                'prominence': float(properties['prominences'][i]) if 'prominences' in properties else 0
            } for i, p in enumerate(significant_minima)]
        
        except Exception as e:
            logger.error(f"Error in find_minima: {str(e)}", exc_info=True)
            return []

    async def send_results(self, minima, waveform, positions):
        try:
            step = max(1, len(waveform) // 1000)
            response = {
                'type': 'analysis_result',
                'minima': minima[:10],
                'waveform': waveform[::step].tolist(),
                'positions': positions[::step].tolist(),
                'sample_rate': self.sample_rate,
                'movement_speed': self.movement_speed
            }
            await self.send(json.dumps(response))
        except Exception as e:
            logger.error("Ошибка отправки результатов: %s", str(e))
            await self.send_error("Ошибка обработки данных")

    async def send_error(self, message):
        await self.send(json.dumps({
            'type': 'error',
            'message': message
        }))
        logger.error("📤 Sent error message: %s", message)

