import numpy as np
import scipy.signal as signal
import matplotlib.pyplot as plt
import random
import math
import json
from datetime import datetime
import logging

# Настройка логгера
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='simulate_sensors.log'
)
logger = logging.getLogger(__name__)


class ExperimentSimulator:
    """
    Класс для имитации эксперимента по определению отношения теплоемкостей воздуха
    методом интерференции.
    
    Атрибуты:
        temperature (float): Текущая температура воздуха в °C
        temperature_drift (float): Максимальный дрейф температуры
        mic_noise (int): Уровень шума микрофона
        position (float): Текущая позиция трубки в мм
        frequency_range (tuple): Диапазон частот в Гц
        initial_speed (float): Базовая скорость движения трубки в мм/с
    """

    def __init__(self):
        """Инициализация параметров эксперимента со случайными флуктуациями."""
        self.temperature = 20.0 + random.uniform(-2, 3)
        self.temperature_drift = 3.0
        self.mic_noise = 15
        self.position = 0
        self.frequency_range = (1500, 5500)
        self.initial_speed = 1.5
        logger.info("Инициализирован новый симулятор эксперимента")

    def generate_temperature(self) -> float:
        """
        Генерирует температуру с синусоидальным дрейфом и шумом.
        
        Returns:
            float: Обновленная температура в °C
        """
        drift = 0.1 * np.sin(2 * np.pi * np.random.uniform(0, 1))
        noise = random.uniform(-0.5, 0.5)
        self.temperature += drift + noise
        logger.debug(f"Новая температура: {self.temperature:.2f}°C")
        return self.temperature

    def generate_voltage(self) -> float:
        """
        Генерирует напряжение с небольшим случайным шумом.
        
        Returns:
            float: Значение напряжения в В
        """
        voltage = 5.0 + random.uniform(-0.2, 0.2)
        logger.debug(f"Сгенерировано напряжение: {voltage:.2f} В")
        return voltage

    def generate_microphone_signal(
        self,
        frequency: float,
        position: float,
        temperature: float
    ) -> float:
        """
        Моделирует сигнал микрофона с учетом интерференции и шума.
        
        Args:
            frequency: Частота звука в Гц
            position: Позиция трубки в мм
            temperature: Текущая температура в °C
            
        Returns:
            float: Значение сигнала микрофона в усл. ед.
        """
        delta_L = 2 * position / 1000  # Разность хода волн в метрах
        temperature_kelvin = temperature + 273.15
        
        # Параметры воздуха
        gamma = 1.4
        R = 287.05  # Удельная газовая постоянная (Дж/(кг·К))
        
        # Расчет скорости звука и длины волны
        v_sound = (gamma * R * temperature_kelvin) ** 0.5
        wavelength = v_sound / frequency
        
        # Моделирование сигнала с шумом
        signal_value = 600 * (1 + np.cos(2 * np.pi * delta_L / wavelength))
        signal_value += random.gauss(0, self.mic_noise)
        
        # Ограничение диапазона
        return np.clip(signal_value, 50, 950)

    def generate_position(self) -> float:
        """
        Обновляет позицию трубки с учетом скорости и случайного шума.
        
        Returns:
            float: Новая позиция трубки в мм
        """
        if self.position >= 1000:
            self.position = 0  # Сброс позиции
            logger.debug("Позиция трубки сброшена в 0")
            
        speed = self.initial_speed + random.uniform(-0.1, 0.1)
        self.position = min(self.position + speed, 1000)
        return self.position

    def find_interference_minima(
        self,
        signal_data: list
    ) -> tuple[np.ndarray, np.ndarray] | tuple[None, None]:
        """
        Находит минимумы интерференционной картины.
        
        Args:
            signal_data: Список значений сигнала
            
        Returns:
            tuple: (Сглаженный сигнал, индексы минимумов) или (None, None)
        """
        signal_array = np.array(signal_data)
        
        # Параметры сглаживания
        window_length = 51
        polyorder = 3
        
        try:
            smoothed_signal = signal.savgol_filter(
                signal_array,
                window_length,
                polyorder
            )
            peaks, _ = signal.find_peaks(
                -smoothed_signal,
                prominence=10,
                distance=20
            )
            
            if len(peaks) >= 2:
                return smoothed_signal, peaks
                
            logger.warning("Не найдено достаточное количество минимумов")
            return None, None
            
        except Exception as e:
            logger.error(f"Ошибка поиска минимумов: {str(e)}")
            return None, None

    def calculate_gamma(
        self,
        frequency: float,
        position: float,
        temperature: float
    ) -> tuple[float, float, float]:
        """
        Вычисляет коэффициент адиабаты γ.
        
        Args:
            frequency: Частота звука в Гц
            position: Позиция трубки в мм
            temperature: Температура в °C
            
        Returns:
            tuple: (γ, скорость звука в м/с, длина волны в м)
        """
        delta_L = 2 * position / 1000
        temperature_kelvin = temperature + 273.15
        
        # Физические константы
        gamma = 1.4
        R = 287.05  # Удельная газовая постоянная (Дж/(кг·К))
        molar_mass = 0.029  # Молярная масса воздуха (кг/моль)
        universal_gas_constant = 8.314  # Универсальная газовая постоянная
        
        # Расчет параметров
        v_sound = (gamma * R * temperature_kelvin) ** 0.5
        wavelength = v_sound / frequency
        
        # Расчет γ с небольшим случайным отклонением
        gamma_value = (
            (v_sound ** 2 * molar_mass) /
            (universal_gas_constant * temperature_kelvin)
        ) * random.uniform(0.998, 1.002)
        
        logger.debug(
            f"Рассчитано γ={gamma_value:.3f} для частоты {frequency} Гц"
        )
        return gamma_value, v_sound, wavelength

    def generate_random_frequencies(self, n: int = 3) -> list[float]:
        """
        Генерирует случайные частоты в заданном диапазоне.
        
        Args:
            n: Количество частот
            
        Returns:
            list: Список частот в Гц
        """
        frequencies = [
            round(random.uniform(*self.frequency_range), 2)
            for _ in range(n)
        ]
        logger.info(f"Сгенерированы частоты: {frequencies} Гц")
        return frequencies

    def run_experiment(
        self,
        frequencies: list[float] | None = None
    ) -> str:
        """
        Проводит эксперимент и возвращает результаты в формате JSON.
        
        Args:
            frequencies: Список частот в Гц (опционально)
            
        Returns:
            str: JSON-строка с результатами эксперимента
            
        Raises:
            ValueError: Если не удалось получить результаты
        """
        if frequencies is None:
            frequencies = self.generate_random_frequencies()
            logger.info("Использованы случайные частоты")

        results = []
        sensor_data = []
        timestamp = datetime.now().isoformat()
        logger.info(f"Начало эксперимента в {timestamp}")

        for freq in frequencies:
            self.generate_temperature()
            signal_data = []
            self.position = 0  # Сброс позиции для каждого эксперимента
            logger.debug(f"Обработка частоты {freq} Гц")

            for step in range(2000):
                current_pos = self.generate_position()
                mic_signal = self.generate_microphone_signal(
                    freq,
                    current_pos,
                    self.temperature
                )
                voltage = self.generate_voltage()

                signal_data.append(mic_signal)
                
                sensor_data.append({
                    'time_ms': step * 5,
                    'microphone_signal': mic_signal,
                    'tube_position': current_pos,
                    'voltage': voltage,
                    'frequency': freq
                })

            smoothed_signal, peaks = self.find_interference_minima(signal_data)

            if smoothed_signal is None or peaks is None:
                result = {
                    'frequency': freq,
                    'status': 'fail',
                    'reason': 'Not enough minima found.'
                }
                results.append(result)
                logger.warning(
                    f"Не удалось обработать частоту {freq} Гц: "
                    "недостаточно минимумов"
                )
                continue

            gamma_value, v_sound, wavelength = self.calculate_gamma(
                freq,
                self.position,
                self.temperature
            )

            result = {
                'frequency': freq,
                'status': 'success',
                'gamma': gamma_value,
                'speed_sound': v_sound,
                "sensor_data": sensor_data,
                'wavelength': wavelength,
                'timestamp': timestamp
            }
            results.append(result)
            logger.info(
                f"Успешно обработана частота {freq} Гц: "
                f"γ={gamma_value:.3f}, v={v_sound:.1f} м/с"
            )

        gamma_values = [r['gamma'] for r in results if r.get('status') == 'success']
        
        if not gamma_values:
            logger.error("Не удалось получить ни одного успешного результата")
            raise ValueError("Эксперимент не дал успешных результатов")
            
        gamma_calculated = np.mean(gamma_values)
        error_percent = abs(gamma_calculated - 1.4) / 1.4 * 100
        status = "success" if error_percent < 2.5 else "fail"
        
        output = {
            "temperature": self.temperature,
            "gamma_calculated": gamma_calculated,
            "gamma_reference": 1.4,
            "error_percent": error_percent,
            "status": status,
            "details": results,
            "timestamp": timestamp
        }

        logger.info(
            f"Эксперимент завершен: γ={gamma_calculated:.3f}, "
            f"отклонение={error_percent:.2f}%, статус={status}"
        )
        
        # Вывод результатов в консоль
        self._print_results(output, results)
        
        return json.dumps(output, indent=2)

    def _print_results(self, output: dict, results: list) -> None:
        """
        Выводит результаты эксперимента в консоль.
        
        Args:
            output: Основные результаты
            results: Детальные результаты
        """
        print(f"\n🔬 Результаты эксперимента #{output['timestamp']}")
        print(f"🌡 Температура: {output['temperature']:.1f}°C")
        print(f"📊 Гамма: {output['gamma_calculated']:.3f} "
              f"(эталон {output['gamma_reference']})")
        print(f"📉 Отклонение: {output['error_percent']:.2f}%")
        print("\nДетализация по частотам:")
        
        for result in results:
            if result.get('status') == 'success':
                print(f"✅ {result['frequency']} Гц: "
                      f"γ={result['gamma']:.3f} "
                      f"λ={result['wavelength']:.3f} м "
                      f"v={result['speed_sound']:.1f} м/с")
            else:
                print(f"❌ {result['frequency']} Гц: "
                      f"{result.get('reason', 'Неудача')}")


if __name__ == "__main__":
    try:
        logger.info("Запуск симулятора эксперимента")
        simulator = ExperimentSimulator()
        results = simulator.run_experiment(frequencies=[1700, 2300, 4000])
        print("\nJSON результаты:")
        print(results)
    except Exception as e:
        logger.critical(f"Критическая ошибка: {str(e)}", exc_info=True)
        print(f"Произошла ошибка: {str(e)}")