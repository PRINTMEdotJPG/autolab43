function setupLogger(app) {
    const logLevels = {
        DEBUG: 0,
        INFO: 1,
        WARN: 2,
        ERROR: 3
    };
    
    let currentLogLevel = logLevels.DEBUG;
    const eventLog = document.getElementById('eventLog');
    
    function formatMessage(level, message) {
        return `[${new Date().toLocaleTimeString()}] [${level}] ${message}`;
    }
    
    function log(level, message, data = null) {
        if (logLevels[level] < currentLogLevel) return;
        
        const formatted = formatMessage(level, message);
        const consoleMethod = {
            'DEBUG': console.debug,
            'INFO': console.info,
            'WARN': console.warn,
            'ERROR': console.error
        }[level] || console.log;
        
        // Безопасный вызов console метода
        consoleMethod(formatted, data || '');
        
        if (eventLog) {
            const entry = document.createElement('div');
            entry.className = `alert alert-${level.toLowerCase()}`;
            entry.innerHTML = `
                <div>${formatted}</div>
                ${data ? `<pre>${JSON.stringify(data, null, 2)}</pre>` : ''}
            `;
            eventLog.prepend(entry);
        }
    }
    
    return {
        debug: (msg, data) => log('DEBUG', msg, data),
        info: (msg, data) => log('INFO', msg, data),
        warn: (msg, data) => log('WARN', msg, data),
        error: (msg, data) => log('ERROR', msg, data),
        setLevel: (level) => currentLogLevel = logLevels[level]
    };
}