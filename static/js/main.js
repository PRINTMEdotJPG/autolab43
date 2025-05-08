document.addEventListener('DOMContentLoaded', function() {
    console.log('[MAIN] DOM загружен');
    
    try {
        // Проверка обязательных элементов
        const requiredElements = [
            'startExperimentBtn', 
            'recordBtn',
            'experimentSetup'
        ].filter(id => !document.getElementById(id));
        
        if (requiredElements.length > 0) {
            throw new Error(`Отсутствуют элементы: ${requiredElements.join(', ')}`);
        }

        // Инициализация приложения
        console.log('[MAIN] Инициализация приложения');
        window.app = new AudioRecorderApp();
        
        // Обработчик перезапуска
        document.getElementById('restartExperimentBtn')?.addEventListener('click', () => {
            window.app.resetExperiment();
        });

    } catch (error) {
        console.error('[MAIN] Ошибка инициализации:', error);
        const eventLog = document.getElementById('eventLog');
        if (eventLog) {
            eventLog.innerHTML = `
                <div class="alert alert-danger">
                    Ошибка запуска: ${error.message}
                    <button onclick="location.reload()">Перезагрузить</button>
                </div>`;
        }
    }
});

window.addEventListener('error', function(event) {
    console.error('Global error:', event.error);
    const eventLog = document.getElementById('eventLog');
    if (eventLog) {
        eventLog.innerHTML += `
            <div class="alert alert-danger">
                Глобальная ошибка: ${event.error.message}
            </div>`;
    }
});