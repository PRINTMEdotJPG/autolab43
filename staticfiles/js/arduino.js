(function(global) {
  /**
   * Модуль работы с оборудованием
   */
  class EquipmentManager {
      constructor(core) {
        console.log('[EQM CONSTRUCTOR] EquipmentManager создается. Core:', core);
        this.core = core;
        this.port = null;
        this.reader = null;
        this.keepReading = false;
        this.isRecording = false; // Флаг, указывающий, идет ли запись данных для эксперимента
        this.distanceData = []; // Массив для хранения данных о расстоянии во время записи
        this.distanceTimestamps = []; // Массив для хранения временных меток для данных о расстоянии
        this.firstArduinoTimestamp = null; // Временная метка первого сообщения от Arduino в текущем сегменте записи (в секундах), используется для расчета относительного времени.
        this.textDecoder = new TextDecoder();
        this.lastLogTime = 0; // Время последнего логирования
        this.logInterval = 500; // Интервал для ограничения частоты вывода логов в консоль (в миллисекундах).
        console.log('[EQM CONSTRUCTOR] EquipmentManager создан. Начальное состояние:', this);
      }
    
      async connect() {
        console.log('[EQM connect] Попытка автоматического подключения (запрос порта у пользователя)...');
        try {
          if (!navigator.serial) {
            console.error('[EQM connect] Web Serial API не поддерживается в этом браузере.');
            this.core.useSimulation();
            return;
          }
          console.log('[EQM connect] Запрашиваем порт через navigator.serial.requestPort()...');
          this.port = await navigator.serial.requestPort();
          console.log('[EQM connect] Порт получен:', this.port ? this.port.getInfo() : 'null');
          
          if (!this.port) {
            console.warn('[EQM connect] Пользователь не выбрал порт.');
            this.core.useSimulation(); // или просто ничего не делаем, давая пользователю попробовать еще раз
            return;
          }

          console.log('[EQM connect] Пытаемся открыть порт...');
          await this.port.open({ baudRate: 9600 });
          console.log('[EQM connect] Порт успешно открыт.');
          
          this.core.equipmentConnected = true;
          console.log('[EQM connect] this.core.equipmentConnected установлен в true');
          this.core.updateEquipmentStatus();
          console.log('[EQM connect] this.core.updateEquipmentStatus() вызван.');
          
          this.startReading();
        } catch (error) {
          console.error('[EQM connect] Ошибка автоматического подключения:', error);
          this.port = null; // Убедимся, что порт сброшен при ошибке
          this.core.equipmentConnected = false;
          this.core.updateEquipmentStatus(); // Обновляем статус на "отключено"
          this.core.useSimulation(); // Переключаемся на симуляцию при ошибке
        }
      }
      
      // Функция для подключения к порту по указанному пути
      async connectToPort(portPath, baudRate = 9600) {
        console.log(`[EQM connectToPort] Попытка подключения к порту '${portPath}' со скоростью ${baudRate} бод.`);
        try {
          if (!navigator.serial) {
            console.error('[EQM connectToPort] Web Serial API не поддерживается в этом браузере.');
            this.core.useSimulation();
            return false;
          }
          
          console.log('[EQM connectToPort] Получаем список доступных портов (navigator.serial.getPorts())...');
          const ports = await navigator.serial.getPorts();
          console.log('[EQM connectToPort] Доступные порты:', ports.map(p => p.getInfo()));
          
          let targetPort = null;
          if (ports && ports.length > 0) {
            for (const p of ports) {
              const info = p.getInfo();
              console.log('[EQM connectToPort] Проверка порта:', info);
              // На разных платформах путь порта может отображаться по-разному
              // Ищем по usbVendorId и usbProductId, если они есть в portPath (например, "usbVendorId=1234,usbProductId=5678")
              // Или по более простому совпадению имени/пути
              let match = false;
              if (portPath.includes('usbVendorId') && info.usbVendorId) {
                 // Предполагаем формат "usbVendorId=XXXX" или "vid=XXXX"
                 const vidMatch = portPath.match(/usbVendorId=(\d+)/i) || portPath.match(/vid=(\d+)/i);
                 if (vidMatch && parseInt(vidMatch[1]) === info.usbVendorId) {
                    const pidMatch = portPath.match(/usbProductId=(\d+)/i) || portPath.match(/pid=(\d+)/i);
                    if (pidMatch && info.usbProductId && parseInt(pidMatch[1]) === info.usbProductId) {
                        match = true;
                    } else if (!pidMatch) { // Если PID не указан в portPath, но VID совпал
                        match = true; 
                    }
                 }
              }
              
              if (!match && ( (info.path && info.path === portPath) || (info.name && info.name === portPath) ) ) {
                match = true;
              }

              if (match) {
                console.log(`[EQM connectToPort] Найден соответствующий порт в списке:`, info);
                targetPort = p;
                break;
              }
            }
          }
          
          if (!targetPort) {
            console.warn(`[EQM connectToPort] Порт '${portPath}' не найден в списке автоматически полученных портов. Попробуем запросить у пользователя (requestPort)...`);
            // Это может быть нежелательно, если пользователь уже указал порт.
            // Возможно, стоит сначала проверить, есть ли такой порт вообще, прежде чем запрашивать.
            // targetPort = await navigator.serial.requestPort(); // Закомментировано, чтобы избежать лишнего запроса, если порт указан неверно
            // if (targetPort) {
            //    console.log('[EQM connectToPort] Пользователь выбрал порт:', targetPort.getInfo());
            // } else {
            //    console.warn('[EQM connectToPort] Пользователь не выбрал порт после запроса.');
            // }
             console.error(`[EQM connectToPort] Порт '${portPath}' не найден. Подключение не удалось.`);
             throw new Error(`Порт ${portPath} не найден.`);
          }
          
          if (!targetPort) { // Двойная проверка на случай, если requestPort() выше был бы раскомментирован и не вернул порт
            console.error(`[EQM connectToPort] Порт ${portPath} так и не был определен.`);
            throw new Error(`Порт ${portPath} не найден или не выбран.`);
          }
          
          this.port = targetPort;
          console.log(`[EQM connectToPort] Пытаемся открыть выбранный порт:`, this.port.getInfo());
          await this.port.open({ baudRate });
          console.log(`[EQM connectToPort] Порт '${portPath}' успешно открыт.`);
          
          this.core.equipmentConnected = true;
          console.log('[EQM connectToPort] this.core.equipmentConnected установлен в true');
          this.core.updateEquipmentStatus();
          console.log('[EQM connectToPort] this.core.updateEquipmentStatus() вызван.');
          
          this.startReading();
          return true;
        } catch (error) {
          console.error(`[EQM connectToPort] Ошибка при подключении к порту '${portPath}':`, error);
          this.port = null; // Сброс порта при ошибке
          this.core.equipmentConnected = false;
          this.core.updateEquipmentStatus();
          this.core.useSimulation();
          return false;
        }
      }
    
      async startReading() {
        console.log('[EQM startReading] Начало чтения данных с порта.');
        if (!this.port || !this.port.readable) {
            console.error('[EQM startReading] Порт не существует или не доступен для чтения (this.port.readable is false). Порт:', this.port);
            return;
        }
        console.log('[EQM startReading] Порт доступен для чтения. Получаем reader...');
        this.reader = this.port.readable.getReader();
        console.log('[EQM startReading] Reader получен:', this.reader);
        const decoder = new TextDecoder();
        let buffer = '';
        
        try {
            console.log('[EQM startReading] Запуск цикла чтения...');
            while (true) {
                const { value, done } = await this.reader.read();
                if (done) {
                    console.log('[EQM startReading] Чтение завершено (done = true).');
                    this.reader.releaseLock();
                    break;
                }
                
                const chunk = decoder.decode(value, { stream: true });
                buffer += chunk;
                
                let newlineIndex;
                while ((newlineIndex = buffer.indexOf('\n')) !== -1) { // Убедимся, что ищем именно \n
                    const line = buffer.substring(0, newlineIndex).trim();
                    buffer = buffer.substring(newlineIndex + 1);
                    this.processDistanceData(line);
                }
            }
        } catch (error) {
            console.error('[EQM startReading] Ошибка в цикле чтения:', error);
            if (this.reader) { // Пытаемся освободить блокировку, если она есть
                try {
                    await this.reader.cancel("Ошибка чтения");
                    this.reader.releaseLock();
                 } catch (cancelError) {
                    console.error('[EQM startReading] Ошибка при отмене reader:', cancelError);
                 }
            }
            this.port = null; // Считаем порт потерянным
            this.core.equipmentConnected = false;
            this.core.updateEquipmentStatus();
        } finally {
            console.log('[EQM startReading] Цикл чтения завершен (блок finally).');
        }
      }
      
      processDistanceData(line) {
        try {
          // Пытаемся распарсить строку как JSON
          const jsonData = JSON.parse(line);
          
          if (jsonData && jsonData.type === 'distance' && jsonData.value !== undefined) {
            const distanceValue = parseFloat(jsonData.value);
            
            if (!isNaN(distanceValue)) {
              // Фильтруем значения -1 (ошибка датчика)
              if (distanceValue < 0) { 
                console.log('[EQM processDistanceData] Получено значение расстояния < 0 (вероятно, ошибка датчика), игнорируется:', distanceValue);
                // Можно передать специальное значение или ничего не делать
                this.core.processEquipmentData({
                  distance: null, // или специальный флаг ошибки
                  time: (jsonData.timestamp || Date.now()) / 1000,
                  error: true
                });
                return; // Не записываем ошибочные данные
              }

              if (this.isRecording) {
                const arduinoTimeSec = jsonData.timestamp / 1000; // Предполагаем, что jsonData.timestamp это миллисекунды от Arduino

                if (this.firstArduinoTimestamp === null) {
                    this.firstArduinoTimestamp = arduinoTimeSec;
                    console.log(`[EQM RECORDING] Установлена первая метка времени Arduino для этого сегмента: ${this.firstArduinoTimestamp}с`);
                }
                // Рассчитываем время относительно первого сообщения Arduino в текущей сессии записи.
                // Это помогает синхронизировать временные метки, если между запусками Arduino и клиента есть расхождения.
                const relativeTimeSec = arduinoTimeSec - this.firstArduinoTimestamp;

                this.distanceData.push(distanceValue);
                this.distanceTimestamps.push(relativeTimeSec); // Используем относительное время
                
                // Ограничение частоты логирования
                const now = Date.now();
                if (now - this.lastLogTime > this.logInterval) {
                    console.log('[EQM RECORDING] Добавлено (лог раз в 500мс):', { distance: distanceValue, time: relativeTimeSec, rawArduinoTime: arduinoTimeSec }, 'Всего:', this.distanceData.length);
                    this.lastLogTime = now;
                }
                
                this.core.processEquipmentData({
                  distance: distanceValue,
                  time: relativeTimeSec // Отправляем относительное время и в processEquipmentData для UI
                });
              } else {
                const arduinoTimeSecForLog = jsonData.timestamp / 1000; 
                
                // Ограничение частоты логирования для сообщений, когда запись не активна.
                const nowNonRecording = Date.now();
                if (nowNonRecording - this.lastLogTime > this.logInterval) {
                    console.log('[EQM NOT RECORDING] Получено (лог раз в 500мс, не записывается):', { distance: distanceValue, time: arduinoTimeSecForLog });
                    this.lastLogTime = nowNonRecording;
                }
                
                this.core.processEquipmentData({
                  distance: distanceValue,
                  time: arduinoTimeSecForLog
                });
              }
            } else {
              console.warn('[EQM processDistanceData] Не удалось распарсить значение \'value\' из JSON как число:', jsonData.value, '(Оригинальный JSON:', jsonData, ')');
            }
          } else if (jsonData && jsonData.type !== 'distance') {
            console.log('[EQM processDistanceData] Получен JSON другого типа:', jsonData.type, jsonData);
          } else if (!jsonData) {
            // Это условие не должно срабатывать, если JSON.parse выбросил ошибку
            console.warn('[EQM processDistanceData] JSON.parse вернул null/undefined, но не выбросил ошибку. Строка:', JSON.stringify(line));
          }
        } catch (error) {
          // Если это не JSON, проверяем, не старый ли это формат "distance: X.XX"
          // (хотя сейчас Arduino должен слать только JSON)
          if (line.startsWith('distance:')) {
            console.warn('[EQM processDistanceData] Получена строка в старом формате "distance:", пытаемся обработать:', JSON.stringify(line));
            const distanceString = line.substring(9);
            const distanceValue = parseFloat(distanceString);
            if (!isNaN(distanceValue) && distanceValue >= 0) {
                this.core.processEquipmentData({
                    distance: distanceValue,
                    time: Date.now() / 1000
                });
            } else {
                 console.warn('[EQM processDistanceData] Не удалось распарсить значение из старого формата:', distanceString);
            }
          } else if (line && line.trim() !== '') { // Логируем непустые строки, которые не являются JSON
            console.log('[EQM processDistanceData] Ошибка парсинга JSON или получен не JSON. Строка не пустая, логируем:', JSON.stringify(line), 'Ошибка:', error.message);
          } else if (!line || line.trim() === '') {
            // console.log('[EQM processDistanceData] Получена пустая или состоящая из пробелов строка (не JSON), игнорируется.');
          }
        }
      }
      
      startRecording() {
        if (!this.port || !this.port.readable) {
            console.warn('[EQM startRecording Measurement] Порт не подключен или не доступен для чтения.');
            this.core.updateEquipmentStatus(false, 'Порт не подключен.');
            return;
        }
        this.isRecording = true;
        // this.recordingStartTime = Date.now(); // Сохраняем время начала записи
        this.distanceData = [];
        this.distanceTimestamps = [];
        this.firstArduinoTimestamp = null; // Сброс для нового сегмента записи
        console.log('[EQM startRecording Measurement] Запись данных о расстоянии АКТИВИРОВАНА. Массивы очищены. firstArduinoTimestamp сброшен.');
      }
      
      stopRecording() {
        console.log('[EQM stopRecording Measurement] Остановка записи измерений с Arduino.');
        this.isRecording = false;
        const result = { // Сначала соберем результат
          distances: this.distanceData,
          timestamps: this.distanceTimestamps
        };
        console.log(`[EQM stopRecording Measurement] Запись ОСТАНОВЛЕНА. Результат:`, JSON.parse(JSON.stringify(result)));
        return result;
      }
    
      async disconnect() {
        console.log('[EQM disconnect] Попытка отключения от порта...');
        if (this.reader) {
          try {
            console.log('[EQM disconnect] Отмена reader.cancel()...');
            await this.reader.cancel();
            // this.reader.releaseLock(); // releaseLock() должен вызываться автоматически при cancel() или done=true
            console.log('[EQM disconnect] Reader отменен.');
          } catch (error) {
            console.error('[EQM disconnect] Ошибка при отмене reader:', error);
          } finally {
            this.reader = null;
          }
        }
        if (this.port) {
          try {
            console.log('[EQM disconnect] Закрытие порта port.close()...');
            await this.port.close();
            console.log('[EQM disconnect] Порт закрыт.');
          } catch (error) {
            console.error('[EQM disconnect] Ошибка при закрытии порта:', error);
          } finally {
            this.port = null;
          }
        }
        this.core.equipmentConnected = false;
        console.log('[EQM disconnect] this.core.equipmentConnected установлен в false');
        this.core.updateEquipmentStatus();
        console.log('[EQM disconnect] this.core.updateEquipmentStatus() вызван. Отключение завершено.');
      }
    }

  // Экспортируем класс в глобальную область видимости
  console.log('[ARDUINO SCRIPT] Перед экспортом EquipmentManager в global.');
  global.EquipmentManager = EquipmentManager;
  console.log('[ARDUINO SCRIPT] Класс EquipmentManager экспортирован в global:', global.EquipmentManager);
  
  // Отправляем событие о загрузке модуля
  console.log('[ARDUINO SCRIPT] Модуль arduino.js полностью выполнен, класс EquipmentManager доступен глобально.');
  
  // Создаем и отправляем специальное событие для уведомления других скриптов
  console.log('[ARDUINO SCRIPT] Перед dispatchEvent("arduino_module_loaded")');
  const event = new CustomEvent('arduino_module_loaded', { 
    detail: { 
      success: true, 
      timestamp: Date.now(),
      message: 'Arduino module and EquipmentManager class are now available.'
    } 
  });
  document.dispatchEvent(event);
  console.log('[ARDUINO SCRIPT] Событие "arduino_module_loaded" ОТПРАВЛЕНО.', event);
  
})(window); // Явно передаем window как глобальный объект