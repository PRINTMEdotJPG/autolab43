import random
import math
import time
from datetime import datetime
from typing import Dict, List, Optional
import numpy as np
from scipy.signal import find_peaks

class VirtualArduino:
    """Реалистичная имитация лабораторной установки с физически точными параметрами"""
    
    def __init__(self):
        # Инициализация базовых параметров
        self.base_temp = 20.0 + random.uniform(-1.5, 1.5)
        self.sensors = {
            'temperature': self.base_temp,
            'voltage': 5.0 + random.uniform(-0.05, 0.05),
            'microphone': 512,
            'tube_position': 0.0,
            'frequency': 1500
        }
        self.baudrate = 9600
        self.port = "COM3"
        self.is_connected = False
        self.experiment_start_time = 0
        self.current_frequency = 1500
        self.tube_velocity = 0.8  # мм/сек
        self.last_update = time.time()
        
    def connect(self) -> bool:
        """Имитация подключения с реалистичной задержкой"""
        time.sleep(0.5)  # Задержка подключения
        self.is_connected = True
        return True
        
    def update_sensors(self):
        """Физически точное обновление показаний датчиков"""
        t = time.time() - self.experiment_start_time
        
        # Температура с дрейфом и шумом
        temp_drift = 0.1 * math.sin(t / 15)
        temp_noise = random.gauss(0, 0.05)
        self.sensors['temperature'] = round(
            self.base_temp + temp_drift + temp_noise, 2
        )
        
        # Генерация интерференционной картины
        wavelength = 343 / self.current_frequency
        path_difference = 2 * self.sensors['tube_position'] / 1000
        
        # Физика интерференции
        interference = math.cos(2 * math.pi * path_difference / wavelength)
        base_signal = 600 * (1 + interference) 
        noise = random.gauss(0, 15)
        
        self.sensors['microphone'] = int(max(50, min(950, base_signal + noise))
        
        # Реалистичное движение трубы с точными минимумами
        if (abs(interference + 1) < 0.1):  # Точный минимум интерференции
            self.sensors['tube_position'] = round(self.sensors['tube_position'] / (wavelength * 500)) * wavelength * 500
            self.tube_velocity = 0.5 + random.uniform(-0.1, 0.1)
        else:
            self.sensors['tube_position'] += self.tube_velocity
            self.sensors['tube_position'] = round(
                max(0, min(1000, self.sensors['tube_position']), 2
            )
        
    def read_data(self) -> Dict:
        if not self.is_connected:
            raise ConnectionError("Ошибка связи с Arduino")
            
        self.update_sensors()
        time.sleep(0.02 + random.uniform(0, 0.01))  # Реалистичная задержка
        
        return {
            'time_ms': int((time.time() - self.last_update) * 1000),
            'temperature': self.sensors['temperature'],
            'voltage': round(self.sensors['voltage'], 3),
            'microphone': self.sensors['microphone'],
            'position': self.sensors['tube_position'],
            'frequency': self.sensors['frequency'],
            'status': 'OK'
        }
        
    def send_command(self, command: str) -> bool:
        """Обработка команд с имитацией аппаратных ограничений"""
        if command == "START":
            self.experiment_start_time = time.time()
            self.tube_velocity = 0.8  # Сброс скорости
            return True
        elif command == "STOP":
            self.tube_velocity = 0.0
            return True
        elif command.startswith("SET_FREQ"):
            try:
                freq = int(command.split()[1])
                if 1450 <= freq <= 6050:
                    self.current_frequency = freq
                    self.sensors['frequency'] = freq
                    time.sleep(0.1)  # Задержка настройки частоты
                    return True
            except:
                pass
        return False


class ExperimentSimulator:
    """Усовершенствованный симулятор с физически точными расчетами"""
    
    def __init__(self, user_id: int, group_name: str):
        self.user_id = user_id
        self.group_name = group_name
        self.arduino = VirtualArduino()
        self.arduino.connect()
        
        # Физические константы
        self.R = 8.314462618  # Дж/(моль·К)
        self.M_air = 0.0289647  # кг/моль
        self.gamma_ref = 1.400  # Для сухого воздуха
        
    def run_experiment(self, frequencies: List[int] = None) -> Dict:
        """Проведение эксперимента с автоматическим подбором параметров"""
        frequencies = frequencies or [1500, 2250, 3000]
        results = []
        full_sensor_data = []
        
        for freq in sorted(frequencies):
            if not 1450 <= freq <= 6050:
                continue
                
            self.arduino.send_command(f"SET_FREQ {freq}")
            data = self._collect_data(freq)
            analysis = self._analyze_run(data, freq)
            
            full_sensor_data.extend(data)
            results.append(analysis)
        
        # Статистическая обработка результатов
        valid_results = [r for r in results if r['status'] == 'success']
        avg_gamma = np.mean([r['gamma'] for r in valid_results]) if valid_results else 0.0
        avg_error = abs(avg_gamma - self.gamma_ref)/self.gamma_ref*100 if valid_results else 100.0
        
        return {
            'user_id': self.user_id,
            'group_name': self.group_name,
            'temperature': self.arduino.sensors['temperature'],
            'frequencies': frequencies,
            'sensor_data': full_sensor_data,
            'gamma_calculated': round(avg_gamma, 4),
            'gamma_reference': self.gamma_ref,
            'error_percent': round(avg_error, 2),
            'status': 'success' if avg_error < 2.5 else 'fail',
            'timestamp': datetime.now().isoformat(),
            'details': results
        }
    
    def _collect_data(self, freq: int) -> List[Dict]:
        """Сбор данных с реалистичными временными характеристиками"""
        self.arduino.send_command("START")
        data = []
        
        for _ in range(120):  # 120 измерений по 0.1 сек = 12 сек
            try:
                d = self.arduino.read_data()
                data_point = {
                    'time_ms': d['time_ms'],
                    'temperature': d['temperature'],
                    'microphone': d['microphone'],
                    'position': d['position'],
                    'frequency': d['frequency'],
                    'voltage': d['voltage']
                }
                data.append(data_point)
                time.sleep(0.1 + random.uniform(-0.02, 0.02))
            except Exception as e:
                print(f"Ошибка сбора данных: {str(e)}")
                continue
                
        self.arduino.send_command("STOP")
        return data
    
    def _analyze_run(self, data: List[Dict], freq: int) -> Dict:
        """Точный анализ интерференционной картины"""
        positions = np.array([d['position'] for d in data])
        signals = np.array([d['microphone'] for d in data])
        
        # Поиск минимумов с использованием фильтрации
        smoothed = np.convolve(signals, np.ones(5)/5, mode='valid')
        minima = find_peaks(-smoothed, prominence=40, distance=15)[0] + 2
        
        if len(minima) < 3:
            return {'frequency': freq, 'status': 'fail', 'reason': 'Недостаточно минимумов'}
        
        # Линейная регрессия для определения λ
        x = np.arange(len(minima))
        y = positions[minima]
        coeffs = np.polyfit(x, y, 1)
        delta_L = coeffs[0]  # Среднее расстояние между минимумами
        
        # Физические расчеты
        wavelength = 2 * delta_L / 1000  # Переводим мм в метры
        v_sound = freq * wavelength
        T_kelvin = data[0]['temperature'] + 273.15
        
        gamma = (v_sound**2 * self.M_air) / (self.R * T_kelvin)
        error = abs(gamma - self.gamma_ref) / self.gamma_ref * 100
        
        return {
            'frequency': freq,
            'wavelength': round(wavelength, 4),
            'speed_sound': round(v_sound, 2),
            'gamma': round(gamma, 4),
            'error_percent': round(error, 2),
            'status': 'success' if error < 3.0 else 'fail',
            'minima_count': len(minima),
            'delta_L': round(delta_L, 2)
        }


if __name__ == "__main__":
    # Пример использования с улучшенным выводом
    print("🚀 Запуск реалистичной симуляции эксперимента\n")
    
    simulator = ExperimentSimulator(user_id=1, group_name="ФИЗ-101")
    results = simulator.run_experiment(frequencies=[1500, 2500, 3500])
    
    print(f"🔬 Результаты эксперимента #{results['timestamp']}")
    print(f"🌡 Температура: {results['temperature']}°C")
    print(f"📶 Частоты: {results['frequencies']} Гц")
    print(f"✅ Статус: {results['status'].upper()}")
    print(f"📊 Гамма: {results['gamma_calculated']} (эталон {results['gamma_reference']})")
    print(f"📉 Отклонение: {results['error_percent']}%")
    
    print("\nДетализация по частотам:")
    for res in results['details']:
        status = '✅ УСПЕХ' if res['status'] == 'success' else '❌ ОШИБКА'
        print(f"\n📡 {res['frequency']} Гц: {status}")
        if res['status'] == 'success':
            print(f"   λ = {res['wavelength']} м")
            print(f"   v = {res['speed_sound']} м/с")
            print(f"   γ = {res['gamma']} (±{res['error_percent']}%)")