export function setupLogger(app) {
    const eventLog = document.getElementById('eventLog');
    
    function log(message, type = 'info') { // Убраны лишние параметры
        const validTypes = ['log', 'error', 'warn', 'info']; // Допустимые методы
        const consoleType = validTypes.includes(type) ? type : 'log';
        
        // Вывод в консоль
        console[consoleType](`[${type.toUpperCase()}] ${message}`);
        
        // Вывод в интерфейс
        if (eventLog) {
            const entryElement = document.createElement('div');
            entryElement.className = `alert alert-${type}`;
            entryElement.textContent = `[${new Date().toLocaleTimeString()}] ${message}`;
            eventLog.prepend(entryElement);
        }
    }
    
    return { log };
}