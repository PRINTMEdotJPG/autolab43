# simulate_sensors.py

import numpy as np
import logging
from dataclasses import dataclass
from typing import List, Dict

# Настройка логирования
logging.basicConfig(level=logging.INFO, filename='simulate_sensors.log',
                    format='%(asctime)s - %(levelname)s - %(message)s')

@dataclass
class VirtualArduino:
    """
    Класс, имитирующий поведение Arduino с подключенными датчиками.
    """
    temperature_range: tuple = (18.0, 25.0)  # °C
    temperature_error: float = 0.5  # °C
    adc_range: tuple = (0, 1023)
    position_range: tuple = (0.0, 1000.0)  # мм
    frequency_range: tuple = (1500, 6000)  # Гц
    current_frequency: float = 1500  # Гц по умолчанию

    def __post_init__(self):
        logging.info("Инициализация VirtualArduino")
        self.is_running = False

    def start(self):
        logging.info("Получена команда START")
        self.is_running = True

    def stop(self):
        logging.info("Получена команда STOP")
        self.is_running = False

    def set_frequency(self, frequency: float):
        if self.frequency_range[0] <= frequency <= self.frequency_range[1]:
            self.current_frequency = frequency
            logging.info(f"Частота установлена на {frequency} Гц")
        else:
            logging.error(f"Частота {frequency} Гц вне допустимого диапазона")
            raise ValueError("Частота вне допустимого диапазона")

    def read_temperature(self) -> float:
        """
        Возвращает случайную температуру в заданном диапазоне с погрешностью.
        """
        temp = np.random.uniform(*self.temperature_range)
        temp += np.random.normal(0, self.temperature_error)
        logging.debug(f"Температура: {temp:.2f}°C")
        return temp

    def read_adc(self, signal: np.ndarray) -> np.ndarray:
        """
        Имитирует показания АЦП микрофона.
        :param signal: массив сигналов
        :return: массив значений АЦП
        """
        adc_values = np.interp(signal, [-1, 1], self.adc_range)
        adc_values = adc_values + np.random.normal(0, 5, size=adc_values.shape)
        adc_values = np.clip(adc_values, *self.adc_range)
        logging.debug("Показания АЦП микрофона сгенерированы")
        return adc_values

    def read_position(self, num_points: int) -> np.ndarray:
        """
        Имитирует показания линейного датчика положения трубы.
        :param num_points: количество точек измерения
        :return: массив позиций
        """
        positions = np.linspace(*self.position_range, num_points)
        positions += np.random.normal(0, 0.5, size=num_points)  # небольшие колебания
        logging.debug("Показания линейного датчика сгенерированы")
        return positions

class ExperimentSimulator:
    """
    Класс для проведения симуляции эксперимента.
    """

    def __init__(self, user_id: int, group_name: str):
        self.user_id = user_id
        self.group_name = group_name
        self.arduino = VirtualArduino()
        self.sensor_data = []
        self.gamma_calculated = None
        self.error_percent = None
        self.resonance_positions = []
        self.frequencies_used = []
        self.temperature = None
        logging.info(f"Эксперимент инициализирован для пользователя {user_id}")

    def run_experiment(self) -> Dict:
        """
        Запускает симуляцию эксперимента.
        :return: словарь с результатами эксперимента
        """
        logging.info("Запуск симуляции эксперимента")
        self.arduino.start()

        # Генерируем данные для 3-х частот по умолчанию
        frequencies = [1500, 3000, 4500]
        self.frequencies_used = frequencies

        # Случайная температура в диапазоне 18-25°C с малыми колебаниями
        self.temperature = self.arduino.read_temperature()

        all_resonance_positions = []

        for freq in frequencies:
            self.arduino.set_frequency(freq)

            # Генерация синусоидального сигнала, имитирующего интерференцию
            num_points = 1000
            positions = self.arduino.read_position(num_points)
            wavelength = 343 / freq * 1000  # длина волны в мм (приблизительно)
            signal = np.sin(2 * np.pi * positions / wavelength)

            # Получаем показания АЦП микрофона
            adc_values = self.arduino.read_adc(signal)

            # Находим минимумы (резонансы)
            from scipy.signal import find_peaks

            peaks, _ = find_peaks(-adc_values, height=0)
            resonance_positions = positions[peaks]
            all_resonance_positions.append(resonance_positions.tolist())

            # Сохраняем данные датчиков
            self.sensor_data.append({
                'frequency': freq,
                'positions': positions.tolist(),
                'adc_values': adc_values.tolist()
            })

            logging.info(f"Собраны данные для частоты {freq} Гц")

        # Рассчитываем скорость звука и коэффициент γ
        gamma_values = self.calculate_gamma(all_resonance_positions, frequencies)

        # Среднее значение γ
        self.gamma_calculated = np.mean(gamma_values)
        self.error_percent = abs((self.gamma_calculated - 1.4) / 1.4) * 100
        self.resonance_positions = all_resonance_positions

        self.arduino.stop()
        logging.info("Симуляция эксперимента завершена")

        return {
            'sensor_data': self.sensor_data,
            'gamma_calculated': self.gamma_calculated,
            'error_percent': self.error_percent,
            'resonance_positions': self.resonance_positions
        }

    def calculate_gamma(self, resonance_positions: List[List[float]], frequencies: List[float]) -> List[float]:
        """
        Расчет коэффициента γ на основе полученных данных.
        :param resonance_positions: список списков позиций резонансов для каждой частоты
        :param frequencies: список частот
        :return: список рассчитанных значений γ
        """
        logging.info("Начало расчета коэффициента γ")
        R = 8.314  # Дж/(моль·К)
        M = 0.029  # кг/моль (приблизительная молярная масса воздуха)
        T = self.temperature + 273.15  # Перевод в Кельвины

        gamma_values = []

        for i, positions in enumerate(resonance_positions):
            freq = frequencies[i]
            # Разность между соседними минимумами - полуволна
            deltas = np.diff(positions)
            half_wavelength = np.mean(deltas)
            wavelength = 2 * half_wavelength / 1000  # перевод в метры
            speed_of_sound = wavelength * freq
            gamma = speed_of_sound ** 2 * M / (R * T)
            gamma_values.append(gamma)
            logging.debug(f"Частота {freq} Гц: γ = {gamma:.4f}")

        logging.info("Расчет коэффициента γ завершен")
        return gamma_values