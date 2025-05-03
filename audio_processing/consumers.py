import json
import logging
import base64
import numpy as np
from channels.generic.websocket import AsyncWebsocketConsumer
from scipy.io import wavfile
from scipy.signal import find_peaks, butter, filtfilt
import io
from datetime import datetime
from pydub import AudioSegment

logger = logging.getLogger(__name__)

class AudioConsumer(AsyncWebsocketConsumer):
    def __init__(self):
        super().__init__()
        self.sample_rate = None  # Инициализация атрибута
        logger.info("AudioConsumer initialized")

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

            # Декодирование аудио и сохранение sample_rate
            samples, self.sample_rate = await self.decode_audio(audio_bytes, data.get('format'))
            logger.info("🔵 Audio decoded | SR: %s Hz | Duration: %.2f s", 
                       self.sample_rate, len(samples)/self.sample_rate)

            # Обработка сигнала
            filtered = self.apply_butterworth_filter(samples, self.sample_rate)
            minima = self.find_minima(filtered, self.sample_rate)
            logger.info("🔵 Found %d minima | First: %.2fs", len(minima), minima[0]['time'] if minima else 0)

            # Отправка результатов с sample_rate
            await self.send_results(minima, samples)
            logger.info("🟢 Successfully sent results")

        except Exception as e:
            logger.error("🔴 Audio processing failed: %s", str(e))
            await self.send_error("Audio processing error")

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

            # Нормализация данных
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

    def find_minima(self, data, sample_rate, min_distance=0.1):
        min_samples = int(sample_rate * min_distance)
        peaks, _ = find_peaks(-data, distance=min_samples)
        return [{
            'time': round(p/sample_rate, 2),
            'amplitude': float(data[p])
        } for p in peaks]

    async def send_results(self, minima, waveform):
        try:
            # Уменьшаем количество точек до 1000 с равномерным шагом
            step = max(1, len(waveform) // 1000)
            reduced_waveform = waveform[::step].tolist()

            response = {
                'type': 'analysis_result',
                'minima': minima[:5],
                'waveform': reduced_waveform,
                'sample_rate': self.sample_rate,
                'duration': len(waveform) / self.sample_rate  # Добавляем длительность
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