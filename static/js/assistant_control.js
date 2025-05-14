// Глобальный объект для хранения состояния приложения
window.app = {
    ws: null,
    currentStep: 1,
    stepsData: [{}, {}, {}], // Инициализируем для 3х шагов
    isInitialized: false,
    isSaving: false,
    equipmentManager: null, // Добавляем ссылку на менеджер оборудования
    arduinoModuleLoaded: typeof window.EquipmentManager !== 'undefined', // Инициализируем исходя из доступности класса
    initializationAttempted: false // Добавляем флаг попытки инициализации
};

if (window.app.arduinoModuleLoaded) {
    console.log('[APP Global Init] EquipmentManager определен при начальной загрузке assistant_control.js. arduinoModuleLoaded установлен в true.');
} else {
    // Этого не должно происходить, если arduino.js загружен перед этим файлом и успешно выполнен.
    console.warn('[APP Global Init] EquipmentManager НЕ определен при начальной загрузке. arduinoModuleLoaded остался false. Проверьте порядок загрузки скриптов и выполнение arduino.js.');
}

// Глобальная переменная для рекордера
let recorder = null;

// Функция для динамического добавления элементов управления Arduino
function createArduinoControls() {
    console.log('[APP] Динамическое создание элементов управления Arduino...');
    
    // Ищем основной контейнер карточки оборудования
    const cardBody = document.querySelector('.card .card-body');
    if (!cardBody) {
        console.error('[APP] Не найден контейнер для элементов управления Arduino');
        return false;
    }
    
    // Проверяем, нет ли уже наших контролов
    if (document.getElementById('arduinoControlsContainer')) {
        console.log('[APP] Элементы управления Arduino уже добавлены');
        return true;
    }
    
    // Создаем контейнер для элементов управления
    const controlsContainer = document.createElement('div');
    controlsContainer.id = 'arduinoControlsContainer';
    
    // Создаем заголовок
    const title = document.createElement('h5');
    title.className = 'card-title';
    title.textContent = 'Оборудование';
    controlsContainer.appendChild(title);
    
    // Создаем блок статуса
    const statusBlock = document.createElement('div');
    statusBlock.className = 'd-flex justify-content-between align-items-center mb-3';
    statusBlock.innerHTML = `
        <span>Статус подключения:</span>
        <span id="equipmentStatus" class="badge badge-danger">Отключено</span>
    `;
    controlsContainer.appendChild(statusBlock);
    
    // Создаем форму ввода порта
    const portInputGroup = document.createElement('div');
    portInputGroup.className = 'mb-3';
    portInputGroup.innerHTML = `
        <div class="input-group">
            <input type="text" id="arduinoPortInput" class="form-control form-control-sm" 
                value="/dev/tty.usbserial-120" placeholder="Путь к порту Arduino">
            <div class="input-group-append">
                <button id="connectToPortBtn" class="btn btn-outline-primary btn-sm">
                    <i class="bi bi-usb-plug"></i> Подключить
                </button>
            </div>
        </div>
        <small class="form-text text-muted">Укажите порт Arduino, например, /dev/tty.usbserial-120 или COM3</small>
    `;
    controlsContainer.appendChild(portInputGroup);
    
    // Создаем кнопку автоматического подключения
    const autoConnectBtn = document.createElement('button');
    autoConnectBtn.id = 'connectEquipmentBtn';
    autoConnectBtn.className = 'btn btn-outline-primary btn-sm w-100 mb-3';
    autoConnectBtn.innerHTML = '<i class="bi bi-usb-plug"></i> Выбрать порт автоматически';
    controlsContainer.appendChild(autoConnectBtn);
    
    // Добавляем разделитель
    const divider = document.createElement('hr');
    controlsContainer.appendChild(divider);
    
    // Вставляем в начало карточки
    cardBody.prepend(controlsContainer);
    
    console.log('[APP] Элементы управления Arduino успешно добавлены');
    return true;
}

// Прослушиваем событие загрузки модуля Arduino
document.addEventListener('arduino_module_loaded', function(e) {
    console.log('[APP EVENT LISTENER] Получено событие arduino_module_loaded:', e.detail);
    if (!window.app.arduinoModuleLoaded) {
        window.app.arduinoModuleLoaded = true;
        console.log('[APP EVENT LISTENER] window.app.arduinoModuleLoaded установлен в true (через событие, ранее был false).');
    }
    
    // Попытка инициализировать менеджер, если DOM готов и менеджер еще не создан
    if ((document.readyState === "interactive" || document.readyState === "complete") &&
        window.app.arduinoModuleLoaded && 
        typeof window.EquipmentManager !== 'undefined' && 
        !window.app.equipmentManager) {
        
        console.log('[APP EVENT LISTENER] DOM готов. Попытка инициализации EquipmentManager из слушателя события.');
        if (createArduinoControls()) { // createArduinoControls проверяет, есть ли куда вставлять элементы
            initializeEquipmentManager();
        } else {
             console.error('[APP EVENT LISTENER] Не удалось создать/найти контейнер для контролов Arduino из слушателя события, инициализация менеджера отложена.');
        }
    } else {
        if (!(document.readyState === "interactive" || document.readyState === "complete")) {
            console.log('[APP EVENT LISTENER] DOM еще не готов, инициализация EquipmentManager будет позже (из DOMContentLoaded или initializeApp).');
        }
    }
});

// Обработчик события DOMContentLoaded
document.addEventListener('DOMContentLoaded', async function() {
    console.log('[APP DOMContentLoaded] DOM загружен. arduinoModuleLoaded:', window.app.arduinoModuleLoaded, "initializationAttempted:", window.app.initializationAttempted);
    
    // Проверяем, не была ли уже попытка инициализации
    if (window.app.initializationAttempted) {
        console.log('[APP] Инициализация уже была попытка, пропускаем');
        return;
    }
    
    // Устанавливаем флаг попытки инициализации
    window.app.initializationAttempted = true;
    
    // Попытка инициализировать EquipmentManager здесь, если он нужен, модуль загружен, но экземпляр еще не создан
    if (window.app.arduinoModuleLoaded && typeof window.EquipmentManager !== 'undefined' && !window.app.equipmentManager) {
        console.log('[APP DOMContentLoaded] Модуль Arduino загружен, класс определен, но менеджер не инициализирован. Попытка инициализации.');
        if (createArduinoControls()) { // Убедимся, что контейнер для контролов доступен
             initializeEquipmentManager();
        } else {
            console.error('[APP DOMContentLoaded] Не удалось создать/найти контейнер для контролов Arduino, инициализация менеджера отложена.');
        }
    }
    
    // Вызываем глобальную функцию initializeApp
    console.log('[APP DOMContentLoaded] Вызываем глобальную функцию initializeApp');
    const initialized = await initializeApp();
    
    if (!initialized) {
        console.error('[APP] Не удалось инициализировать приложение');
        // Сбрасываем флаг, чтобы можно было попробовать снова (хотя это может быть рискованно)
        // window.app.initializationAttempted = false; 
    }
});

// Обработчик события load
window.addEventListener('load', function() {
    console.log('[APP window.load] Страница полностью загружена, проверяем контролы Arduino и EquipmentManager...');
    
    // Проверяем, была ли успешная инициализация приложения
    if (!window.app.isInitialized) {
        console.log('[APP window.load] Приложение не инициализировано к моменту window.load, пропускаем доп. проверки Arduino.');
        return;
    }
    
    // Проверяем и при необходимости создаем контролы Arduino (на всякий случай, если они не создались ранее)
    // и пытаемся инициализировать менеджер, если он все еще не создан.
    if (window.app.arduinoModuleLoaded && typeof window.EquipmentManager !== 'undefined' && !window.app.equipmentManager) {
        console.warn('[APP window.load] EquipmentManager все еще не инициализирован после DOMContentLoaded и initializeApp. Финальная попытка инициализации...');
        if (createArduinoControls()) { // Убедимся, что контейнер для контролов доступен
            initializeEquipmentManager();
        } else {
            console.error('[APP window.load] Не удалось создать/найти контейнер для контролов Arduino на window.load. Менеджер не будет инициализирован.');
            if(!window.app.equipmentManager) useSimulation(); // Если все еще нет менеджера, точно симуляция
        }
    } else if (window.app.equipmentManager) {
         console.log('[APP window.load] EquipmentManager уже существует.');
    } else if (!window.app.arduinoModuleLoaded || typeof window.EquipmentManager === 'undefined') {
        console.warn('[APP window.load] Модуль Arduino не загружен или класс EquipmentManager не определен. Используется симуляция.');
        if(!window.app.equipmentManager) useSimulation(); // Убедимся, что симуляция включена
    }

    // Пытаемся автоматически подключиться к Arduino через 1 секунду после загрузки, если это еще не сделано
    // Это нужно, если initializeApp (и его вызовы autoConnect) завершились до того, как equipmentManager был готов.
    setTimeout(async () => {
        if (window.app.isInitialized && window.app.equipmentManager && !window.app.equipmentManager.port) {
            console.log('[APP window.load setTimeout] Попытка автоматического подключения к Arduino...');
            await autoConnectToArduino();
        } else {
            console.log('[APP window.load setTimeout] Условия для автоподключения не выполнены:', 
                { isInitialized: window.app.isInitialized, equipmentManagerExists: !!window.app.equipmentManager, portExists: window.app.equipmentManager ? !!window.app.equipmentManager.port : null });
        }
    }, 1000);
});

// Функция для инициализации менеджера оборудования
function initializeEquipmentManager() {
    console.log('[APP initializeEquipmentManager] Начало инициализации менеджера оборудования...');
    try {
        if (window.app.equipmentManager) {
            console.warn('[APP initializeEquipmentManager] Менеджер оборудования уже инициализирован. Пропускаем.');
            return true;
        }

        if (typeof window.EquipmentManager === 'undefined') {
            console.error('[APP initializeEquipmentManager] Класс EquipmentManager не определен. Невозможно инициализировать.');
            // Не используем throw, чтобы позволить приложению перейти к симуляции
            useSimulation(); // Переключаемся на симуляцию, если класс недоступен
            return false; 
        }
        
        // Убедимся, что контролы Arduino созданы, т.к. EquipmentManager может их использовать
        if (!document.getElementById('arduinoControlsContainer')) {
            console.log('[APP initializeEquipmentManager] Контролы Arduino еще не созданы. Попытка создать...');
            if (!createArduinoControls()) { // createArduinoControls возвращает true/false
                 console.error('[APP initializeEquipmentManager] Не удалось создать/найти контейнер для контролов Arduino. Инициализация менеджера может быть неполной или использовать симуляцию.');
                 // Если контролы критичны, можно здесь вызвать useSimulation() и вернуть false
                 // Пока что, если EquipmentManager создастся, он будет работать без UI-обновлений статуса в динамических контролах, если они не создались.
            }
        }
        
        console.log('[APP initializeEquipmentManager] Создаем новый экземпляр EquipmentManager.');
        window.app.equipmentManager = new window.EquipmentManager({
            equipmentConnected: false, // Начальное состояние
            updateEquipmentStatus: updateEquipmentStatus, // Функция для обновления UI
            useSimulation: useSimulation, // Функция для переключения на симуляцию
            processEquipmentData: processEquipmentData // Функция для обработки данных
        });
        
        console.log('[APP initializeEquipmentManager] Менеджер оборудования успешно инициализирован:', window.app.equipmentManager);
        // Сразу обновим статус в UI, так как менеджер создан (даже если еще не подключен)
        updateEquipmentStatus(); 
        return true;
    } catch (error) {
        console.error('[APP initializeEquipmentManager] Ошибка инициализации менеджера оборудования:', error);
        // Попытаемся использовать симуляцию как fallback, если EquipmentManager не создался
        useSimulation(); 
        return false;
    }
}

// Функция инициализации WebSocket
async function initializeWebSocket() {
    try {
        // Проверяем experimentId перед созданием WebSocket
        if (!window.experimentId || isNaN(window.experimentId)) {
            console.error('[WS Init] ID эксперимента не определен или некорректен:', window.experimentId);
            throw new Error('ID эксперимента не определен или некорректен');
        }
        
        // Создаем WebSocket соединение
        const wsUrl = `ws://${window.location.host}/ws/experiment/${window.experimentId}/`;
        console.log('[WS Init] Подключение к:', wsUrl);
        
        window.app.ws = new WebSocket(wsUrl);
        
        window.app.ws.onopen = () => {
            console.log('[WS] Соединение установлено');
            showAlert('Подключение к серверу установлено', 'success'); // Изменено сообщение
        };
        
        window.app.ws.onclose = () => {
            console.log('[WS] Соединение закрыто');
            showAlert('Подключение к серверу потеряно', 'warning'); // Изменено сообщение
        };
        
        window.app.ws.onerror = (error) => {
            console.error('[WS] Ошибка WebSocket:', error);
            showAlert('Ошибка WebSocket соединения', 'danger');
        };
        
        window.app.ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                handleWebSocketMessage(data);
            } catch (error) {
                console.error('[WS] Ошибка обработки сообщения:', error);
                showAlert('Ошибка обработки данных от сервера', 'danger'); // Изменено сообщение
            }
        };
        
        // Ждем подключения
        console.log('[WS Init] Ожидание открытия WebSocket соединения...');
        await new Promise((resolve, reject) => {
            const timeout = setTimeout(() => {
                console.error('[WS Init] Таймаут подключения к WebSocket');
                reject(new Error('Таймаут подключения к WebSocket'));
            }, 5000); // 5 секунд таймаут
            
            window.app.ws.addEventListener('open', () => {
                clearTimeout(timeout);
                console.log('[WS Init] Событие "open" получено, WebSocket готов.');
                resolve();
            });
            
            window.app.ws.addEventListener('error', (err) => { // Добавил аргумент err для логирования
                clearTimeout(timeout);
                console.error('[WS Init] Событие "error" получено при подключении WebSocket:', err);
                reject(new Error('Ошибка подключения к WebSocket'));
            });
        });
        
        console.log('[WS Init] WebSocket успешно инициализирован и открыт.');
        return true;
    } catch (error) {
        console.error('[WS Init] Ошибка инициализации WebSocket:', error);
        showAlert(`Ошибка подключения WebSocket: ${error.message}`, 'danger');
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
            
            case 'step_confirmation': // Обработка подтверждения от сервера
                console.log('[WS] Получено подтверждение шага от сервера:', data);
                // Можно добавить логику реакции на это, если необходимо
                break;

            case 'recording_started': // Обработка начала записи от сервера
                console.log('[WS] Сервер подтвердил начало записи для шага:', data.step);
                // Можно обновить UI здесь, если нужно
                break;

            case 'recording_stopped': // Обработка остановки записи от сервера
                console.log('[WS] Сервер подтвердил остановку записи для шага:', data.step);
                // Можно обновить UI здесь, если нужно
                break;
            
            case 'error': // Обработка ошибок от сервера
                console.error('[WS] Получена ошибка от сервера:', data.message);
                showAlert(`Ошибка от сервера (шаг ${data.step || 'N/A'}): ${data.message}`, 'danger');
                break;

            default:
                console.log('[WS] Получено сообщение неизвестного типа:', data.type, data);
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
            console.log('[WS handleParametersUpdated] Установлен текущий шаг:', window.app.currentStep);
        }
        
        showAlert('Параметры эксперимента обновлены сервером', 'info');
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
            if (!btn.classList.contains('btn-outline-success')) { // Если кнопка не была уже помечена как успешно завершенная
                btn.innerHTML = '<i class="bi bi-record-circle"></i> Недоступно';
                btn.classList.remove('btn-primary', 'btn-danger');
                btn.classList.add('btn-secondary');
            }
        });
        
        showAlert('Эксперимент успешно завершен (сообщение от сервера)', 'success');
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
            console.error(`[WS handleMinimaData] Canvas ${canvasId} не найден`);
            throw new Error(`Canvas ${canvasId} не найден`);
        }
        
        if (typeof renderMinimaChart === 'function') {
            await renderMinimaChart(data.minima, data.step, data.frequency);
            console.log('[WS handleMinimaData] График успешно обновлен для шага', data.step);
        } else {
            console.error('[WS handleMinimaData] Функция renderMinimaChart не найдена');
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
        console.log('[APP Init] Начало initializeApp...');
        console.log('[APP Init] Текущее состояние перед инициализацией:', {
            isInitialized: window.app.isInitialized,
            arduinoModuleLoaded: window.app.arduinoModuleLoaded, // Должно быть true, если arduino.js отработал
            equipmentManager: !!window.app.equipmentManager,
            experimentId: window.experimentId // Логируем ID эксперимента, который должен быть установлен из HTML
        });
        
        // Проверяем наличие ID эксперимента (уже должен быть установлен из HTML)
        if (typeof window.EXPERIMENT_ID === 'undefined' || !window.EXPERIMENT_ID) { // Добавил проверку на пустое значение
            console.error('[APP Init] ID эксперимента (window.EXPERIMENT_ID) не определен в глобальной переменной.');
            throw new Error('ID эксперимента не определен в глобальной переменной window.EXPERIMENT_ID');
        }
        
        // Парсим и проверяем ID эксперимента
        const parsedId = parseInt(window.EXPERIMENT_ID);
        if (isNaN(parsedId)) {
            console.error('[APP Init] ID эксперимента (window.EXPERIMENT_ID) не является числом:', window.EXPERIMENT_ID);
            throw new Error('ID эксперимента не является числом');
        }
        
        // Устанавливаем ID эксперимента глобально в window.app (если нужно) и window.experimentId (для WebSocket)
        window.experimentId = parsedId; // Используется в initializeWebSocket
        window.app.experimentId = parsedId; // Для общего доступа в приложении
        console.log('[APP Init] ID эксперимента установлен:', window.app.experimentId);
        
        // Инициализируем WebSocket
        console.log('[APP Init] Начинаем инициализацию WebSocket...');
        const wsInitialized = await initializeWebSocket(); // await здесь важен
        if (!wsInitialized) {
            console.error('[APP Init] Не удалось инициализировать WebSocket. Дальнейшая инициализация может быть неполной.');
            // Можно решить, стоит ли прерывать выполнение или продолжать с ограниченной функциональностью
            // throw new Error('Не удалось инициализировать WebSocket'); 
        } else {
            console.log('[APP Init] WebSocket успешно инициализирован.');
        }
        
        // Инициализируем EquipmentManager, если модуль Arduino УЖЕ загружен к этому моменту
        console.log('[APP Init] Проверка для инициализации EquipmentManager...');
        if (window.app.arduinoModuleLoaded && typeof window.EquipmentManager !== 'undefined') {
            if (!window.app.equipmentManager) { // Только если менеджер ЕЩЕ НЕ создан
                console.log('[APP Init] Модуль Arduino загружен, класс определен, экземпляр менеджера не создан. Инициализируем EquipmentManager...');
                // Убедимся, что DOM готов для createArduinoControls (обычно вызывается внутри initializeEquipmentManager или перед ним)
                // Так как initializeApp вызывается из DOMContentLoaded, DOM должен быть как минимум 'interactive'.
                if (createArduinoControls()) { // Убедимся, что контейнер для контролов доступен
                    const managerInitialized = initializeEquipmentManager();
                    if (!managerInitialized) {
                        console.error('[APP Init] Не удалось инициализировать EquipmentManager при попытке в initializeApp (initializeEquipmentManager вернул false).');
                        // useSimulation() вызывается внутри initializeEquipmentManager при ошибке
                    }
                } else {
                     console.error('[APP Init] Не удалось создать/найти контейнер для контролов Arduino. Инициализация EquipmentManager невозможна. Переход к симуляции.');
                     useSimulation(); 
                }
            } else {
                console.log('[APP Init] EquipmentManager уже был инициализирован ранее.');
            }
        } else {
            console.log(`[APP Init] Условия для немедленной инициализации EquipmentManager не выполнены: arduinoModuleLoaded=${window.app.arduinoModuleLoaded}, EquipmentManager defined=${typeof window.EquipmentManager !== 'undefined'}. Он может быть инициализирован позже или уже используется симуляция.`);
            // Если модуль НЕ загружен (arduinoModuleLoaded=false) ИЛИ класс не определен, это проблема.
            if (!window.app.arduinoModuleLoaded || typeof window.EquipmentManager === 'undefined') {
                 console.warn('[APP Init] Модуль Arduino не загружен или класс EquipmentManager не определен. Переключаемся на симуляцию.');
                 useSimulation();
            }
        }
        
        // Инициализируем обработчики событий для UI
        console.log('[APP Init] Инициализация UI обработчиков событий...');
        initializeEventHandlers(); // Эта функция теперь должна правильно находить кнопки
        console.log('[APP Init] UI обработчики событий инициализированы.');
        
        // Устанавливаем начальные значения из DOM в stepsData и на полях ввода
        console.log('[APP Init] Установка начальных значений параметров эксперимента...');
        const temperatureInput = document.getElementById('temperatureInput');
        const globalTemperature = parseFloat(temperatureInput?.value || 20);
        if (temperatureInput) temperatureInput.value = globalTemperature;

        const frequencyInputs = document.querySelectorAll('.stage-freq');
        frequencyInputs.forEach((input, index) => {
            const step = index + 1;
            const freqValue = parseFloat(input.value || 1500);
            input.value = freqValue;
            // Убедимся, что stepsData[index] существует
            if (!window.app.stepsData[index]) window.app.stepsData[index] = {};
            window.app.stepsData[index].frequency = freqValue;
            window.app.stepsData[index].temperature = globalTemperature;
            console.log(`[APP Init] Инициализированы параметры для этапа ${step} в stepsData:`, JSON.parse(JSON.stringify(window.app.stepsData[index])));
        });
        console.log('[APP Init] Все stepsData после инициализации:', JSON.parse(JSON.stringify(window.app.stepsData)));
        
        // Инициализация рекордера
        console.log('[APP Init] Инициализация рекордера (audio)...');
        if (typeof setupRecording === 'function') {
            window.app.recorder = setupRecording({
                ws: {
                    isConnected: () => window.app.ws && window.app.ws.readyState === WebSocket.OPEN,
                    send: (msg) => {
                        if (window.app.ws && window.app.ws.readyState === WebSocket.OPEN) {
                            window.app.ws.send(msg);
                        } else {
                            console.error('[Recorder] Попытка отправки через WebSocket, но соединение не открыто.');
                            showAlert('Ошибка: WebSocket не подключен для отправки аудио.', 'danger');
                        }
                    }
                },
                logger: console, // Используем глобальный console для логов рекордера
                get currentStep() { return window.app.currentStep; },
                get stepsData() { return window.app.stepsData; } // Передаем актуальные данные
            });
            console.log('[APP Init] Рекордер (audio) инициализирован:', window.app.recorder);
        } else {
            console.error('[APP Init] Функция setupRecording не найдена. Запись аудио будет недоступна.');
        }
        
        window.app.isInitialized = true;
        console.log('[APP Init] Приложение успешно инициализировано (isInitialized = true).');
        
        return true;
    } catch (error) {
        console.error('[APP Init] КРИТИЧЕСКАЯ ОШИБКА ИНИЦИАЛИЗАЦИИ:', error);
        showAlert(`Критическая ошибка инициализации: ${error.message}`, 'danger');
        window.app.isInitialized = false; // Убедимся, что флаг сброшен при ошибке
        return false;
    }
}

// Обработчик данных от оборудования (Arduino)
function processEquipmentData(data) {
    // console.log('[APP processEquipmentData] Получены данные от оборудования:', data); // Можно раскомментировать для детального лога
    
    if (data.distance !== undefined && data.distance !== null) { // Добавлена проверка на null
        // Данные от Arduino приходят в сантиметрах. 
        // Фильтруем отрицательные значения (ошибка датчика), которые EquipmentManager может прислать как null или с флагом error.
        // EquipmentManager уже обработал jsonData.value < 0 и может передать data.distance = null и data.error = true
        if (data.error || data.distance < 0) { // Если есть флаг ошибки или расстояние все еще отрицательное
            console.log('[APP processEquipmentData] Получено некорректное или ошибочное значение расстояния от EquipmentManager:', data.distance);
            const globalDistanceElement = document.getElementById('currentDistance');
            if (globalDistanceElement) {
                globalDistanceElement.textContent = '-- см (ошибка)';
            }
            // Для активного этапа тоже можно отобразить ошибку
            const activeStageButton = document.querySelector('.record-btn.btn-danger');
            if (activeStageButton) {
                const stageContainer = activeStageButton.closest('.stage-card');
                if (stageContainer) {
                    const distanceElement = stageContainer.querySelector('.stage-distance');
                    if (distanceElement) distanceElement.textContent = '-- см (ошибка)';
                }
            }
            return; // Не обрабатываем дальше
        }

        const distanceCm = parseFloat(data.distance).toFixed(1); // Данные УЖЕ в сантиметрах от EquipmentManager
        
        // Обновляем глобальное отображение расстояния
        const globalDistanceElement = document.getElementById('currentDistance');
        if (globalDistanceElement) {
            globalDistanceElement.textContent = `${distanceCm} см`;
            // Можно добавить временную подсветку, если нужно
            // globalDistanceElement.classList.add('text-success'); 
            // setTimeout(() => {
            //     globalDistanceElement.classList.remove('text-success');
            // }, 200);
        } else {
            // console.warn('[APP processEquipmentData] Глобальный элемент currentDistance не найден');
        }

        // Обновление расстояния для активного этапа, если запись идет
        const activeStageButton = document.querySelector('.record-btn.btn-danger'); // btn-danger означает, что запись активна
        if (activeStageButton) {
            const stageContainer = activeStageButton.closest('.stage-card');
            if (stageContainer) {
                const distanceDisplay = stageContainer.querySelector('.distance-display');
                const distanceElement = stageContainer.querySelector('.stage-distance');
                
                if (distanceDisplay && distanceElement) {
                    distanceDisplay.style.display = 'block'; // Показываем блок
                    distanceElement.textContent = `${distanceCm} см`;
                    
                    // Добавляем эффект подсветки для элемента этапа
                    distanceElement.classList.remove('bg-info'); // Убираем старый фон, если был
                    distanceElement.classList.add('bg-warning');
                    setTimeout(() => {
                        distanceElement.classList.remove('bg-warning');
                        distanceElement.classList.add('bg-info'); // Возвращаем стандартный фон
                    }, 150); // Короткая подсветка
                    
                    // console.log(`[APP processEquipmentData] Обновлено расстояние на активном этапе (${activeStageButton.dataset.stage}): ${distanceCm} см`);
                }
            }
        }
    } else if (data.distance === null && data.error) {
        // Это уже обработано выше, но можно добавить отдельный лог, если нужно
        console.log('[APP processEquipmentData] Явно получены данные об ошибке расстояния от EquipmentManager.');
        const globalDistanceElement = document.getElementById('currentDistance');
        if (globalDistanceElement) {
            globalDistanceElement.textContent = '-- см (ошибка)';
        }
    }
}

// Обновление статуса оборудования в UI
function updateEquipmentStatus() {
    const statusElement = document.getElementById('equipmentStatus'); // Статус в динамически созданных контролах
    const directStatusElement = document.getElementById('directEquipmentStatus'); // Статус в HTML-разметке
    
    let isConnected = false;
    if (window.app.equipmentManager && window.app.equipmentManager.port && window.app.equipmentManager.port.readable) { // Более надежная проверка
        isConnected = true;
    }

    console.log('[APP updateEquipmentStatus] Обновление статуса. Подключено:', isConnected, 'Менеджер:', window.app.equipmentManager);

    const updateBadge = (element) => {
        if (element) {
            if (isConnected) {
                element.textContent = 'Подключено';
                element.classList.remove('badge-danger', 'badge-warning');
                element.classList.add('badge-success');
            } else {
                element.textContent = 'Отключено';
                element.classList.remove('badge-success', 'badge-warning');
                element.classList.add('badge-danger');
            }
        } else {
            // console.warn('[APP updateEquipmentStatus] Элемент статуса не найден для обновления.');
        }
    };

    updateBadge(statusElement);
    updateBadge(directStatusElement);
}

// Использование симуляции вместо реального оборудования
function useSimulation() {
    console.warn('[APP] Переключение на симуляцию оборудования. Реальное оборудование недоступно или ошибка подключения.');
    showAlert('Оборудование не доступно. Используется симуляция.', 'warning');
    // Здесь можно добавить логику для имитации данных, если необходимо для тестирования.
    // Например, имитировать подключение:
    if (document.getElementById('equipmentStatus')) {
        const statusElement = document.getElementById('equipmentStatus');
        statusElement.textContent = 'Симуляция';
        statusElement.classList.remove('badge-danger', 'badge-success');
        statusElement.classList.add('badge-warning');
    }
    if (document.getElementById('directEquipmentStatus')) {
        const directStatusElement = document.getElementById('directEquipmentStatus');
        directStatusElement.textContent = 'Симуляция';
        directStatusElement.classList.remove('badge-danger', 'badge-success');
        directStatusElement.classList.add('badge-warning');
    }
}

// Функция инициализации обработчиков событий для UI элементов
function initializeEventHandlers() {
    console.log('[APP EvtHandlers] Начало инициализации UI обработчиков...');
    
    // Обработчики для кнопок записи каждого этапа
    document.querySelectorAll('.record-btn').forEach(button => {
        // Удаляем старые обработчики, чтобы избежать дублирования, если функция вызывается повторно
        // button.removeEventListener('click', handleRecordButtonClick); // Нужна именованная функция
        // Простой способ: заменяем элемент его клоном без обработчиков (если не нужны другие обработчики)
        // const newButton = button.cloneNode(true);
        // button.parentNode.replaceChild(newButton, button);
        // button = newButton; // работаем с новым элементом
        // Более безопасный подход - проверять, не добавлен ли уже обработчик, или использовать addEventListener с опцией { once: true } если нужно, но тут не тот случай.
        // Пока оставим как есть, но это место для потенциального улучшения при множественных вызовах initializeEventHandlers.

        const stage = parseInt(button.dataset.stage);
        console.log(`[APP EvtHandlers] Настройка обработчика для кнопки записи этапа ${stage}`);
        
        button.addEventListener('click', async function() { // Используем function для сохранения this
            const currentButton = this; // Сохраняем ссылку на кнопку
            const currentStage = parseInt(currentButton.dataset.stage);
            const card = currentButton.closest('.stage-card');
            if (!card) {
                console.error(`[APP EvtHandlers] Не найден stage-card для кнопки этапа ${currentStage}`);
                showAlert('Ошибка UI: не найден контейнер этапа.', 'danger');
                return;
            }
            const progressElement = card.querySelector('.stage-progress');
            const distanceDisplay = card.querySelector('.distance-display');


            if (currentButton.classList.contains('btn-primary')) { // Если кнопка "Начать запись"
                console.log(`[APP EvtHandlers] Этап ${currentStage} - Нажата кнопка "Начать запись".`);
                try {
                    // Получаем и валидируем параметры
                    const temperatureInput = document.getElementById('temperatureInput');
                    const frequencyInput = card.querySelector('.stage-freq');
                    
                    if (!temperatureInput || !frequencyInput) {
                        console.error(`[APP EvtHandlers] Этап ${currentStage} - Не найдены поля параметров (температура/частота).`);
                        throw new Error('Не найдены поля ввода параметров этапа.');
                    }
                    
                    const temperature = parseFloat(temperatureInput.value);
                    const frequency = parseFloat(frequencyInput.value);
                    
                    if (isNaN(temperature) || temperature < 10 || temperature > 40) {
                        throw new Error('Температура должна быть в диапазоне от 10 до 40°C.');
                    }
                    if (isNaN(frequency) || frequency < 1000 || frequency > 6000) {
                        throw new Error('Частота должна быть в диапазоне от 1000 до 6000 Гц.');
                    }
                    
                    if (!window.app.ws || window.app.ws.readyState !== WebSocket.OPEN) {
                        console.error(`[APP EvtHandlers] Этап ${currentStage} - WebSocket не подключен.`);
                        throw new Error('WebSocket не подключен. Невозможно начать запись.');
                    }

                    // Проверка, подключено ли оборудование Arduino
                    if (!window.app.equipmentManager || !window.app.equipmentManager.port || !window.app.equipmentManager.port.readable) {
                        console.warn(`[APP EvtHandlers] Этап ${currentStage} - Оборудование Arduino не подключено. Запись начнется без данных с датчика.`);
                        showAlert('Внимание: Arduino не подключено. Запись данных с датчика не будет производиться.', 'warning');
                    } else {
                         // Показываем блок расстояния при начале записи, если Arduino подключен
                        if (distanceDisplay) distanceDisplay.style.display = 'block';
                    }
                    
                    // Обновляем текущий шаг в глобальном состоянии
                    window.app.currentStep = currentStage;
                    console.log(`[APP EvtHandlers] Этап ${currentStage} - Установлен текущий шаг: ${window.app.currentStep}`);
                    
                    // Отправляем параметры эксперимента на сервер ПЕРЕД началом записи
                    await sendExperimentParams(currentStage); // Эта функция может выбросить исключение
                    
                    // Обновляем UI кнопки
                    currentButton.innerHTML = '<i class="bi bi-stop-circle"></i> Остановить';
                    currentButton.classList.remove('btn-primary');
                    currentButton.classList.add('btn-danger');
                    if (progressElement) progressElement.style.display = 'block';
                    
                    // Запускаем запись данных с Arduino, если менеджер доступен и подключен
                    if (window.app.equipmentManager && window.app.equipmentManager.port && window.app.equipmentManager.port.readable) {
                        console.log(`[APP EvtHandlers] Этап ${currentStage} - Запуск записи данных с Arduino.`);
                        window.app.equipmentManager.startRecording(); // Внутри EquipmentManager есть console.log
                    }
                    
                    // Отправляем команду начала записи на сервер
                    console.log(`[APP EvtHandlers] Этап ${currentStage} - Отправка команды 'start_recording' на сервер.`);
                    window.app.ws.send(JSON.stringify({
                        type: 'start_recording',
                        step: currentStage
                    }));
                    
                    // Запускаем запись аудио, если рекордер доступен
                    if (window.app.recorder) {
                        console.log(`[APP EvtHandlers] Этап ${currentStage} - Запуск записи аудио.`);
                        await window.app.recorder.start(); // Эта функция может выбросить исключение
                    } else {
                        console.warn(`[APP EvtHandlers] Этап ${currentStage} - Аудио рекордер не инициализирован. Запись аудио не начнется.`);
                    }
                    console.log(`[APP EvtHandlers] Этап ${currentStage} - Запись успешно начата (клиентская сторона).`);
                    
                } catch (error) {
                    console.error(`[APP EvtHandlers] Этап ${currentStage} - Ошибка начала записи:`, error);
                    showAlert(`Ошибка начала записи (этап ${currentStage}): ${error.message}`, 'danger');
                    // Возвращаем кнопку в исходное состояние, если что-то пошло не так
                    currentButton.innerHTML = '<i class="bi bi-record-circle"></i> Начать запись';
                    currentButton.classList.remove('btn-danger');
                    currentButton.classList.add('btn-primary');
                    if (progressElement) progressElement.style.display = 'none';
                    if (distanceDisplay) distanceDisplay.style.display = 'none';
                    return; // Прерываем выполнение
                }

            } else if (currentButton.classList.contains('btn-danger')) { // Если кнопка "Остановить"
                console.log(`[APP EvtHandlers] Этап ${currentStage} - Нажата кнопка "Остановить запись".`);
                try {
                    let distanceData = null;
                    // Останавливаем запись данных с Arduino и получаем собранные данные
                    if (window.app.equipmentManager && window.app.equipmentManager.isRecording) { // Проверяем, идет ли запись
                        console.log(`[APP EvtHandlers] Этап ${currentStage} - Остановка записи данных с Arduino.`);
                        distanceData = window.app.equipmentManager.stopRecording();
                        console.log(`[APP EvtHandlers] Этап ${currentStage} - Данные с Arduino собраны:`, distanceData);
                        
                        // Данные о расстоянии больше не отправляются отдельным сообщением.
                        // Они будут включены в complete_audio через recorder.
                    } else {
                         console.log(`[APP EvtHandlers] Этап ${currentStage} - Запись с Arduino не активна или менеджер не доступен.`);
                    }
                    
                    // Останавливаем запись аудио, если рекордер доступен и записывает
                    if (window.app.recorder && window.app.recorder.isRecording()) {
                        console.log(`[APP EvtHandlers] Этап ${currentStage} - Остановка записи аудио (передаем distanceData).`);
                        // ПЕРЕДАЕМ distanceData в recorder.stop()
                        // Ожидается, что recorder.stop() или логика внутри него (в onstop)
                        // теперь будет использовать эти distanceData для формирования сообщения complete_audio.
                        await window.app.recorder.stop(distanceData); 
                        
                        // БЛОК НИЖЕ УДАЛЕН, так как recorder.stop() теперь должен сам
                        // корректно сформировать и отправить complete_audio с данными о расстоянии.
                        // Лог "[APP EvtHandlers] Этап X - Нет аудио данных для отправки." больше не должен появляться,
                        // так как мы не ожидаем audioData от recorder.stop() для отправки здесь.
                        /*
                        const audioData = await window.app.recorder.stop(distanceData); // Передаем distanceData
                        if (audioData) { 
                            console.log(`[APP EvtHandlers] Этап ${currentStage} - Отправка аудио данных ('complete_audio') на сервер.`);
                            const messageToSend = {
                                type: 'complete_audio',
                                data: audioData.data, 
                                format: audioData.format || 'webm', 
                                step: currentStage,
                                frequency: parseFloat(card.querySelector('.stage-freq').value), 
                                temperature: parseFloat(document.getElementById('temperatureInput').value),
                                distances: distanceData && distanceData.distances ? distanceData.distances : [], 
                                timestamps: distanceData && distanceData.timestamps ? distanceData.timestamps : [] 
                            };
                            console.log(`[APP EvtHandlers] Этап ${currentStage} - Подготовка сообщения complete_audio:`, JSON.parse(JSON.stringify(messageToSend)));
                            window.app.ws.send(JSON.stringify(messageToSend));
                            console.log(`[APP EvtHandlers] Этап ${currentStage} - Аудио данные (включая данные о расстоянии) отправлены на сервер.`);
                        } else {
                             console.log(`[APP EvtHandlers] Этап ${currentStage} - Нет аудио данных для отправки (из assistant_control).`);
                        }
                        */
                    } else {
                        console.log(`[APP EvtHandlers] Этап ${currentStage} - Запись аудио не активна или рекордер не доступен.`);
                    }
                    
                    // Отправляем команду остановки записи на сервер
                    console.log(`[APP EvtHandlers] Этап ${currentStage} - Отправка команды 'stop_recording' на сервер.`);
                    window.app.ws.send(JSON.stringify({
                        type: 'stop_recording',
                        step: currentStage
                    }));
                    
                    // Обновляем UI кнопки
                    currentButton.innerHTML = '<i class="bi bi-check-circle"></i> Завершено'; // Меняем на "Завершено"
                    currentButton.classList.remove('btn-danger');
                    currentButton.classList.add('btn-outline-success'); // Делаем ее "успешной"
                    currentButton.disabled = true; // Блокируем кнопку после завершения этапа
                    if (progressElement) progressElement.style.display = 'none';
                    // Не скрываем distanceDisplay, чтобы пользователь видел последнее значение
                    
                    console.log(`[APP EvtHandlers] Этап ${currentStage} - Запись успешно остановлена (клиентская сторона).`);

                } catch (error) {
                    console.error(`[APP EvtHandlers] Этап ${currentStage} - Ошибка остановки записи:`, error);
                    showAlert(`Ошибка остановки записи (этап ${currentStage}): ${error.message}`, 'danger');
                    // Не меняем состояние кнопки обратно на "Начать запись", так как процесс мог частично выполниться.
                    // Оставляем кнопку в состоянии "Остановить", чтобы пользователь мог попробовать еще раз, если это имеет смысл,
                    // или администратор должен будет вмешаться. Либо, если ошибка критическая, блокируем ее.
                    // currentButton.disabled = true; // Раскомментировать, если нужно блокировать при ошибке остановки.
                }
            }
        });
    });
    
    // Обработчики для полей ввода частоты
    const frequencyInputs = document.querySelectorAll('.stage-freq');
    frequencyInputs.forEach((input, index) => {
        const step = index + 1;
        console.log(`[APP EvtHandlers] Настройка обработчика для поля частоты этапа ${step}`);
        input.addEventListener('change', function() {
            const value = parseFloat(this.value);
            if (!isNaN(value)) {
                if (window.app.stepsData[index]) { // Убедимся, что объект существует
                    window.app.stepsData[index].frequency = value;
                    console.log(`[APP EvtHandlers] Обновлена частота для этапа ${step} в stepsData:`, value);
                } else {
                    console.warn(`[APP EvtHandlers] stepsData[${index}] не найден для обновления частоты.`);
                }
            }
        });
    });
    
    // Обработчик для поля температуры
    const temperatureInput = document.getElementById('temperatureInput');
    if (temperatureInput) {
        console.log('[APP EvtHandlers] Настройка обработчика для поля температуры.');
        temperatureInput.addEventListener('change', function() {
            const value = parseFloat(this.value);
            if (!isNaN(value)) {
                window.app.stepsData.forEach((stepData, i) => { // stepData, а не step
                    if (stepData) { // Убедимся, что объект существует
                        stepData.temperature = value;
                    } else {
                         console.warn(`[APP EvtHandlers] stepsData[${i}] не найден для обновления температуры.`);
                    }
                });
                console.log('[APP EvtHandlers] Обновлена глобальная температура для всех этапов в stepsData:', value);
            }
        });
    } else {
        console.error('[APP EvtHandlers] Поле ввода температуры не найдено.');
    }

    // Обработчик для кнопки "Подключить" к порту Arduino (из динамических контролов)
    const connectToPortBtn = document.getElementById('connectToPortBtn');
    if (connectToPortBtn) {
        connectToPortBtn.addEventListener('click', async () => {
            console.log('[APP EvtHandlers] Нажата кнопка "Подключить" (динамическая).');
            await autoConnectToArduino(); // Используем существующую функцию
        });
    } else {
        // console.warn('[APP EvtHandlers] Кнопка connectToPortBtn (динамическая) не найдена при инициализации обработчиков.');
        // Это может быть нормально, если createArduinoControls() еще не выполнилась.
    }
    
    // Обработчик для кнопки "Выбрать порт автоматически" (из динамических контролов)
    const connectEquipmentBtn = document.getElementById('connectEquipmentBtn');
    if (connectEquipmentBtn) {
        connectEquipmentBtn.addEventListener('click', async () => {
            console.log('[APP EvtHandlers] Нажата кнопка "Выбрать порт автоматически".');
            if (window.app.equipmentManager) {
                try {
                    // Запрашиваем порт у пользователя через Web Serial API
                    connectEquipmentBtn.disabled = true;
                    connectEquipmentBtn.innerHTML = '<i class="bi bi-hourglass-split"></i> Выбор порта...';
                    await window.app.equipmentManager.connect(); // Этот метод вызывает navigator.serial.requestPort()
                    // Статус обновится через updateEquipmentStatus, вызываемый из connect()
                     connectEquipmentBtn.innerHTML = '<i class="bi bi-usb-plug"></i> Выбрать порт автоматически';
                     connectEquipmentBtn.disabled = false;

                } catch (error) {
                    console.error('[APP EvtHandlers] Ошибка при вызове equipmentManager.connect():', error);
                    showAlert('Ошибка при запросе порта: ' + error.message, 'danger');
                    connectEquipmentBtn.innerHTML = '<i class="bi bi-usb-plug"></i> Выбрать порт автоматически';
                    connectEquipmentBtn.disabled = false;
                }
            } else {
                console.error('[APP EvtHandlers] EquipmentManager не инициализирован для connectEquipmentBtn.');
                showAlert('Менеджер оборудования не готов.', 'warning');
            }
        });
    } else {
        // console.warn('[APP EvtHandlers] Кнопка connectEquipmentBtn (динамическая) не найдена.');
    }

    // Кнопка "Сохранить параметры"
    const saveParamsBtn = document.getElementById('saveParamsBtn');
    if (saveParamsBtn) {
        saveParamsBtn.addEventListener('click', async () => {
            console.log('[APP EvtHandlers] Нажата кнопка "Сохранить параметры".');
            try {
                // Собираем все параметры и отправляем их на сервер
                // Это может быть полезно, если параметры менялись, но запись не производилась
                const temperature = parseFloat(document.getElementById('temperatureInput').value);
                if (isNaN(temperature)) throw new Error('Некорректное значение температуры.');

                const paramsToSend = {
                    type: 'update_all_params', // Новый тип сообщения для сервера
                    temperature: temperature,
                    stages: []
                };

                const freqInputs = document.querySelectorAll('.stage-freq');
                freqInputs.forEach((input, index) => {
                    const freq = parseFloat(input.value);
                    if (isNaN(freq)) throw new Error(`Некорректная частота для этапа ${index + 1}.`);
                    paramsToSend.stages.push({
                        step: index + 1,
                        frequency: freq,
                        temperature: temperature // Используем общую температуру
                    });
                });
                
                if (window.app.ws && window.app.ws.readyState === WebSocket.OPEN) {
                    window.app.ws.send(JSON.stringify(paramsToSend));
                    showAlert('Параметры отправлены на сервер.', 'success');
                    console.log('[APP EvtHandlers] Параметры (update_all_params) отправлены:', paramsToSend);
                } else {
                    throw new Error('WebSocket не подключен для сохранения параметров.');
                }

            } catch (error) {
                console.error('[APP EvtHandlers] Ошибка при сохранении параметров:', error);
                showAlert('Ошибка сохранения параметров: ' + error.message, 'danger');
            }
        });
    }

    // Кнопка "Завершить эксперимент"
    const completeExperimentBtn = document.getElementById('completeExperimentBtn');
    if (completeExperimentBtn) {
        completeExperimentBtn.addEventListener('click', async () => {
            console.log('[APP EvtHandlers] Нажата кнопка "Завершить эксперимент".');
             if (window.app.isSaving) {
                showAlert('Сохранение уже идет...', 'info');
                return;
            }
            if (!confirm('Вы уверены, что хотите завершить эксперимент? Все несохраненные данные для активных этапов могут быть потеряны.')) {
                return;
            }

            window.app.isSaving = true;
            completeExperimentBtn.disabled = true;
            completeExperimentBtn.innerHTML = '<i class="bi bi-hourglass-split"></i> Завершение...';

            try {
                if (window.app.ws && window.app.ws.readyState === WebSocket.OPEN) {
                    window.app.ws.send(JSON.stringify({ type: 'finalize_experiment' })); // Новый тип сообщения
                    console.log('[APP EvtHandlers] Отправлена команда finalize_experiment на сервер.');
                    // Сервер должен ответить сообщением experiment_complete или ошибкой
                    // UI обновится при получении experiment_complete
                } else {
                    throw new Error('WebSocket не подключен для завершения эксперимента.');
                }
            } catch (error) {
                 console.error('[APP EvtHandlers] Ошибка при отправке команды завершения эксперимента:', error);
                showAlert('Ошибка завершения эксперимента: ' + error.message, 'danger');
                completeExperimentBtn.disabled = false;
                completeExperimentBtn.innerHTML = '<i class="bi bi-flag-fill"></i> Завершить эксперимент';
            } finally {
                window.app.isSaving = false; 
                // Не сбрасываем disabled здесь, ждем ответа от сервера или таймаута
            }
        });
    }
    
    console.log('[APP EvtHandlers] UI обработчики событий успешно инициализированы.');
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
        // Проверяем, существует ли еще alert в DOM перед попыткой удалить
        if (alert.parentElement) { 
            alert.classList.remove('show');
            // Даем время для анимации fade out
            setTimeout(() => {
                if (alert.parentElement) { // Еще одна проверка перед удалением
                    alert.remove();
                }
            }, 150);
        }
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

// Функция отправки параметров эксперимента
async function sendExperimentParams(step) {
    try {
        console.log(`[APP sendExperimentParams] Отправка параметров для шага ${step}.`);
        const stageCard = document.querySelector(`.record-btn[data-stage="${step}"]`).closest('.stage-card');
        if (!stageCard) {
            throw new Error(`Не найден stage-card для этапа ${step}`);
        }

        const frequencyInput = stageCard.querySelector('.stage-freq');
        const temperatureInput = document.getElementById('temperatureInput');
        
        // Данные для текущего шага
        const currentFrequency = parseFloat(frequencyInput?.value); // Уже должно быть установлено
        const currentTemperature = parseFloat(temperatureInput?.value); // Уже должно быть установлено
        
        if (isNaN(currentFrequency) || currentFrequency <= 0) {
            console.error(`[APP sendExperimentParams] Некорректная частота для шага ${step}: ${frequencyInput?.value}`);
            throw new Error('Частота должна быть положительным числом.');
        }
        
        if (isNaN(currentTemperature) || currentTemperature < 10 || currentTemperature > 40) {
             console.error(`[APP sendExperimentParams] Некорректная температура: ${temperatureInput?.value}`);
            throw new Error('Температура должна быть в диапазоне от 10 до 40°C.');
        }
        
        // Обновляем stepsData (хотя это должно было произойти при изменении полей)
        if (window.app.stepsData[step - 1]) {
            window.app.stepsData[step - 1].frequency = currentFrequency;
            window.app.stepsData[step - 1].temperature = currentTemperature;
        } else {
            console.warn(`[APP sendExperimentParams] stepsData[${step-1}] не найден для обновления.`);
        }
        console.log(`[APP sendExperimentParams] Обновленные stepsData для шага ${step}:`, JSON.parse(JSON.stringify(window.app.stepsData[step - 1])));
        console.log('[APP sendExperimentParams] Текущие все stepsData:', JSON.parse(JSON.stringify(window.app.stepsData)));

        const params = {
            type: 'experiment_params',
            step: step,
            frequency: currentFrequency,
            temperature: currentTemperature
        };
        
        console.log('[APP sendExperimentParams] Отправка параметров (experiment_params) на сервер:', params);
        
        if (window.app.ws && window.app.ws.readyState === WebSocket.OPEN) {
            window.app.ws.send(JSON.stringify(params));
            console.log('[APP sendExperimentParams] Параметры успешно отправлены.');
        } else {
            console.error('[APP sendExperimentParams] WebSocket соединение не установлено. Невозможно отправить параметры.');
            throw new Error('WebSocket соединение не установлено.');
        }
    } catch (error) {
        console.error('[APP sendExperimentParams] Ошибка отправки experiment_params:', error);
        showAlert('Ошибка отправки параметров на сервер: ' + error.message, 'danger');
        throw error; // Важно пробросить ошибку, чтобы вызывающая функция (например, обработчик кнопки записи) знала о проблеме
    }
}

// Функция автоматического подключения к порту Arduino (через поле ввода)
async function autoConnectToArduino() {
    console.log('[APP autoConnectToArduino] Попытка подключения к Arduino через поле ввода...');
    
    if (!window.app.equipmentManager) {
        console.error('[APP autoConnectToArduino] Менеджер оборудования не инициализирован. Невозможно подключиться.');
        showAlert('Менеджер оборудования не готов.', 'warning');
        return false;
    }
    
    // Получаем порт из поля ввода (динамически созданного)
    const portInput = document.getElementById('arduinoPortInput'); // Поле из createArduinoControls
    if (!portInput) {
        console.error('[APP autoConnectToArduino] Поле ввода arduinoPortInput не найдено.');
        showAlert('Элемент UI для ввода порта не найден.', 'danger');
        return false;
    }
    const portPath = portInput.value.trim();
    
    if (!portPath) {
        console.warn('[APP autoConnectToArduino] Не указан путь к порту Arduino в поле ввода. Пожалуйста, укажите порт или используйте автоматический выбор.');
        showAlert('Укажите путь к порту Arduino в соответствующем поле или используйте кнопку "Выбрать порт автоматически".', 'warning');
        return false;
    }
    
    console.log(`[APP autoConnectToArduino] Подключение к порту ${portPath} через EquipmentManager...`);
    
    const connectBtn = document.getElementById('connectToPortBtn'); // Кнопка из createArduinoControls
    if (connectBtn) {
        connectBtn.disabled = true;
        connectBtn.innerHTML = '<i class="bi bi-hourglass-split"></i> Подключение...';
    }
    
    try {
        // Используем метод connectToPort из КЛИЕНТСКОГО EquipmentManager
        const connected = await window.app.equipmentManager.connectToPort(portPath);
        // updateEquipmentStatus() будет вызван изнутри connectToPort (через this.core.updateEquipmentStatus)
        // или напрямую в connectToPort при успехе/ошибке.
        
        if (connectBtn) {
            connectBtn.disabled = false; // Разблокируем кнопку после попытки
            if (connected) {
                showAlert(`Успешно подключено к порту ${portPath} (через клиент).`, 'success');
                // Текст кнопки и статус должны обновиться через updateEquipmentStatus,
                // вызываемый из EquipmentManager.connectToPort или его методов.
                // Для явности можно обновить здесь, но лучше положиться на колбеки.
                connectBtn.innerHTML = '<i class="bi bi-usb-plug-fill"></i> Подключено';
            } else {
                // showAlert уже должен был быть вызван изнутри connectToPort при ошибке,
                // либо если connectToPort вернул false без явной ошибки.
                connectBtn.innerHTML = '<i class="bi bi-usb-plug"></i> Подключить';
                // Дополнительно выведем сообщение, если оно не было показано
                if (!document.querySelector('#alertContainer .alert-danger')) { // Проверка, не было ли уже ошибки
                    showAlert(`Не удалось подключиться к порту ${portPath}. Проверьте порт и доступность устройства.`, 'danger');
                }
            }
        }
        return connected;

    } catch (error) { // Ловим ошибки, которые могли быть не пойманы внутри connectToPort
        console.error('[APP autoConnectToArduino] Внешняя ошибка при вызове equipmentManager.connectToPort:', error);
        showAlert('Ошибка при подключении к Arduino: ' + error.message, 'danger');
        if (connectBtn) {
            connectBtn.disabled = false;
            connectBtn.innerHTML = '<i class="bi bi-usb-plug"></i> Подключить';
        }
        // Убедимся, что статус обновился на "Отключено" или "Симуляция"
        // (updateEquipmentStatus вызывается внутри connectToPort при ошибке)
        if (window.app.equipmentManager && !window.app.equipmentManager.port) {
             // Если порт не установлен после ошибки, возможно, стоит явно вызвать updateEquipmentStatus
             // или useSimulation, если connectToPort не сделал этого.
            console.log('[APP autoConnectToArduino] Порт не установлен после ошибки, проверяем статус...');
            updateEquipmentStatus(); 
            // Если после updateEquipmentStatus все еще не "Симуляция" и порт null, возможно, стоит вызвать useSimulation
            if (window.app.equipmentManager && !window.app.equipmentManager.port && document.getElementById('equipmentStatus')?.textContent !== 'Симуляция') {
                // useSimulation(); // Раскомментировать, если connectToPort не переключает на симуляцию при ошибках
            }
        }
        return false;
    }
}