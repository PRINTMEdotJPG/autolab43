import numpy as np
from scipy.signal import hilbert
from app.consumers import AudioConsumer

def test_find_minima():
    """Тест для проверки корректности поиска интерференционных минимумов"""
    # Генерация тестового сигнала
    sr = 48000  # Частота дискретизации
    t = np.linspace(0, 10, sr)
    
    # Создаем сигнал с затухающей огибающей и модуляцией
    carrier = np.sin(2*np.pi*1000*t)  # Несущая 1 кГц
    envelope = np.exp(-0.2*t) * (1 + 0.3*np.sin(2*np.pi*0.8*t))  # Затухающая огибающая с модуляцией
    test_signal = carrier * envelope
    
    # Инициализируем и тестируем
    consumer = AudioConsumer()
    consumer.movement_speed = 0.01  # Устанавливаем скорость движения
    
    minima = consumer.find_minima(test_signal, sr)
    
    # Визуализация для отладки (опционально)
    import matplotlib.pyplot as plt
    plt.figure(figsize=(12, 6))
    plt.plot(t, test_signal, label='Тестовый сигнал')
    if minima:
        plt.scatter([m['time'] for m in minima], 
                   [test_signal[int(m['time']*sr)] for m in minima],
                   color='red', label='Найденные минимумы')
    plt.title('Проверка поиска минимумов')
    plt.xlabel('Время (с)')
    plt.ylabel('Амплитуда')
    plt.legend()
    plt.grid()
    plt.show()
    
    # Проверяем что найдены минимумы
    assert len(minima) > 0, "Не найдено ни одного минимума"
    assert len(minima) == 8, f"Ожидалось 8 минимумов, найдено {len(minima)}"
    assert all(m['prominence'] > 0.1 for m in minima), "Найдены слабовыраженные минимумы"