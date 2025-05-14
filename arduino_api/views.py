import json
import logging
import serial
import time
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

# Глобальный объект для хранения подключения
arduino_connection = None

# Настройка логирования
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

@csrf_exempt
@require_http_methods(["POST"])
def connect_arduino(request):
    """API-эндпоинт для подключения к Arduino через указанный порт.
    
    Параметры запроса:
        port (str): Путь к порту, например /dev/tty.usbserial-120 или COM3
        baudrate (int, optional): Скорость подключения, по умолчанию 9600
    
    Returns:
        JsonResponse: Результат операции подключения
    """
    global arduino_connection
    
    try:
        # Получаем данные из запроса
        data = json.loads(request.body)
        port = data.get('port')
        baudrate = data.get('baudrate', 9600)
        
        if not port:
            return JsonResponse({'success': False, 'error': 'Не указан порт Arduino'}, status=400)
        
        logger.info(f"Попытка подключения к Arduino: порт={port}, скорость={baudrate}")
        
        # Если уже есть подключение, закрываем его
        if arduino_connection and arduino_connection.is_open:
            arduino_connection.close()
            logger.info("Закрыто существующее подключение")
        
        # Подключаемся к Arduino
        arduino_connection = serial.Serial(
            port=port,
            baudrate=baudrate,
            timeout=1
        )
        
        # Короткая пауза для установки соединения
        time.sleep(1)
        
        # Проверяем успешность подключения
        if arduino_connection.is_open:
            logger.info(f"Успешно подключено к Arduino: порт={port}, скорость={baudrate}")
            
            # Читаем немного данных для проверки
            try:
                arduino_connection.flushInput()
                test_data = arduino_connection.readline().decode('utf-8').strip()
                logger.info(f"Получены тестовые данные от Arduino: {test_data}")
            except Exception as e:
                logger.warning(f"Не удалось прочитать тестовые данные: {e}")
            
            return JsonResponse({
                'success': True, 
                'message': f'Успешно подключено к Arduino на порту {port}'
            })
        else:
            logger.error(f"Не удалось подключиться к Arduino: порт={port}")
            return JsonResponse({
                'success': False, 
                'error': 'Не удалось открыть соединение с портом'
            }, status=500)
            
    except serial.SerialException as e:
        logger.error(f"Ошибка подключения к Arduino: {str(e)}")
        return JsonResponse({
            'success': False, 
            'error': f'Ошибка подключения: {str(e)}'
        }, status=500)
    except Exception as e:
        logger.error(f"Неизвестная ошибка при подключении к Arduino: {str(e)}")
        return JsonResponse({
            'success': False, 
            'error': f'Неизвестная ошибка: {str(e)}'
        }, status=500)

@csrf_exempt
@require_http_methods(["POST"])
def disconnect_arduino(request):
    """API-эндпоинт для отключения от Arduino.
    
    Returns:
        JsonResponse: Результат операции отключения
    """
    global arduino_connection
    
    try:
        if arduino_connection and arduino_connection.is_open:
            arduino_connection.close()
            logger.info("Arduino успешно отключен")
            return JsonResponse({
                'success': True, 
                'message': 'Arduino успешно отключен'
            })
        else:
            logger.warning("Попытка отключения при отсутствии соединения")
            return JsonResponse({
                'success': False, 
                'error': 'Нет активного подключения к Arduino'
            })
    except Exception as e:
        logger.error(f"Ошибка при отключении Arduino: {str(e)}")
        return JsonResponse({
            'success': False, 
            'error': f'Ошибка отключения: {str(e)}'
        }, status=500)

@require_http_methods(["GET"])
def arduino_status(request):
    """API-эндпоинт для проверки статуса подключения к Arduino.
    
    Returns:
        JsonResponse: Информация о текущем подключении
    """
    global arduino_connection
    
    try:
        if arduino_connection and arduino_connection.is_open:
            return JsonResponse({
                'connected': True,
                'port': arduino_connection.port,
                'baudrate': arduino_connection.baudrate
            })
        else:
            return JsonResponse({'connected': False})
    except Exception as e:
        logger.error(f"Ошибка при получении статуса Arduino: {str(e)}")
        return JsonResponse({
            'connected': False,
            'error': str(e)
        }, status=500)

@csrf_exempt
@require_http_methods(["POST"])
def read_distance(request):
    """API-эндпоинт для чтения данных о расстоянии с Arduino.
    
    Returns:
        JsonResponse: Данные о расстоянии
    """
    global arduino_connection
    
    try:
        if not arduino_connection or not arduino_connection.is_open:
            return JsonResponse({
                'success': False,
                'error': 'Нет подключения к Arduino'
            }, status=400)
        
        # Читаем данные с Arduino
        arduino_connection.flushInput()
        start_time = time.time()
        distances = []
        timestamps = []
        
        # Читаем данные в течение 1 секунды
        while time.time() - start_time < 1.0:
            if arduino_connection.in_waiting > 0:
                try:
                    line = arduino_connection.readline().decode('utf-8').strip()
                    if line.startswith('distance:'):
                        distance_value = float(line[9:])
                        distances.append(distance_value)
                        timestamps.append(time.time() - start_time)
                except Exception as e:
                    logger.error(f"Ошибка при чтении данных: {str(e)}")
        
        if distances:
            return JsonResponse({
                'success': True,
                'distances': distances,
                'timestamps': timestamps,
                'count': len(distances)
            })
        else:
            return JsonResponse({
                'success': False,
                'error': 'Не получены данные о расстоянии'
            })
            
    except Exception as e:
        logger.error(f"Ошибка при чтении данных о расстоянии: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500) 