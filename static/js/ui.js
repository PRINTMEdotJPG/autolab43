// static/js/ui.js
function setupUI(app) {
    // Получаем элементы с проверкой
    function getElement(id) {
        const el = document.getElementById(id);
        if (!el) console.error('Element not found:', id);
        return el;
    }

    const elements = {
        startBtn: getElement('startExperimentBtn'),
        recordBtn: getElement('recordBtn'),
        experimentSetup: getElement('experimentSetup'),
        audioExperiment: getElement('audioExperiment'),
        confirmParamsBtn: getElement('confirmParamsBtn'),
        currentStepDisplay: getElement('currentStepDisplay'),
        currentFrequency: getElement('currentFrequency'),
        currentTemperature: getElement('currentTemperature'),
        currentDistance: getElement('currentDistance'),
        experimentStep: getElement('experimentStep'),
        studentResultsForm: getElement('studentResultsForm'),
        temperatureInput: getElement('temperature'),
        frequencyInput: getElement('frequency'),
        validationResult: getElement('validationResult'),
        chartsContainer: getElement('chartsContainer'),
        submitResultsBtn: getElement('submitResultsBtn'),
        speedInput: getElement('speed'),
        gammaInput: getElement('gamma'),
        stepCharts: getElement('stepCharts'),
        progressBar: getElement('progressBar'),
        connectionStatus: getElement('connectionStatus'),
        recordingStatus: getElement('recordingStatus'),
        arduinoStatus: getElement('arduinoStatus'),
        distanceStatus: getElement('distanceStatus'),
        validationContent: getElement('validationContent'),
        paramsForm: getElement('paramsForm'),
        resultsForm: getElement('resultsForm'),
        connectArduinoBtn: null // Будет создан динамически
    };

    // ==================== Основные функции UI ====================

    function showStepForm() {
        safeDisplay(elements.experimentSetup, 'block');
        safeDisplay(elements.audioExperiment, 'none');
        safeDisplay(elements.studentResultsForm, 'none');
        safeDisplay(elements.validationResult, 'none');
        
        if (elements.currentStepDisplay) {
            elements.currentStepDisplay.textContent = app.currentStep;
        }
        
        resetInputs([elements.temperatureInput, elements.frequencyInput]);
    }

    function prepareNextStep(step) {
        console.log("Вызов prepareNextStep, step:", step);
        safeDisplay(elements.experimentSetup, 'none');
        safeDisplay(elements.audioExperiment, 'block');
        safeDisplay(elements.studentResultsForm, 'none');
        
        updateStepInfo(step);
        createChartContainer(step);
    }

    function updateStepInfo(step) {
        const stepData = app.stepsData[step-1];
        if (elements.currentFrequency) {
            elements.currentFrequency.innerHTML = `<i class="bi bi-graph-up"></i> Частота: ${stepData?.frequency || '-'} Гц`;
        }
        if (elements.currentTemperature) {
            elements.currentTemperature.innerHTML = `<i class="bi bi-thermometer-half"></i> Температура: ${stepData?.temperature || '-'}°C`;
        }
        if (elements.currentDistance) {
            elements.currentDistance.innerHTML = `<i class="bi bi-rulers"></i> Расстояние: ${stepData?.distance ? stepData.distance.toFixed(1) : '-'} см`;
        }
        if (elements.experimentStep) {
            elements.experimentStep.textContent = `Шаг ${step}/${app.maxSteps}`;
        }
    }

    function createChartContainer(step) {
        if (!document.getElementById(`chart-step-${step}`) && elements.stepCharts) {
            const chartContainer = document.createElement('div');
            chartContainer.className = 'chart-container mb-4';
            chartContainer.innerHTML = `
                <h5>Шаг ${step} (${app.stepsData[step-1]?.frequency || '?'} Гц)</h5>
                <canvas id="chart-step-${step}" height="200"></canvas>
            `;
            elements.stepCharts.appendChild(chartContainer);
        }
    }

    function updateStepData(step, data) {
        if (app.stepsData[step-1]) {
            app.stepsData[step-1] = { ...app.stepsData[step-1], ...data };
            updateStepInfo(step);
            
            if (window.renderMinimaChart) {
                window.renderMinimaChart(data.minima, step, data.frequency);
            }
        }
    }

    function showResultsForm() {
        safeDisplay(elements.experimentSetup, 'none');
        safeDisplay(elements.audioExperiment, 'none');
        safeDisplay(elements.studentResultsForm, 'block');
        
        if (window.renderCombinedChart && app.stepsData.every(step => step.minima && step.minima.length > 0)) {
            window.renderCombinedChart(app.stepsData);
        }
    }

    function showValidationResult(data) {
        if (!elements.validationContent) return;
        
        elements.validationContent.innerHTML = `
            <h4 class="${data.is_valid ? 'text-success' : 'text-danger'}">
                ${data.is_valid ? 'Поздравляем!' : 'Ошибка!'}
            </h4>
            <p>${data.is_valid ? 'Результаты верны!' : 'Результаты не соответствуют ожидаемым значениям'}</p>
            <ul class="text-start">
                <li>Ваша скорость: ${data.student_speed} м/с (система: ${data.system_speed} м/с)</li>
                <li>Ваше γ: ${data.student_gamma} (система: ${data.system_gamma}, эталон: 1.4)</li>
                <li>Ошибка скорости: ${data.speed_error}%</li>
                <li>Ошибка γ: ${data.gamma_error_system}% (от системы), ${data.gamma_error_reference}% (от эталона)</li>
            </ul>
        `;
        safeDisplay(elements.validationResult, 'block');
    }

    function resetUI() {
        safeDisplay(elements.experimentSetup, 'none');
        safeDisplay(elements.audioExperiment, 'none');
        safeDisplay(elements.studentResultsForm, 'none');
        safeDisplay(elements.validationResult, 'none');
        
        resetInputs([
            elements.temperatureInput, 
            elements.frequencyInput,
            elements.speedInput,
            elements.gammaInput
        ]);
        
        if (elements.currentStepDisplay) {
            elements.currentStepDisplay.textContent = '1';
        }
        
        clearCharts();
    }

    function clearCharts() {
        const containers = document.querySelectorAll('.chart-container');
        containers.forEach(container => container.remove());
        
        if (elements.stepCharts) {
            elements.stepCharts.innerHTML = '';
        }
    }

    // ==================== Функции для работы с Arduino ====================

    function updateArduinoStatus(isConnected) {
        if (elements.arduinoStatus) {
            const indicator = elements.arduinoStatus.querySelector('.status-indicator') || document.createElement('span');
            indicator.className = `status-indicator ${isConnected ? 'status-active' : 'status-inactive'}`;
            
            elements.arduinoStatus.innerHTML = '';
            elements.arduinoStatus.appendChild(indicator);
            elements.arduinoStatus.appendChild(document.createTextNode(
                `Arduino: ${isConnected ? 'Подключена' : 'Не подключена'}`
            ));
        }
        
        if (elements.connectArduinoBtn) {
            elements.connectArduinoBtn.innerHTML = `
                <i class="bi bi-cpu"></i> ${isConnected ? 'Отключить' : 'Подключить Arduino'}
            `;
        }
    }

    function updateDistance(distance) {
        if (elements.distanceStatus) {
            const distanceValue = elements.distanceStatus.querySelector('#distanceValue') || 
                                 document.createElement('span');
            distanceValue.id = 'distanceValue';
            distanceValue.textContent = distance.toFixed(1);
            
            elements.distanceStatus.innerHTML = `
                <i class="bi bi-rulers"></i> Расстояние: 
            `;
            elements.distanceStatus.appendChild(distanceValue);
            elements.distanceStatus.appendChild(document.createTextNode(' см'));
        }
        
        // Обновляем расстояние в текущем шаге эксперимента
        if (app.currentStep > 0 && elements.currentDistance) {
            elements.currentDistance.innerHTML = `
                <i class="bi bi-rulers"></i> Расстояние: ${distance.toFixed(1)} см
            `;
        }
    }

    function addArduinoControls() {
        if (elements.experimentSetup) {
            const controlsHTML = `
                <div class="mt-3">
                    <button id="connectArduinoBtn" class="btn btn-sm btn-outline-secondary">
                        <i class="bi bi-cpu"></i> Подключить Arduino
                    </button>
                </div>
            `;
            
            elements.experimentSetup.querySelector('.card-body').insertAdjacentHTML('beforeend', controlsHTML);
            elements.connectArduinoBtn = document.getElementById('connectArduinoBtn');
            
            if (elements.connectArduinoBtn) {
                elements.connectArduinoBtn.addEventListener('click', () => {
                    if (!app.arduino) {
                        app.showNotification('Модуль Arduino недоступен', 'error');
                        return;
                    }
                    
                    if (app.arduino.isConnected) {
                        app.arduino.disconnect();
                    } else {
                        app.arduino.init().catch(e => {
                            app.logger.error('Ошибка инициализации Arduino:', e);
                        });
                    }
                });
            }
        }
    }

    // ==================== Вспомогательные функции ====================

    function safeDisplay(element, display) {
        if (element) element.style.display = display;
    }

    function resetInputs(inputs) {
        inputs.forEach(input => {
            if (input) input.value = '';
        });
    }

    function updateProgress(percent) {
        if (elements.progressBar) {
            elements.progressBar.style.width = `${percent}%`;
            elements.progressBar.setAttribute('aria-valuenow', percent);
        }
    }

    function updateConnectionStatus(isConnected) {
        if (elements.connectionStatus) {
            const indicator = elements.connectionStatus.querySelector('.status-indicator') || 
                             document.createElement('span');
            indicator.className = `status-indicator ${isConnected ? 'status-active' : 'status-inactive'}`;
            
            elements.connectionStatus.innerHTML = '';
            elements.connectionStatus.appendChild(indicator);
            elements.connectionStatus.appendChild(document.createTextNode(
                `WebSocket: ${isConnected ? 'Подключен' : 'Не подключен'}`
            ));
        }
    }

    function updateRecordingStatus(isRecording) {
        if (elements.recordingStatus) {
            const indicator = elements.recordingStatus.querySelector('.status-indicator') || 
                             document.createElement('span');
            indicator.className = `status-indicator ${isRecording ? 'status-active' : 'status-inactive'}`;
            
            elements.recordingStatus.innerHTML = '';
            elements.recordingStatus.appendChild(indicator);
            elements.recordingStatus.appendChild(document.createTextNode(
                `Запись: ${isRecording ? 'Активна' : 'Не активна'}`
            ));
        }
    }

    // ==================== Инициализация обработчиков событий ====================

    function initEventHandlers() {
        if (elements.startBtn) {
            elements.startBtn.addEventListener('click', function() {
                if (app.ws && app.ws.isConnected()) {
                    try {
                        app.logger.info('[UI] Нажата кнопка старта эксперимента');
                        app.startExperiment();
                    } catch (error) {
                        app.logger.error('[UI] Ошибка в обработчике кнопки:', error);
                        app.showNotification('Не удалось начать эксперимент', 'error');
                    }
                } else {
                    app.showNotification('Пожалуйста, дождитесь подключения WebSocket', 'warning');
                }
            });
        }

        if (elements.recordBtn) {
            elements.recordBtn.addEventListener('click', async function() {
                try {
                    if (app.recording.isRecording()) {
                        await app.recording.stop();
                        this.innerHTML = '<i class="bi bi-mic"></i> Начать запись';
                        updateRecordingStatus(false);
                        return;
                    }
                    
                    await app.recording.start();
                    this.innerHTML = '<i class="bi bi-stop-circle"></i> Остановить запись';
                    updateRecordingStatus(true);
                } catch (error) {
                    app.logger.error(`Ошибка записи: ${error.message}`);
                    app.showNotification('Ошибка при записи аудио', 'error');
                }
            });
        }

        if (elements.confirmParamsBtn && elements.paramsForm) {
            elements.paramsForm.addEventListener('submit', async function(e) {
                e.preventDefault();
                
                const temperature = parseFloat(elements.temperatureInput.value);
                const frequency = parseFloat(elements.frequencyInput.value);
                
                if (app.validation.validateTemperature(temperature) && 
                    app.validation.validateFrequency(frequency)) {
                    
                    app.stepsData[app.currentStep - 1] = {
                        ...app.stepsData[app.currentStep - 1],
                        temperature,
                        frequency
                    };
                    
                    try {
                        if (!app.ws.isConnected()) {
                            await app.ws.connect();
                        }
                        
                        const sent = app.ws.send({
                            type: 'experiment_params',
                            step: app.currentStep,
                            temperature,
                            frequency
                        });
                        
                        if (sent) {
                            app.logger.info('Параметры шага сохранены');
                            app.showNotification('Параметры успешно сохранены', 'success');
                        }
                    } catch (error) {
                        app.logger.error('Ошибка отправки', error);
                        app.showNotification('Ошибка при сохранении параметров', 'error');
                    }
                }
            });
        }

        if (elements.submitResultsBtn && elements.resultsForm) {
            elements.resultsForm.addEventListener('submit', function(e) {
                e.preventDefault();
                const speed = parseFloat(elements.speedInput.value);
                const gamma = parseFloat(elements.gammaInput.value);
                
                if (!isNaN(speed) && !isNaN(gamma) && app.ws.isConnected()) {
                    app.ws.send({
                        type: 'final_results',
                        studentSpeed: speed,
                        studentGamma: gamma
                    });
                    app.showNotification('Результаты отправлены на проверку', 'success');
                } else {
                    app.showNotification('Пожалуйста, заполните все поля корректно', 'warning');
                }
            });
        }
    }

    // Инициализация
    initEventHandlers();
    addArduinoControls();

    return {
    showStepForm,
    prepareNextStep,
    showResultsForm,
    showValidationResult,
    updateStepData,
    resetUI,
    updateArduinoStatus, // Добавлено
    updateDistance,      // Добавлено
    addArduinoControls,  // Добавлено!
    elements
};
}