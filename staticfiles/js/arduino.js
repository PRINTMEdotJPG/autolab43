/**
 * Модуль для работы с Arduino через Web Serial API
 * @param {AudioRecorderApp} app - Основное приложение
 */
function setupArduino(app) {
    const arduino = {
        port: null,
        reader: null,
        isConnected: false,
        currentDistance: null,
        distanceUpdates: [],
        buffer: '',
        readerLock: false, // Флаг для предотвращения параллельного чтения

        /**
         * Инициализация подключения к Arduino
         */
        async init() {
            try {
                // Проверка поддержки Web Serial API
                if (!('serial' in navigator)) {
                    throw new Error('Web Serial API не поддерживается в вашем браузере');
                }

                // Запрос доступа к устройству
                this.port = await navigator.serial.requestPort();
                await this.port.open({ baudRate: 9600 });

                // Сбрасываем состояние
                this.isConnected = true;
                this.buffer = '';
                this.readerLock = false;
                
                // Настройка чтения данных
                this.reader = this.port.readable.getReader();
                
                // Обновление UI
                app.ui.updateArduinoStatus(true);
                app.logger.info('[ARDUINO] Успешное подключение');
                app.showNotification('Arduino подключена', 'success');

                // Запуск чтения данных в фоне
                this._readData().catch(error => {
                    this._handleReadError(app, error);
                });

            } catch (error) {
                this._handleConnectionError(app, error);
            }
        },

        /**
         * Чтение данных с Arduino
         */
        async _readData() {
            const decoder = new TextDecoder();
            
            while (this.port.readable && this.isConnected && !this.readerLock) {
                try {
                    this.readerLock = true;
                    const { value, done } = await this.reader.read();
                    this.readerLock = false;
                    
                    if (done) {
                        this.logger.info('[ARDUINO] Поток чтения завершен');
                        break;
                    }

                    const text = decoder.decode(value);
                    this._processData(text, app);

                } catch (error) {
                    this.readerLock = false;
                    this._handleReadError(app, error);
                    break;
                }
            }
        },

        /**
         * Обработка полученных данных
         */
        _processData(data, app) {
            try {
                // Добавляем данные в буфер
                this.buffer += data;
                
                // Защита от переполнения буфера
                if (this.buffer.length > 1024) {
                    app.logger.warn('[ARDUINO] Буфер очищен из-за переполнения');
                    this.buffer = '';
                    return;
                }
                
                // Обрабатываем все полные сообщения в буфере
                let startIdx = 0;
                let braceLevel = 0;
                let inString = false;
                
                for (let i = 0; i < this.buffer.length; i++) {
                    const char = this.buffer[i];
                    
                    // Отслеживаем кавычки (игнорируем экранированные)
                    if (char === '"' && (i === 0 || this.buffer[i-1] !== '\\')) {
                        inString = !inString;
                    }
                    
                    if (!inString) {
                        if (char === '{') braceLevel++;
                        if (char === '}') braceLevel--;
                        
                        // Нашли полный JSON объект
                        if (braceLevel === 0 && char === '}' && startIdx <= i) {
                            const message = this.buffer.substring(startIdx, i+1);
                            this._handleJsonMessage(message, app);
                            startIdx = i+1;
                        }
                    }
                }
                
                // Удаляем обработанные данные из буфера
                if (startIdx > 0) {
                    this.buffer = this.buffer.substring(startIdx);
                }
                
            } catch (error) {
                app.logger.error('[ARDUINO] Ошибка обработки данных:', error);
            }
        },
        
        /**
         * Обработка одного JSON сообщения
         */
        _handleJsonMessage(jsonStr, app) {
            try {
                const parsed = JSON.parse(jsonStr);
                
                if (parsed.type === 'distance' && typeof parsed.value === 'number') {
                    this.currentDistance = parsed.value;
                    app.ui.updateDistance(this.currentDistance);
                    
                    if (app.recording.isRecording) {
                        this.distanceUpdates.push({
                            timestamp: parsed.timestamp || Date.now(),
                            distance: this.currentDistance
                        });
                    }
                    
                    app.logger.debug(`[ARDUINO] Расстояние: ${this.currentDistance.toFixed(1)} см`);
                } else {
                    app.logger.warn('[ARDUINO] Неизвестный тип сообщения:', jsonStr);
                }
            } catch (e) {
                app.logger.warn('[ARDUINO] Некорректные данные:', jsonStr);
            }
        },

        /**
         * Получение данных о расстоянии во время записи
         */
        getRecordingDistanceData() {
            const data = this.distanceUpdates;
            this.distanceUpdates = [];
            return data;
        },

        /**
         * Закрытие соединения
         */
        async disconnect() {
            try {
                this.isConnected = false;
                
                if (this.reader) {
                    try {
                        await this.reader.cancel();
                    } catch (e) {
                        console.warn('Ошибка при отмене reader:', e);
                    }
                    
                    // Не вызываем release() явно, так как он может быть уже освобожден
                    this.reader = null;
                }
                
                if (this.port) {
                    await this.port.close();
                    this.port = null;
                }
                
                this.buffer = '';
                app.ui.updateArduinoStatus(false);
                app.logger.info('[ARDUINO] Соединение закрыто');
                
            } catch (error) {
                app.logger.error('[ARDUINO] Ошибка отключения:', error);
            }
        },
        
        /**
         * Обработчик ошибок подключения
         */
        _handleConnectionError(app, error) {
            this.isConnected = false;
            app.logger.error('[ARDUINO] Ошибка подключения:', error);
            app.showNotification(`Ошибка Arduino: ${error.message}`, 'error');
            app.ui.updateArduinoStatus(false);
        },
        
        /**
         * Обработчик ошибок чтения
         */
        _handleReadError(app, error) {
            this.isConnected = false;
            app.logger.error('[ARDUINO] Ошибка чтения данных:', error);
            app.ui.updateArduinoStatus(false);
            
            // Пытаемся аккуратно закрыть соединение
            this.disconnect().catch(e => {
                app.logger.warn('[ARDUINO] Ошибка при закрытии после ошибки чтения:', e);
            });
        }
    };

    // Методы для работы с записью
    arduino.startRecording = function() {
        this.distanceUpdates = [];
        app.logger.debug('[ARDUINO] Начата запись данных расстояния');
    };

    arduino.stopRecording = function() {
        app.logger.debug('[ARDUINO] Завершена запись данных расстояния');
    };

    return arduino;
}

/**
 * Инициализация модуля Arduino
 */
function initArduinoModule(app) {
    if (!app.ui || typeof app.ui.updateArduinoStatus !== 'function') {
        app.logger.warn('[ARDUINO] UI методы не доступны - пропускаем инициализацию');
        return null;
    }
    
    try {
        const arduino = setupArduino(app);
        app.logger.info('[ARDUINO] Модуль инициализирован');
        return arduino;
    } catch (error) {
        app.logger.error('[ARDUINO] Ошибка инициализации:', error);
        return null;
    }
}

window.initArduinoModule = initArduinoModule;