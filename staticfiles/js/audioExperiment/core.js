// static/js/core.js
function AudioRecorderApp() {
    // Инициализация логгера
    this.logger = {
        log: function(message, type = 'info') {
            const eventLog = document.getElementById('eventLog');
            if (eventLog) {
                const entry = document.createElement('div');
                entry.className = `alert alert-${type}`;
                entry.innerHTML = `[${new Date().toLocaleTimeString()}] ${message}`;
                eventLog.prepend(entry);
            }
            console[type] ? console[type](message) : console.log(message);
        }
    };
    this.log = this.logger.log.bind(this.logger);

    // Инициализация состояния
    this.currentStep = 1;
    this.maxSteps = 3;
    this.stepsData = Array(this.maxSteps).fill().map((_, i) => ({
        step: i + 1,
        minima: [],
        frequency: null,
        temperature: null,
        status: 'pending'
    }));

    // Инициализация модулей
    this.ws = setupWebSocket(this);
    this.recording = setupRecording(this);
    this.ui = setupUI(this);
    this.validation = setupValidation(this);

    // Настройка обработчиков WebSocket
    this._setupWebSocketHandlers();

    this.log('Система инициализирована', 'info');
}

AudioRecorderApp.prototype._setupWebSocketHandlers = function() {
    const socket = this.ws.getSocket();
    if (!socket) return;

    socket.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            this.log(`Получено сообщение: ${data.type}`, 'debug');

            switch(data.type) {
                case 'step_confirmation':
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
                case 'error':
                    this.log(data.message, 'error');
                    break;
                default:
                    this.log(`Неизвестный тип сообщения: ${data.type}`, 'warn');
            }
        } catch (error) {
            this.log(`Ошибка обработки сообщения: ${error}`, 'error');
        }
    };
};

AudioRecorderApp.prototype.startExperiment = function() {
    this.currentStep = 1;
    this.stepsData = Array(this.maxSteps).fill().map((_, i) => ({
        step: i + 1,
        minima: [],
        frequency: null,
        temperature: null,
        status: 'pending'
    }));
    this.ui.showStepForm();
    this.log(`Начало эксперимента (шаг ${this.currentStep})`, 'info');
};

AudioRecorderApp.prototype.handleStepConfirmation = function(data) {
    if (data.status === 'ready_for_recording') {
        this.ui.prepareNextStep(this.currentStep);
        this.log(`Параметры шага ${this.currentStep} подтверждены`, 'success');
    }
};

AudioRecorderApp.prototype.handleMinimaData = function(data) {
    if (!data.step || data.step < 1 || data.step > this.maxSteps) return;

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
    } else {
        this.log(`Все данные для шага ${data.step} получены`, 'success');
    }
};

AudioRecorderApp.prototype.handleExperimentCompletion = function(data) {
    this.log('Все шаги эксперимента завершены', 'success');
    this.ui.showResultsForm();
    
    // Отображаем все графики
    this.stepsData.forEach(step => {
        if (step.minima && step.minima.length > 0 && window.renderMinimaChart) {
            window.renderMinimaChart(step.minima, step.step, step.frequency);
        }
    });
    
    // Отображаем совмещенный график
    if (this.stepsData.every(step => step.minima && step.minima.length > 0) && window.renderCombinedChart) {
        window.renderCombinedChart(this.stepsData);
    }
};

AudioRecorderApp.prototype.handleVerificationResult = function(data) {
    this.ui.showValidationResult(data);
    if (data.is_valid) {
        this.log('Результаты успешно проверены!', 'success');
    } else {
        this.log('Результаты не прошли проверку', 'error');
    }
};

AudioRecorderApp.prototype.resetExperiment = function() {
    this.currentStep = 1;
    this.stepsData = Array(this.maxSteps).fill().map((_, i) => ({
        step: i + 1,
        minima: [],
        frequency: null,
        temperature: null,
        status: 'pending'
    }));
    this.ui.resetUI();
    this.log('Эксперимент сброшен', 'info');
};

// Инициализация при загрузке страницы
document.addEventListener('DOMContentLoaded', function() {
    try {
        window.app = new AudioRecorderApp();
        
        // Обработчик кнопки перезапуска
        document.getElementById('restartExperimentBtn')?.addEventListener('click', function() {
            window.app.resetExperiment();
        });
    } catch (error) {
        console.error('Ошибка инициализации:', error);
        const eventLog = document.getElementById('eventLog');
        if (eventLog) {
            const errorElement = document.createElement('div');
            errorElement.className = 'alert alert-danger';
            errorElement.textContent = `Ошибка инициализации: ${error.message}`;
            eventLog.prepend(errorElement);
        }
    }
});