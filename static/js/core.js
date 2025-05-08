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

        this.logger.info('[CORE] Приложение готово к работе');
    } catch (error) {
        this.logger.error('[CORE] Ошибка инициализации', error);
        throw error;
    }
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

AudioRecorderApp.prototype.startExperiment = function() {
    if (this.experimentStarted) return;
    
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
    this.logger.info('[CORE] Начат эксперимент. Шаг 1');
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
    this.ui.showValidationResult(data);
    this.logger.info('[CORE] Получены результаты проверки');
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