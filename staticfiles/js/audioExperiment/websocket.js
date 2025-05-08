export function setupWebSocket(app) {
    let socket = null;
    let reconnectAttempts = 0;
    const maxReconnectAttempts = 5;
    const reconnectDelay = 3000;

    function connect() {
        if (socket && socket.readyState === WebSocket.OPEN) return;

        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/audio/`;

        socket = new WebSocket(wsUrl);

        socket.onopen = () => {
            reconnectAttempts = 0;
            app.log('WebSocket подключен', 'success');
            if (document.getElementById('connectionStatus')) {
                document.getElementById('connectionStatus').textContent = 'Соединение: Активно';
            }
        };

        socket.onerror = (error) => {
            app.log(`Ошибка WebSocket: ${error.message}`, 'error');
            if (document.getElementById('connectionStatus')) {
                document.getElementById('connectionStatus').textContent = 'Соединение: Ошибка';
            }
            attemptReconnect();
        };

        socket.onclose = (event) => {
            app.log(`Соединение закрыто: ${event.reason || 'Причина неизвестна'}`, 'warning');
            attemptReconnect();
        };
    }

    function attemptReconnect() {
        if (reconnectAttempts < maxReconnectAttempts) {
            reconnectAttempts++;
            app.log(`Попытка переподключения ${reconnectAttempts}/${maxReconnectAttempts}...`, 'info');
            setTimeout(connect, reconnectDelay);
        } else {
            app.log('Превышено максимальное количество попыток подключения', 'error');
        }
    }

    function send(data) {
        if (socket?.readyState === WebSocket.OPEN) {
            socket.send(JSON.stringify(data));
        } else {
            app.log('Не удалось отправить данные: WebSocket не подключен', 'error');
        }
    }

    return {
        connect,
        send,
        getSocket: () => socket,
        isConnected: () => socket?.readyState === WebSocket.OPEN
    };
}