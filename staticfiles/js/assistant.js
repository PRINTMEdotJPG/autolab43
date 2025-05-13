class AssistantApp {
    constructor() {
        console.log('[DEBUG] AssistantApp constructor called');
        this.isRecording = false;
        this.recordingInterval = null;
        this.currentExperiment = null;
        this.initEventListeners();
    }

    initEventListeners() {
        console.log('[DEBUG] Initializing event listeners');
        const startBtn = document.getElementById('startExperimentBtn');
        
        if (startBtn) {
            console.log('[DEBUG] Found startExperimentBtn:', startBtn);
            startBtn.addEventListener('click', (e) => {
                console.log('[DEBUG] Button clicked!', e);
                this.createExperiment();
            });
        } else {
            console.error('[DEBUG] startExperimentBtn NOT FOUND!');
        }
    }

    async createExperiment() {
        console.log('[DEBUG] createExperiment() called');
        const studentId = document.getElementById('studentSelect')?.value;
        console.log('[DEBUG] Selected student ID:', studentId);
        
        if (!studentId) {
            alert('Выберите студента!');
            return;
        }

        try {
            console.log('[DEBUG] Sending request to /assistant/start-experiment/');
            const response = await fetch('/assistant/start-experiment/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken()
                },
                body: JSON.stringify({
                    student_id: studentId,
                    temperature: 20.0
                })
            });

            console.log('[DEBUG] Response status:', response.status);
            
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.message || 'Ошибка сервера');
            }
            
            const data = await response.json();
            console.log('[DEBUG] Experiment created:', data);
            window.location.href = `/experiment/control/${data.experiment_id}/`;
            
        } catch (error) {
            console.error('[ERROR] createExperiment failed:', error);
            alert(`Ошибка: ${error.message}`);
        }
    }

    getCSRFToken() {
        const token = document.querySelector('[name=csrfmiddlewaretoken]')?.value;
        console.log('[DEBUG] CSRF Token:', token);
        return token || '';
    }
}

// Явная инициализация
console.log('[DEBUG] Loading AssistantApp...');
if (document.getElementById('startExperimentBtn')) {
    window.assistantApp = new AssistantApp();
    console.log('[DEBUG] AssistantApp initialized');
} else {
    console.log('[DEBUG] No startExperimentBtn found on page load');
}