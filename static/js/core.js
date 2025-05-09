function AudioRecorderApp() {
    // Инициализация логгера
    this.logger = setupLogger(this);
    this.log = (message, type) => {
        const method = type ? this.logger[type.toLowerCase()] || this.logger.info : this.logger.info;
        method.call(this.logger, message);
    };    this.logger.debug('[CORE] Инициализация приложения');
    
    // Состояние приложения
    this.currentStep = 0;
    this.maxSteps = 3;
    this.stepsData = [];
    this.experimentStarted = false;

    try {
        // Инициализация модулей
        this.ws = setupWebSocket(this);
        this.recording = setupRecording(this);
        this.ui = setupUI(this);
        this.validation = setupValidation(this);

        // Настройка обработчиков
        this._setupWebSocketHandlers();

        // Подключение WebSocket
        this.ws.connect().then(() => {
            this.logger.info('[CORE] WebSocket подключен');
        }).catch(error => {
            this.logger.error('[CORE] Ошибка подключения', error);
        });

        this.currentExperimentId = null;

        this.logger.info('[CORE] Приложение готово к работе');
    } catch (error) {
        this.logger.error('[CORE] Ошибка инициализации', error);
        throw error;
    }

    this.getCSRFToken = function() {
        const cookieValue = document.cookie
            .split('; ')
            .find(row => row.startsWith('csrftoken='))
            ?.split('=')[1];
        return cookieValue || '';
    };
    
    // Заменяем текущую реализацию на:
AudioRecorderApp.prototype.showNotification = function(message, type = 'info') {
    const consoleMethods = {
        'error': 'error',
        'warn': 'warn',
        'info': 'log',
        'success': 'log',
        'debug': 'debug'
    };
    
    const consoleMethod = consoleMethods[type] || 'log';
    const styles = {
        'error': 'color: red; font-weight: bold;',
        'success': 'color: green; font-weight: bold;',
        'warn': 'color: orange;',
        'info': 'color: blue;',
        'debug': 'color: gray;'
    };
    
    // Логируем в консоль с оформлением
    console[consoleMethod](`%c[${type.toUpperCase()}] ${message}`, styles[type] || '');
    
    // Логируем в систему логгирования
    if (this.logger) {
        const logMethod = this.logger[type] || this.logger.info;
        logMethod.call(this.logger, `[UI] ${message}`);
    }
    
    // Показываем UI уведомление (если подключен UI модуль)
    if (this.ui && this.ui.showNotification) {
        this.ui.showNotification(message, type);
    }
};
}

AudioRecorderApp.prototype._setupWebSocketHandlers = function() {
    // Устанавливаем обработчик сообщений в объекте приложения
    this._handleWebSocketMessage = (data) => {
        try {
            console.log("Processing WebSocket message:", data);
            
            switch(data.type) {
                case 'step_confirmation':
                    console.log("Handling step confirmation");
                    this.handleStepConfirmation(data);
                    break;
                case 'minima_data':
                    this.handleMinimaData(data);
                    break;
                case 'experiment_complete':
                    this.handleExperimentCompletion(data);
                    break;
                case 'verification_result':
                    this.handleVerificationResult(data);
                    break;
                default:
                    this.logger.warn('[CORE] Неизвестный тип сообщения', data);
            }
        } catch (error) {
            console.error("Error in message handler:", error);
            this.logger.error('[CORE] Ошибка обработки сообщения', error);
        }
    };

    // Получаем сокет и настраиваем обработчики
    const socket = this.ws.getSocket();
    if (!socket) {
        this.logger.warn('[CORE] WebSocket недоступен');
        return;
    }

    // Обработчики ошибок и закрытия соединения остаются здесь
    socket.onerror = (error) => {
        this.logger.error('[CORE] Ошибка WebSocket', error);
    };

    socket.onclose = () => {
        this.logger.warn('[CORE] Соединение закрыто');
    };

    // Обработчик onmessage теперь в websocket.js
    this.logger.debug('[CORE] WebSocket handlers установлены');
};

AudioRecorderApp.prototype.startNewExperiment = function() {
    return fetch('/api/start-experiment/', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': this.getCSRFToken()
        }
    })
    .then(response => {
        if (!response.ok) throw new Error('Network response was not ok');
        return response.json();
    })
    .then(data => {
        if (data.status === 'success') {
            this.currentExperimentId = data.experiment_id;
            return this.currentExperimentId;
        } else {
            throw new Error(data.message || 'Unknown error');
        }
    });
};

AudioRecorderApp.prototype.startExperiment = async function() {
    if (this.experimentStarted) {
        this.logger.warn('[CORE] Эксперимент уже начат');
        return;
    }
    
    try {
        this.logger.info('[CORE] Запрос на старт эксперимента');
        await this.startNewExperiment();
        
        this.currentStep = 1;
        this.stepsData = Array(this.maxSteps).fill().map((_, i) => ({
            step: i + 1,
            minima: [],
            frequency: null,
            temperature: null,
            status: 'pending'
        }));
        this.experimentStarted = true;
        
        this.ui.showStepForm();
        this.logger.info('[CORE] Эксперимент начат. ID:', this.currentExperimentId);
        this.showNotification('Эксперимент успешно начат', 'success');
        
    } catch (error) {
        this.logger.error('[CORE] Ошибка старта эксперимента:', error);
        this.showNotification(`Ошибка начала эксперимента: ${error.message}`, 'error');
        throw error; // Пробрасываем ошибку дальше
    }
};

AudioRecorderApp.prototype.handleStepConfirmation = function(data) {
    console.log("Step confirmation data:", data); // Добавляем лог
    if (!data.step) {
        this.logger.error('[CORE] Invalid step confirmation: missing step');
        return;
    }
    this.ui.prepareNextStep(data.step);
    this.logger.info(`[CORE] Подтвержден шаг ${data.step}`);
};

AudioRecorderApp.prototype.handleMinimaData = function(data) {
    this.stepsData[data.step - 1] = {
        ...this.stepsData[data.step - 1],
        ...data,
        status: 'processed'
    };

    if (window.renderMinimaChart) {
        window.renderMinimaChart(data.minima, data.step, data.frequency);
    }

    if (data.step < this.maxSteps) {
        this.currentStep = data.step + 1;
        this.ui.showStepForm();
    }
};

AudioRecorderApp.prototype.handleExperimentCompletion = function() {
    this.ui.showResultsForm();
    if (window.renderCombinedChart) {
        window.renderCombinedChart(this.stepsData);
    }
    this.logger.info('[CORE] Эксперимент завершен');
};

AudioRecorderApp.prototype.handleVerificationResult = function(data) {
    this.validationResult = data; // Сохраняем результаты валидации
    this.ui.showValidationResult(data);
    document.getElementById('saveResultsBtn').addEventListener('click', () => {
        this.saveExperimentResults();
    });
    document.getElementById('restartExperimentBtn').addEventListener('click', () => {
        this.resetExperiment();
    });
    this.logger.info('[CORE] Получены результаты проверки');
};

// Новый метод для сохранения результатов
AudioRecorderApp.prototype.saveExperimentResults = function() {
    if (!this.currentExperimentId) {
        this.logger.error('[CORE] Experiment ID is not defined');
        this.showNotification('Эксперимент не начат', 'error');
        return;
    }

    // Подготавливаем данные для сохранения
    const saveData = {
        final_results: {
            system_speed: this.validationResult?.system_speed || 0,
            system_gamma: this.validationResult?.system_gamma || 0,
            student_speed: this.validationResult?.student_speed || 0,
            student_gamma: this.validationResult?.student_gamma || 0,
            error_percent: this.validationResult?.error_percent || 0
        },
        steps: this.stepsData.map(step => ({
            step: step.step,
            frequency: step.frequency,
            temperature: step.temperature,
            minima: step.minima,
            status: step.status
        }))
    };

    fetch(`/api/save-experiment/${this.currentExperimentId}/`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': this.getCSRFToken()
        },
        body: JSON.stringify(saveData)
    })
    .then(response => {
        if (!response.ok) {
            return response.json().then(err => { throw err; });
        }
        return response.json();
    })
    .then(data => {
        if (data.status === 'success') {
            this.logger.info('[CORE] Результаты сохранены');
            this.showNotification('Данные успешно сохранены', 'success');
        } else {
            throw new Error(data.message || 'Unknown error');
        }
    })
    .catch(error => {
        this.logger.error('[CORE] Ошибка сохранения', error);
        this.showNotification('Ошибка сохранения: ' + (error.message || 'Неизвестная ошибка'), 'error');
    });
};

AudioRecorderApp.prototype.resetExperiment = function() {
    this.currentStep = 0;
    this.stepsData = [];
    this.experimentStarted = false;
    this.ui.resetUI();
    this.logger.info('[CORE] Эксперимент сброшен');
};

// Экспорт класса
window.AudioRecorderApp = AudioRecorderApp;