function setupWebSocket(app) {
    let socket = null;
    let isConnected = false;

    function connect() {
        return new Promise((resolve, reject) => {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = `${protocol}//${window.location.host}/ws/audio/`;
            
            socket = new WebSocket(wsUrl);

            // Привязываем обработчики к контексту приложения
            socket.onopen = () => {
                isConnected = true;
                updateConnectionStatus();
                app.logger.info('[WS] Соединение установлено');
                resolve();
            };

            socket.onerror = (error) => {
                isConnected = false;
                updateConnectionStatus();
                app.logger.error('[WS] Ошибка соединения', error);
                reject(error);
            };

            socket.onclose = () => {
                isConnected = false;
                updateConnectionStatus();
                app.logger.warn('[WS] Соединение закрыто');
            };

            // Главное исправление: привязываем контекст app
            socket.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    app.logger.debug('[WS] Получено сообщение', data);
                    
                    // Вызываем обработчик в core.js
                    if (app._handleWebSocketMessage) {
                        app._handleWebSocketMessage(data);
                    }
                } catch (error) {
                    app.logger.error('[WS] Ошибка обработки сообщения', error);
                }
            };
        });
    }


    function updateConnectionStatus() {
        const statusElement = document.getElementById('connectionStatus');
        if (statusElement) {
            statusElement.innerHTML = isConnected ?
                '<span class="status-indicator status-active"></span> WebSocket: Подключено' :
                '<span class="status-indicator status-inactive"></span> WebSocket: Не подключено';
        }
    }

    function send(data) {
        try {
            if (!isConnected) throw new Error("WebSocket не подключен");
            socket.send(JSON.stringify(data));
            console.log("Данные успешно отправлены:", data); // ← Добавить
            return true;
        } catch (error) {
            console.error("Ошибка отправки:", error); // ← Добавить
            return false;
        }
    }

    function getSocket() {
        return socket;
    }

    return {
        connect,
        send,
        getSocket,
        isConnected: () => isConnected
    };
}

window.setupWebSocket = setupWebSocket;