import serial
import time

# Настройка последовательного порта
ser = serial.Serial(
    port='/dev/tty.usbserial-120',      # Замените на ваш порт (например '/dev/ttyACM0' для Linux)
    baudrate=9600,
    timeout=1
)

try:
    print("Чтение данных с датчика HC-SR04... (Ctrl+C для остановки)")
    while True:
        if ser.in_waiting > 0:
            # Чтение строки из последовательного порта
            line = ser.readline().decode('utf-8').rstrip()
            
            try:
                distance = float(line)
                print(f"Расстояние: {distance:.2f} см") # частота 10 гц
            except ValueError:
                print(f"Получены некорректные данные: {line}")

except KeyboardInterrupt:
    print("\nПрограмма остановлена")
    ser.close()  # Закрытие последовательного порта