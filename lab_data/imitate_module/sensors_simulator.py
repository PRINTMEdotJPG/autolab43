import numpy as np
import scipy.signal as signal
import matplotlib.pyplot as plt
import random
import math
import json
from datetime import datetime

class ExperimentSimulator:
    """Класс для имитации эксперимента по определению отношения теплоемкостей воздуха γ методом интерференции."""
    
    def __init__(self):
        """Инициализация параметров эксперимента."""
        self.temperature = 20.0 + random.uniform(-2, 3)  # Начальная температура с флуктуациями
        self.temperature_drift = 3.0                     # Максимальный дрейф температуры (не используется)
        self.mic_noise = 15                              # Уровень шума микрофона
        self.position = 0                                # Текущая позиция трубки (мм)
        self.frequency_range = (1500, 5500)              # Диапазон частот (Гц)
        self.initial_speed = 1.5                         # Базовая скорость движения трубки (мм/с)

    def generate_temperature(self):
        """Генерирует температуру с синусоидальным дрейфом и шумом.
        
        Returns:
            float: Обновленная температура (°C)
        """
        drift = 0.1 * np.sin(2 * np.pi * np.random.uniform(0, 1))  # Синусоидальный дрейф
        noise = random.uniform(-0.5, 0.5)                           # Случайный шум
        self.temperature += drift + noise
        return self.temperature

    def generate_voltage(self):
        """Генерирует напряжение с небольшим случайным шумом.
        
        Returns:
            float: Значение напряжения (В)
        """
        return 5.0 + random.uniform(-0.2, 0.2)

    def generate_microphone_signal(self, frequency, position, temperature):
        """Моделирует сигнал микрофона с учетом интерференции и шума.
        
        Args:
            frequency (float): Частота звука (Гц)
            position (float): Позиция трубки (мм)
            temperature (float): Текущая температура (°C)
            
        Returns:
            float: Значение сигнала микрофона (усл. ед.)
        """
        delta_L = 2 * position / 1000                     # Разность хода волн (м)
        temperature_kelvin = temperature + 273.15         # Температура в Кельвинах
        gamma = 1.4                                       # Коэффициент адиабаты для воздуха
        R = 287.05                                        # Удельная газовая постоянная (Дж/(кг·К))
        
        # Расчет скорости звука и длины волны
        v_sound = (gamma * R * temperature_kelvin) ** 0.5
        wavelength = v_sound / frequency
        signal_value = 600 * (1 + np.cos(2 * np.pi * delta_L / wavelength)) 
        signal_value += random.gauss(0, self.mic_noise)   # Добавление шума
        return np.clip(signal_value, 50, 950)             # Ограничение диапазона

    def generate_position(self):
        """Обновляет позицию трубки с учетом скорости и случайного шума.
        
        Returns:
            float: Новая позиция трубки (мм)
        """
        if self.position >= 1000:
            self.position = 0  # Сброс позиции
        speed = self.initial_speed + random.uniform(-0.1, 0.1)
        self.position = min(self.position + speed, 1000)
        return self.position

    def find_interference_minima(self, signal_data):
        """Находит минимумы интерференционной картины.
        
        Args:
            signal_data (list): Исходный сигнал
            
        Returns:
            tuple: (Сглаженный сигнал, индексы минимумов) или (None, None)
        """
        signal_array = np.array(signal_data)
        window_length = 51
        smoothed_signal = signal.savgol_filter(signal_array, window_length, 3)  # Сглаживание
        peaks, _ = signal.find_peaks(-smoothed_signal, prominence=10, distance=20)  # Поиск минимумов
        return (smoothed_signal, peaks) if len(peaks) >= 2 else (None, None)

    def calculate_gamma(self, frequency, position, temperature):
        """Вычисляет коэффициент адиабаты γ.
        
        Args:
            frequency (float): Частота звука (Гц)
            position (float): Позиция трубки (мм)
            temperature (float): Температура (°C)
            
        Returns:
            tuple: (γ, скорость звука (м/с), длина волны (м))
        """
        delta_L = 2 * position / 1000
        temperature_kelvin = temperature + 273.15
        gamma = 1.4
        R = 287.05
        
        v_sound = (gamma * R * temperature_kelvin) ** 0.5
        wavelength = v_sound / frequency
        gamma_value = (v_sound ** 2 * 0.029) / (8.314 * temperature_kelvin) * random.uniform(0.998, 1.002)
        return gamma_value, v_sound, wavelength

    def generate_random_frequencies(self, n=3):
        """Генерирует случайные частоты в заданном диапазоне.
        
        Args:
            n (int): Количество частот
            
        Returns:
            list: Список частот (Гц)
        """
        return [round(random.uniform(*self.frequency_range), 2) for _ in range(n)]

    def run_experiment(self, frequencies=None):
        """Проводит эксперимент и возвращает результаты в формате JSON.
        
        Args:
            frequencies (list): Список частот (Гц)
            
        Returns:
            str: JSON-строка с результатами
        """
        if frequencies is None:
            frequencies = self.generate_random_frequencies()

        results = []
        timestamp = datetime.now().isoformat()

        for freq in frequencies:
            self.generate_temperature()
            signal_data = []
            self.position = 0  # Сброс позиции для каждого эксперимента

            for _ in range(2000):
                current_pos = self.generate_position()
                mic_signal = self.generate_microphone_signal(freq, current_pos, self.temperature)
                signal_data.append(mic_signal)

            smoothed_signal, peaks = self.find_interference_minima(signal_data)

            if smoothed_signal is None or peaks is None:
                results.append({
                    'frequency': freq,
                    'status': 'fail',
                    'reason': 'Not enough minima found.'
                })
                continue

            # Расчёт гамма-значения для полученной частоты и температуры
            gamma_value, v_sound, wavelength = self.calculate_gamma(freq, self.position, self.temperature)

            results.append({
                'frequency': freq,
                'status': 'success',
                'gamma': gamma_value,
                'speed_sound': v_sound,
                'wavelength': wavelength,
                'timestamp': timestamp
            })
        

        gamma_values = [r['gamma'] for r in results if r.get('status') == 'success']
        gamma_calculated = np.mean(gamma_values) if gamma_values else np.nan
        error_percent = abs(gamma_calculated - 1.4) / 1.4 * 100 if not np.isnan(gamma_calculated) else np.nan
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

        print(f"🔬 Результаты эксперимента #{timestamp}")
        print(f"🌡 Температура: {self.temperature:.1f}°C")
        print(f"📊 Гамма: {gamma_calculated:.3f} (эталон 1.4)")
        print(f"📉 Отклонение: {error_percent:.2f}%\n")
        print("Детализация:")

        for result in results:
            if result.get('status') == 'success':
                print(f"✅ {result['frequency']} Гц: γ={result['gamma']:.3f} λ={result['wavelength']:.3f} м v={result['speed_sound']:.1f} м/с")
            else:
                print(f"❌ {result['frequency']} Гц: {result.get('reason', 'Неудача')}")

        return json.dumps(output, indent=2)

# Пример использования
simulator = ExperimentSimulator()
results = simulator.run_experiment(frequencies=[1700, 2300, 4000])
print(results)