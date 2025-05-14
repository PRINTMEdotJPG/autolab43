// Глобальный объект для хранения состояния приложения
window.app = {
    ws: null,
    currentStep: 1,
    stepsData: [{}, {}, {}], // Инициализируем для 3х шагов
    isInitialized: false,
    isSaving: false
};

// Глобальная переменная для рекордера
let recorder = null;

// Функция инициализации WebSocket
async function initializeWebSocket() {
    try {
        // Проверяем experimentId перед созданием WebSocket
        if (!window.experimentId || isNaN(window.experimentId)) {
            throw new Error('ID эксперимента не определен или некорректен');
        }
        
        // Создаем WebSocket соединение
        const wsUrl = `ws://${window.location.host}/ws/experiment/${window.experimentId}/`;
        console.log('[WS] Подключение к:', wsUrl);
        
        window.app.ws = new WebSocket(wsUrl);
        
        window.app.ws.onopen = () => {
            console.log('[WS] Соединение установлено');
            showAlert('Подключение к оборудованию установлено', 'success');
        };
        
        window.app.ws.onclose = () => {
            console.log('[WS] Соединение закрыто');
            showAlert('Подключение к оборудованию потеряно', 'warning');
        };
        
        window.app.ws.onerror = (error) => {
            console.error('[WS] Ошибка:', error);
            showAlert('Ошибка подключения к оборудованию', 'danger');
        };
        
        window.app.ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                handleWebSocketMessage(data);
            } catch (error) {
                console.error('[WS] Ошибка обработки сообщения:', error);
                showAlert('Ошибка обработки данных от оборудования', 'danger');
            }
        };
        
        // Ждем подключения
        await new Promise((resolve, reject) => {
            const timeout = setTimeout(() => {
                reject(new Error('Таймаут подключения к WebSocket'));
            }, 5000);
            
            window.app.ws.addEventListener('open', () => {
                clearTimeout(timeout);
                resolve();
            });
            
            window.app.ws.addEventListener('error', () => {
                clearTimeout(timeout);
                reject(new Error('Ошибка подключения к WebSocket'));
            });
        });
        
        return true;
    } catch (error) {
        console.error('[WS] Ошибка инициализации WebSocket:', error);
        showAlert(`Ошибка подключения: ${error.message}`, 'danger');
        return false;
    }
}

// Обработчик сообщений WebSocket
async function handleWebSocketMessage(data) {
    console.log('[WS] Получено сообщение:', data);
    
    try {
        switch (data.type) {
            case 'minima_data':
                await handleMinimaData(data);
                break;
                
            case 'parameters_updated':
                await handleParametersUpdated(data);
                break;
                
            case 'experiment_complete':
                await handleExperimentComplete(data);
                break;
                
            default:
                console.log('[WS] Получено сообщение другого типа:', data.type);
        }
    } catch (error) {
        console.error('[WS] Ошибка обработки сообщения:', error);
        showAlert('Ошибка обработки данных: ' + error.message, 'danger');
    }
}

// Обработчик обновления параметров
async function handleParametersUpdated(data) {
    console.log('[WS] Обработка обновления параметров:', data);
    
    try {
        // Обновляем значения в форме
        const temperatureInput = document.getElementById('temperatureInput');
        if (temperatureInput && data.data.temperature) {
            temperatureInput.value = data.data.temperature;
        }
        
        // Обновляем частоты для каждого этапа
        if (data.data.frequencies) {
            const frequencyInputs = document.querySelectorAll('.stage-freq');
            data.data.frequencies.forEach((freq, index) => {
                if (frequencyInputs[index]) {
                    frequencyInputs[index].value = freq;
                }
            });
        }
        
        // Обновляем текущий шаг
        if (data.data.current_step) {
            window.app.currentStep = data.data.current_step;
        }
        
        showAlert('Параметры эксперимента обновлены', 'info');
    } catch (error) {
        console.error('[WS] Ошибка обновления параметров:', error);
        showAlert('Ошибка обновления параметров: ' + error.message, 'warning');
    }
}

// Обработчик завершения эксперимента
async function handleExperimentComplete(data) {
    console.log('[WS] Эксперимент завершен:', data);
    
    try {
        // Обновляем UI
        const completeBtn = document.getElementById('completeExperimentBtn');
        if (completeBtn) {
            completeBtn.innerHTML = '<i class="bi bi-check-circle"></i> Завершен';
            completeBtn.classList.remove('btn-primary');
            completeBtn.classList.add('btn-success');
            completeBtn.disabled = true;
        }
        
        // Деактивируем все кнопки записи
        document.querySelectorAll('.record-btn').forEach(btn => {
            btn.disabled = true;
            if (!btn.classList.contains('btn-outline-success')) {
                btn.innerHTML = '<i class="bi bi-record-circle"></i> Недоступно';
                btn.classList.remove('btn-primary', 'btn-danger');
                btn.classList.add('btn-secondary');
            }
        });
        
        showAlert('Эксперимент успешно завершен', 'success');
    } catch (error) {
        console.error('[WS] Ошибка обработки завершения эксперимента:', error);
        showAlert('Ошибка при завершении эксперимента: ' + error.message, 'danger');
    }
}

// Обработчик данных минимумов
async function handleMinimaData(data) {
    console.log('[WS] Получены данные минимумов:', data);
    
    try {
        const canvasId = `chart-step-${data.step}`;
        const canvas = document.getElementById(canvasId);
        
        if (!canvas) {
            throw new Error(`Canvas ${canvasId} не найден`);
        }
        
        if (typeof renderMinimaChart === 'function') {
            await renderMinimaChart(data.minima, data.step, data.frequency);
            console.log('[WS] График успешно обновлен');
        } else {
            throw new Error('Функция renderMinimaChart не найдена');
        }
    } catch (error) {
        console.error('[WS] Ошибка обработки данных минимумов:', error);
        showAlert('Ошибка при обновлении графика: ' + error.message, 'warning');
    }
}

// Функция инициализации приложения
async function initializeApp() {
    try {
        console.log('[APP] Начало инициализации приложения...');
        
        // Проверяем наличие ID эксперимента
        if (typeof window.EXPERIMENT_ID === 'undefined') {
            throw new Error('ID эксперимента не определен в глобальной переменной');
        }
        
        // Парсим и проверяем ID эксперимента
        const parsedId = parseInt(window.EXPERIMENT_ID);
        if (isNaN(parsedId)) {
            throw new Error('ID эксперимента не является числом');
        }
        
        // Устанавливаем ID эксперимента глобально
        window.experimentId = parsedId;
        console.log('[APP] ID эксперимента установлен:', window.experimentId);
        
        // Инициализируем WebSocket
        const wsInitialized = await initializeWebSocket();
        if (!wsInitialized) {
            throw new Error('Не удалось инициализировать WebSocket');
        }
        
        // Инициализируем обработчики событий
        initializeEventHandlers();
        
        // Устанавливаем начальные значения из DOM в stepsData и на полях ввода
        const temperatureInput = document.getElementById('temperatureInput');
        const globalTemperature = parseFloat(temperatureInput?.value || 20);
        if (temperatureInput) temperatureInput.value = globalTemperature;

        const frequencyInputs = document.querySelectorAll('.stage-freq');
        frequencyInputs.forEach((input, index) => {
            const step = index + 1;
            const freqValue = parseFloat(input.value || 1500); // Значение по умолчанию из HTML или 1500
            input.value = freqValue; // Убедимся, что поле ввода обновлено
            if (window.app.stepsData[index]) {
                window.app.stepsData[index] = {
                    frequency: freqValue,
                    temperature: globalTemperature // Используем глобальную температуру для всех этапов
                };
            } else { // На случай, если этапов будет больше 3х в будущем
                 window.app.stepsData[index] = { frequency: freqValue, temperature: globalTemperature };
            }
            console.log(`[APP] Initialized step ${step} params in stepsData:`, window.app.stepsData[index]);
        });
        
        // Инициализация рекордера
        console.log('[APP] Initializing recorder...');
        recorder = setupRecording({
            ws: {
                isConnected: () => window.app.ws && window.app.ws.readyState === WebSocket.OPEN,
                send: (msg) => window.app.ws.send(msg)
            },
            logger: console,
            get currentStep() { return window.app.currentStep; },
            get stepsData() { return window.app.stepsData; }
        });
        console.log('[APP] Recorder initialized:', recorder);
        
        window.app.isInitialized = true;
        console.log('[APP] Приложение успешно инициализировано');
        
        return true;
    } catch (error) {
        console.error('[APP] Ошибка инициализации:', error);
        showAlert(`Ошибка инициализации: ${error.message}`, 'danger');
        return false;
    }
}

// Функция инициализации обработчиков событий
function initializeEventHandlers() {
    const saveBtn = document.getElementById('saveParamsBtn');
    const completeBtn = document.getElementById('completeExperimentBtn');
    const recordBtns = document.querySelectorAll('.record-btn');
    
    // Проверяем, что experimentId определен и является числом
    if (!window.experimentId || isNaN(window.experimentId)) {
        console.error('[APP] experimentId не определен или некорректен:', window.experimentId);
        showAlert('Ошибка: ID эксперимента не определен или некорректен', 'danger');
        
        // Деактивируем все кнопки
        if (saveBtn) saveBtn.disabled = true;
        if (completeBtn) completeBtn.disabled = true;
        recordBtns.forEach(btn => btn.disabled = true);
        
        return;
    }
    
    console.log('[APP] Инициализация обработчиков событий для эксперимента:', window.experimentId);
    
    // Обработчик для кнопки сохранения параметров
    if (saveBtn) {
        saveBtn.addEventListener('click', async function(event) {
            event.preventDefault();
            
            if (window.app.isSaving) {
                console.log('[APP] Сохранение уже выполняется...');
                return;
            }
            
            try {
                window.app.isSaving = true;
                saveBtn.disabled = true;
                saveBtn.innerHTML = '<i class="bi bi-hourglass-split spin"></i> Сохранение...';
                
                // Собираем и валидируем данные
                const temperatureInput = document.getElementById('temperatureInput');
                const frequencyInputs = document.querySelectorAll('.stage-freq');
                
                if (!temperatureInput) {
                    throw new Error('Поле температуры не найдено');
                }
                
                const temperature = parseFloat(temperatureInput.value);
                if (isNaN(temperature) || temperature < 10 || temperature > 40) {
                    throw new Error('Температура должна быть в диапазоне от 10 до 40°C');
                }
                
                // Собираем и валидируем частоты для всех этапов
                // И обновляем window.app.stepsData актуальными значениями из полей
                const frequencies = Array.from(frequencyInputs).map((input, index) => {
                    const freq = parseFloat(input.value);
                    if (isNaN(freq) || freq < 1000 || freq > 6000) {
                        throw new Error(`Частота для этапа ${index + 1} должна быть в диапазоне от 1000 до 6000 Гц`);
                    }
                    // Обновляем stepsData ПЕРЕД отправкой на сервер
                    if(window.app.stepsData[index]) {
                        window.app.stepsData[index].frequency = freq;
                        window.app.stepsData[index].temperature = temperature;
                    } else {
                        window.app.stepsData[index] = { frequency: freq, temperature: temperature };
                    }
                    return freq;
                });
                console.log('[APP] Updated all stepsData before save HTTP POST:', JSON.parse(JSON.stringify(window.app.stepsData)));
                
                // Формируем данные для отправки
                const data = {
                    temperature: temperature,
                    frequencies: frequencies,
                    current_step: window.app.currentStep || 1
                };
                
                console.log('[APP] Отправка параметров:', data);
                
                // Отправляем запрос
                const response = await fetch(`/api/experiment/${window.experimentId}/save-params/`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': getCookie('csrftoken')
                    },
                    body: JSON.stringify(data)
                });
                
                if (!response.ok) {
                    const errorData = await response.json();
                    throw new Error(errorData.message || 'Ошибка при сохранении параметров');
                }
                
                const result = await response.json();
                console.log('[APP] Параметры успешно сохранены через HTTP:', result);
                
                showAlert('Параметры успешно сохранены', 'success');
                
            } catch (error) {
                console.error('[APP] Ошибка при сохранении параметров:', error);
                showAlert(`Ошибка: ${error.message}`, 'danger');
            } finally {
                window.app.isSaving = false;
                saveBtn.disabled = false;
                saveBtn.innerHTML = '<i class="bi bi-save"></i> Сохранить параметры';
            }
        });
    }
    
    // Запись данных
    recordBtns.forEach(btn => {
        btn.addEventListener('click', async function() {
            const stage = parseInt(this.dataset.stage);
            const card = this.closest('.stage-card');
            const progress = card.querySelector('.stage-progress');
            
            if (this.classList.contains('btn-primary')) {
                // Начало записи
                console.log(`[APP] Stage ${stage} - Start recording button clicked.`);
                try {
                    // Получаем и валидируем параметры
                    const temperatureInput = document.getElementById('temperatureInput');
                    const frequencyInput = card.querySelector('.stage-freq');
                    
                    if (!temperatureInput || !frequencyInput) {
                        throw new Error('Не найдены поля параметров');
                    }
                    
                    const temperature = parseFloat(temperatureInput.value);
                    const frequency = parseFloat(frequencyInput.value);
                    
                    if (isNaN(temperature) || temperature < 10 || temperature > 40) {
                        throw new Error('Температура должна быть в диапазоне от 10 до 40°C');
                    }
                    
                    if (isNaN(frequency) || frequency < 1000 || frequency > 6000) {
                        throw new Error('Частота должна быть в диапазоне от 1000 до 6000 Гц');
                    }
                    
                    if (!window.app.ws || window.app.ws.readyState !== WebSocket.OPEN) {
                        throw new Error('WebSocket не подключен');
                    }
                    
                    // Обновляем текущий шаг
                    window.app.currentStep = stage;
                    
                    // Отправляем параметры эксперимента перед началом записи
                    await sendExperimentParams(stage);
                    
                    // Показываем прогресс
                    this.innerHTML = '<i class="bi bi-stop-circle"></i> Остановить';
                    this.classList.remove('btn-primary');
                    this.classList.add('btn-danger');
                    progress.style.display = 'block';
                    
                    // Отправляем команду начала записи
                    window.app.ws.send(JSON.stringify({
                        type: 'start_recording',
                        step: stage
                    }));
                    console.log(`[APP] Stage ${stage} - Sent start_recording to server.`);
                    
                    // Запускаем запись аудио
                    if (recorder) {
                        console.log(`[APP] Stage ${stage} - Attempting to call recorder.start()`);
                        await recorder.start();
                        console.log(`[APP] Stage ${stage} - recorder.start() called.`);
                    } else {
                        console.error(`[APP] Stage ${stage} - Recorder object is null, cannot start recording.`);
                    }
                    
                } catch (error) {
                    console.error(`[APP] Stage ${stage} - Ошибка начала записи:`, error);
                    showAlert(`Ошибка: ${error.message}`, 'danger');
                    return;
                }
            } else {
                // Остановка записи
                console.log(`[APP] Stage ${stage} - Stop recording button clicked.`);
                try {
                    window.app.ws.send(JSON.stringify({
                        type: 'stop_recording',
                        step: stage
                    }));
                    console.log(`[APP] Stage ${stage} - Sent stop_recording to server.`);

                    // Останавливаем запись аудио
                    console.log(`[APP] Stage ${stage} - Attempting to call recorder.stop()`);
                    if (recorder) {
                        console.log(`[APP] Stage ${stage} - Recorder object exists, calling recorder.stop().`);
                        await recorder.stop(); // Убедитесь, что stop возвращает Promise или является async
                        console.log(`[APP] Stage ${stage} - recorder.stop() finished.`);
                    } else {
                        console.error(`[APP] Stage ${stage} - Recorder object is null, cannot stop recording.`);
                    }
                    
                    this.innerHTML = '<i class="bi bi-record-circle"></i> Начать запись';
                    this.classList.remove('btn-danger');
                    this.classList.add('btn-primary');
                    progress.style.display = 'none';
                    
                } catch (error) {
                    console.error(`[APP] Stage ${stage} - Ошибка остановки записи:`, error);
                    showAlert(`Ошибка: ${error.message}`, 'danger');
                }
            }
        });
    });
    
    // Завершение эксперимента
    if (completeBtn) {
        completeBtn.addEventListener('click', async function() {
            try {
                // Используем experimentId напрямую из глобальной области
                if (!window.experimentId || isNaN(window.experimentId)) {
                    throw new Error('ID эксперимента не определен или некорректен');
                }
                
                console.log('[APP] Нажата кнопка завершения эксперимента:', window.experimentId);
                
                if (!confirm('Вы уверены, что хотите завершить эксперимент? Данные будут сохранены.')) {
                    return;
                }
                
                // Деактивируем кнопку и показываем прогресс
                completeBtn.disabled = true;
                completeBtn.innerHTML = '<i class="bi bi-hourglass-split spin"></i> Завершение...';
                
                try {
                    // Отправляем запрос на сервер
                    const response = await fetch(`/api/experiment/${window.experimentId}/complete/`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': getCookie('csrftoken')
                        }
                    });
                    
                    if (!response.ok) {
                        const errorData = await response.json();
                        throw new Error(errorData.message || 'Ошибка при завершении эксперимента');
                    }
                    
                    showAlert('Эксперимент успешно завершен', 'success');
                    
                    // Обновляем UI
                    completeBtn.innerHTML = '<i class="bi bi-check-circle"></i> Завершен';
                    completeBtn.classList.remove('btn-primary');
                    completeBtn.classList.add('btn-success');
                    completeBtn.disabled = true;
                    
                    // Деактивируем все кнопки записи
                    document.querySelectorAll('.record-btn').forEach(btn => {
                        btn.disabled = true;
                        if (!btn.classList.contains('btn-outline-success')) {
                            btn.innerHTML = '<i class="bi bi-record-circle"></i> Недоступно';
                            btn.classList.remove('btn-primary', 'btn-danger');
                            btn.classList.add('btn-secondary');
                        }
                    });
                    
                } catch (error) {
                    console.error('[APP] Ошибка при завершении эксперимента:', error);
                    showAlert('Ошибка при завершении эксперимента: ' + error.message, 'danger');
                    
                    // Восстанавливаем кнопку
                    completeBtn.disabled = false;
                    completeBtn.innerHTML = '<i class="bi bi-flag-fill"></i> Завершить эксперимент';
                }
            } catch (error) {
                console.error('[APP] Ошибка при завершении эксперимента:', error);
                showAlert('Ошибка при завершении эксперимента: ' + error.message, 'danger');
            }
        });
    }
}

function completeRecording(stage, card, btn) {
    card.querySelector('.badge').classList.remove('bg-secondary');
    card.querySelector('.badge').classList.add('bg-success');
    card.querySelector('.badge').textContent = 'Завершен';
    
    btn.innerHTML = '<i class="bi bi-check-circle"></i> Завершен';
    btn.classList.remove('btn-danger');
    btn.classList.add('btn-outline-success');
    btn.disabled = true;
    
    showAlert(`Этап ${stage} успешно завершен!`, 'success');
}

// Утилиты для работы с UI
function showAlert(message, type = 'info') {
    const alertContainer = document.getElementById('alertContainer') || createAlertContainer();
    const alert = document.createElement('div');
    alert.className = `alert alert-${type} alert-dismissible fade show`;
    alert.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
    `;
    alertContainer.appendChild(alert);
    
    // Автоматически скрываем через 5 секунд
    setTimeout(() => {
        alert.classList.remove('show');
        setTimeout(() => alert.remove(), 150);
    }, 5000);
}

function createAlertContainer() {
    const container = document.createElement('div');
    container.id = 'alertContainer';
    container.style.cssText = 'position: fixed; top: 20px; right: 20px; z-index: 9999;';
    document.body.appendChild(container);
    return container;
}

function getCSRFToken() {
    const cookies = document.cookie.split(';');
    for (let cookie of cookies) {
        const [name, value] = cookie.trim().split('=');
        if (name === 'csrftoken') {
            return value;
        }
    }
    return '';
}

function getCookie(name) {
    const cookies = document.cookie.split(';');
    for (let cookie of cookies) {
        const [cookieName, cookieValue] = cookie.trim().split('=');
        if (cookieName === name) {
            return cookieValue;
        }
    }
    return null;
}

// Экспортируем функцию инициализации
window.initializeApp = initializeApp;

// Автоматическая инициализация при загрузке DOM
document.addEventListener('DOMContentLoaded', async () => {
    console.log('[APP] DOM загружен, начинаем инициализацию...');
    try {
        const initialized = await initializeApp();
        if (!initialized) {
            console.error('[APP] Не удалось инициализировать приложение');
        }
    } catch (error) {
        console.error('[APP] Ошибка при инициализации:', error);
        showAlert('Ошибка при инициализации приложения', 'danger');
    }
});

// Функция отправки параметров эксперимента
async function sendExperimentParams(step) {
    try {
        const frequencyInputs = document.querySelectorAll('.stage-freq');
        const temperatureInput = document.getElementById('temperatureInput');
        
        // Данные для текущего шага
        const currentFrequency = parseFloat(frequencyInputs[step - 1]?.value || 1500);
        const currentTemperature = parseFloat(temperatureInput?.value || 20);
        
        if (isNaN(currentFrequency) || currentFrequency <= 0) {
            throw new Error('Частота должна быть положительным числом');
        }
        
        if (isNaN(currentTemperature) || currentTemperature < 10 || currentTemperature > 40) {
            throw new Error('Температура должна быть в диапазоне от 10 до 40°C');
        }
        
        // Обновляем глобальную температуру для всех stepsData, если она изменилась
        // и обновляем температуру для текущего шага
        window.app.stepsData.forEach(stepData => {
            stepData.temperature = currentTemperature;
        });
        window.app.stepsData[step - 1].frequency = currentFrequency;
        window.app.stepsData[step - 1].temperature = currentTemperature; // Явное присвоение для текущего шага

        console.log(`[APP] Updated stepsData for step ${step}:`, window.app.stepsData[step - 1]);
        console.log('[APP] Current all stepsData:', JSON.parse(JSON.stringify(window.app.stepsData)));

        const params = {
            type: 'experiment_params',
            step: step,
            frequency: currentFrequency,
            temperature: currentTemperature
        };
        
        console.log('[APP] Отправка параметров эксперимента (experiment_params):', params);
        
        if (window.app.ws && window.app.ws.readyState === WebSocket.OPEN) {
            window.app.ws.send(JSON.stringify(params));
        } else {
            throw new Error('WebSocket соединение не установлено');
        }
    } catch (error) {
        console.error('[APP] Ошибка отправки experiment_params:', error);
        showAlert('Ошибка: ' + error.message, 'danger');
        throw error; // Важно пробросить ошибку, чтобы recorder.start() не вызывался
    }
}