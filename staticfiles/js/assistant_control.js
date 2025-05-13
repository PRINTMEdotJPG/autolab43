// Функция инициализации приложения
async function initializeApp() {
    const experimentId = window.location.pathname.split('/').filter(Boolean).pop();
    
    // Инициализация основного объекта приложения
    window.app = {
        logger: {
            info: (msg) => console.log('[APP]', msg),
            error: (msg) => console.error('[APP]', msg),
            warn: (msg) => console.warn('[APP]', msg),
            debug: (msg) => console.debug('[APP]', msg)
        },
        handleWebSocketMessage: async function(data) {
            console.log('[APP] Received WebSocket message:', data);
            
            if (data.type === 'minima_data') {
                console.log('[APP] Received minima data:', data);
                
                // Проверяем, что все необходимые функции доступны
                if (typeof Chart === 'undefined') {
                    console.error('[APP] Chart.js не загружен!');
                    return;
                }
                if (typeof renderMinimaChart === 'undefined') {
                    console.error('[APP] renderMinimaChart не найдена!');
                    return;
                }
                
                // Проверяем наличие canvas элемента
                const canvasId = `chart-step-${data.step}`;
                const canvas = document.getElementById(canvasId);
                if (!canvas) {
                    console.error(`[APP] Canvas элемент ${canvasId} не найден!`);
                    // Попробуем подождать немного и проверить снова
                    await new Promise(resolve => setTimeout(resolve, 500));
                    const retryCanvas = document.getElementById(canvasId);
                    if (!retryCanvas) {
                        console.error(`[APP] Canvas элемент ${canvasId} все еще не найден после повторной попытки!`);
                        return;
                    }
                    console.log(`[APP] Canvas элемент ${canvasId} найден после повторной попытки`);
                }
                
                try {
                    console.log('[APP] Вызываем renderMinimaChart с данными:', {
                        step: data.step,
                        frequency: data.frequency,
                        minimaCount: data.minima.length
                    });
                    renderMinimaChart(data.minima, data.step, data.frequency);
                } catch (error) {
                    console.error('[APP] Ошибка при отрисовке графика:', error);
                }
            } else {
                console.log('[APP] Получено сообщение другого типа:', data.type);
            }
        }
    };

    // Функция для проверки готовности страницы
    async function waitForPageReady() {
        // Проверяем наличие всех canvas элементов
        const canvasIds = ['chart-step-1', 'chart-step-2', 'chart-step-3', 'finalChart'];
        for (const id of canvasIds) {
            const canvas = document.getElementById(id);
            if (!canvas) {
                console.error(`[APP] Canvas элемент ${id} не найден при инициализации`);
                return false;
            }
            console.log(`[APP] Canvas элемент ${id} найден`);
        }
        return true;
    }

    // Загрузка зависимостей
    try {
        // Ждем готовности страницы
        const isPageReady = await waitForPageReady();
        if (!isPageReady) {
            throw new Error('Страница не готова: не найдены необходимые элементы');
        }

        // Загрузка и инициализация WebSocket
        console.log('[APP] Инициализация WebSocket...');
        window.app.ws = setupWebSocket(window.app);
        await window.app.ws.connect();

        // Инициализация recording.js
        if (typeof setupRecording === 'function') {
            window.recording = setupRecording(window.app);
            console.log('[APP] Recording.js инициализирован');
        } else {
            console.error('[APP] Функция setupRecording не найдена');
            return false;
        }

        console.log('[APP] Все зависимости загружены успешно');
        
        // Инициализация обработчиков событий
        initializeEventHandlers();
        
        return true;
    } catch (error) {
        console.error('[APP] Ошибка при загрузке зависимостей:', error);
        return false;
    }
}

// Функция инициализации обработчиков событий
function initializeEventHandlers() {
    const saveBtn = document.getElementById('saveParamsBtn');
    const completeBtn = document.getElementById('completeExperimentBtn');
    const recordBtns = document.querySelectorAll('.record-btn');
    
    // Сохранение параметров
    if (saveBtn) {
        saveBtn.addEventListener('click', async function() {
            const temperature = document.getElementById('temperatureInput').value;
            const frequencies = Array.from(document.querySelectorAll('.stage-freq')).map(input => input.value);
            
            // Проверка, что все частоты заполнены
            if (frequencies.some(f => !f)) {
                showAlert('Заполните частоты для всех этапов!', 'danger');
                return;
            }
        
            try {
                saveBtn.disabled = true;
                saveBtn.innerHTML = '<i class="bi bi-arrow-repeat spin"></i> Сохранение...';
                
                const response = await fetch(`/api/experiment/${experimentId}/save-params/`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': getCSRFToken()
                    },
                    body: JSON.stringify({
                        temperature: temperature,
                        frequencies: frequencies
                    })
                });
                
                if (!response.ok) throw new Error('Ошибка сервера');
                
                showAlert('Параметры успешно сохранены!', 'success');
                
                // Активируем первую кнопку записи
                document.querySelector('.record-btn').disabled = false;
                
            } catch (error) {
                showAlert(`Ошибка: ${error.message}`, 'danger');
            } finally {
                saveBtn.disabled = false;
                saveBtn.innerHTML = '<i class="bi bi-save"></i> Сохранить параметры';
            }
        });
    }
    
    // Запись данных
    recordBtns.forEach(btn => {
        btn.addEventListener('click', async function() {
            const stage = this.dataset.stage;
            const card = this.closest('.stage-card');
            const progress = card.querySelector('.stage-progress');
            
            if (this.classList.contains('btn-primary')) {
                // Начало записи
                try {
                    const temperature = document.getElementById('temperatureInput').value;
                    const frequencies = Array.from(document.querySelectorAll('.stage-freq')).map(input => input.value);
                    
                    if (!window.recording) {
                        throw new Error('Модуль записи не загружен');
                    }

                    if (!window.app.ws || !window.app.ws.isConnected()) {
                        throw new Error('WebSocket не подключен');
                    }

                    window.app = window.app || {};
                    window.app.currentStep = parseInt(stage);
                    window.app.stepsData = frequencies.map((freq, idx) => ({
                        frequency: parseFloat(freq),
                        temperature: parseFloat(temperature)
                    }));

                    // Отправляем параметры эксперимента перед началом записи
                    const experimentParams = {
                        type: 'experiment_params',
                        step: parseInt(stage),
                        frequency: parseFloat(frequencies[stage-1]),
                        temperature: parseFloat(temperature)
                    };
                    
                    console.log('Отправка параметров эксперимента:', experimentParams);
                    
                    if (!window.app.ws.send(experimentParams)) {
                        throw new Error('Ошибка отправки параметров эксперимента');
                    }

                    console.log('Параметры эксперимента отправлены успешно');
                    
                    // Небольшая задержка перед началом записи
                    await new Promise(resolve => setTimeout(resolve, 500));
                    
                    await window.recording.start();
                    
                    this.innerHTML = '<i class="bi bi-stop-circle"></i> Остановить';
                    this.classList.remove('btn-primary');
                    this.classList.add('btn-danger');
                    progress.style.display = 'block';
                } catch (error) {
                    showAlert(`Ошибка записи: ${error.message}`, 'danger');
                }
            } else {
                // Остановка записи
                window.recording.stop();
                completeRecording(stage, card, this);
            }
        });
    });
    
    // Завершение эксперимента
    if (completeBtn) {
        completeBtn.addEventListener('click', async function() {
            if (confirm('Вы уверены, что хотите завершить эксперимент? Данные будут сохранены.')) {
                try {
                    completeBtn.disabled = true;
                    completeBtn.innerHTML = '<i class="bi bi-arrow-repeat spin"></i> Сохранение...';
                    
                    const response = await fetch(`/api/experiment/${experimentId}/complete/`, {
                        method: 'POST',
                        headers: {
                            'X-CSRFToken': getCSRFToken()
                        }
                    });
                    
                    if (!response.ok) throw new Error('Ошибка сервера');
                    
                    window.location.reload();
                } catch (error) {
                    showAlert(`Ошибка: ${error.message}`, 'danger');
                    completeBtn.disabled = false;
                    completeBtn.innerHTML = '<i class="bi bi-flag-fill"></i> Завершить эксперимент';
                }
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

function showAlert(message, type) {
    const alert = document.createElement('div');
    alert.className = `alert alert-${type} alert-dismissible fade show mt-3`;
    alert.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    document.querySelector('.card-body').prepend(alert);
    setTimeout(() => alert.remove(), 5000);
}

function getCSRFToken() {
    return document.querySelector('[name=csrfmiddlewaretoken]').value;
}

// Экспортируем функцию инициализации
window.initializeApp = initializeApp;