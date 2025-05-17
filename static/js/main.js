// Основной файл с прямым кодом инициализации Arduino

document.addEventListener('DOMContentLoaded', function() {
    console.log('[MAIN] Страница загружена, начинаем прямую инициализацию Arduino...');
    
    // Создаем элементы управления Arduino напрямую, если они отсутствуют
    // createDirectArduinoControls();
    
    // Добавляем прямые обработчики событий
    // setTimeout(setupDirectHandlers, 500);
});

// Функция для прямого создания элементов управления Arduino
function createDirectArduinoControls() {
    console.log('[MAIN] Прямое создание элементов управления Arduino...');
    
    // Проверяем существующие элементы
    if (document.getElementById('directArduinoControls')) {
        console.log('[MAIN] Прямые элементы управления Arduino уже добавлены');
        return;
    }
    
    // Ищем основной контейнер
    const container = document.querySelector('.container');
    if (!container) {
        console.error('[MAIN] Не найден контейнер для добавления элементов');
        return;
    }
    
    // Создаем карточку Arduino
    const arduinoCard = document.createElement('div');
    arduinoCard.id = 'directArduinoControls';
    arduinoCard.className = 'card mt-4';
    arduinoCard.innerHTML = `
        <div class="card-header bg-primary text-white">
            <h5 class="mb-0">Прямое подключение к Arduino</h5>
        </div>
        <div class="card-body">
            <div class="d-flex justify-content-between align-items-center mb-3">
                <span>Статус подключения:</span>
                <span id="directEquipmentStatus" class="badge badge-danger">Отключено</span>
            </div>
            
            <div class="mb-3">
                <div class="input-group">
                    <input type="text" id="directPortInput" class="form-control" 
                           value="/dev/tty.usbserial-120" placeholder="Путь к порту Arduino">
                    <div class="input-group-append">
                        <button id="directConnectBtn" class="btn btn-primary">
                            <i class="bi bi-usb-plug"></i> Подключить напрямую
                        </button>
                    </div>
                </div>
                <small class="form-text text-muted">Прямое подключение к Arduino, минуя Web Serial API</small>
            </div>
        </div>
    `;
    
    // Добавляем карточку на страницу
    container.appendChild(arduinoCard);
    console.log('[MAIN] Прямые элементы управления Arduino добавлены');
}

// Функция настройки прямых обработчиков событий
function setupDirectHandlers() {
    console.log('[MAIN] Настройка прямых обработчиков событий...');
    
    // Кнопка прямого подключения
    const directConnectBtn = document.getElementById('directConnectBtn');
    if (directConnectBtn) {
        directConnectBtn.addEventListener('click', function() {
            const portInput = document.getElementById('directPortInput');
            const portPath = portInput ? portInput.value.trim() : '';
            
            if (!portPath) {
                alert('Укажите путь к порту Arduino');
                return;
            }
            
            // Прямое подключение через fetch API
            directConnectBtn.disabled = true;
            directConnectBtn.innerHTML = '<i class="bi bi-hourglass-split"></i> Подключение...';
            
            fetch('/api/arduino/connect/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken()
                },
                body: JSON.stringify({ port: portPath })
            })
            .then(response => response.json())
            .then(data => {
                directConnectBtn.disabled = false;
                
                if (data.success) {
                    directConnectBtn.innerHTML = '<i class="bi bi-usb-plug-fill"></i> Подключено';
                    const statusBadge = document.getElementById('directEquipmentStatus');
                    if (statusBadge) {
                        statusBadge.className = 'badge badge-success';
                        statusBadge.textContent = 'Подключено';
                    }
                    
                    if (window.app && window.app.equipmentManager) {
                        window.app.equipmentManager.core.equipmentConnected = true;
                        window.app.equipmentManager.core.updateEquipmentStatus();
                    }
                    
                    // Запускаем автоматическое подключение в основном интерфейсе
                    if (typeof autoConnectToArduino === 'function') {
                        autoConnectToArduino();
                    }
                    
                    alert('Успешно подключено к Arduino на порту ' + portPath);
                } else {
                    directConnectBtn.innerHTML = '<i class="bi bi-usb-plug"></i> Подключить напрямую';
                    alert('Ошибка подключения: ' + (data.error || 'Неизвестная ошибка'));
                }
            })
            .catch(error => {
                directConnectBtn.disabled = false;
                directConnectBtn.innerHTML = '<i class="bi bi-usb-plug"></i> Подключить напрямую';
                alert('Ошибка запроса: ' + error.message);
            });
        });
    }
}

// Вспомогательная функция для получения CSRF токена
function getCsrfToken() {
    const cookies = document.cookie.split(';');
    for (let cookie of cookies) {
        const [name, value] = cookie.trim().split('=');
        if (name === 'csrftoken') {
            return value;
        }
    }
    return '';
}