// static/js/recording.js
function setupRecording(app) {
    let mediaRecorder = null;
    let mediaStream = null;
    let isRecording = false;
    let audioChunks = [];
    const recordingInterval = 100; // ms

    async function start() {
        if (!app.ws.isConnected()) {
            throw new Error('WebSocket не подключен');
        }

        try {
            // Запрашиваем доступ к микрофону
            mediaStream = await navigator.mediaDevices.getUserMedia({ 
                audio: {
                    sampleRate: 44100,
                    channelCount: 1,
                    echoCancellation: false,
                    noiseSuppression: false,
                    autoGainControl: false
                }
            });
            
            // Настраиваем MediaRecorder
            mediaRecorder = new MediaRecorder(mediaStream, {
                mimeType: 'audio/webm;codecs=opus',
                audioBitsPerSecond: 128000
            });

            audioChunks = [];
            
            mediaRecorder.ondataavailable = async (e) => {
                if (e.data.size > 0) {
                    audioChunks.push(e.data);
                    await processAndSendAudio();
                }
            };

            mediaRecorder.onerror = (e) => {
                app.log(`Ошибка записи: ${e.error.name}`, 'error');
                stop();
            };

            mediaRecorder.start(recordingInterval);
            isRecording = true;
            
            app.log('Запись начата', 'success');
            updateRecordingStatus(true);
            
        } catch (error) {
            app.log(`Ошибка при запуске записи: ${error.message}`, 'error');
            stop();
            throw error;
        }
    }

    async function processAndSendAudio() {
        if (audioChunks.length === 0 || !app.ws.isConnected()) return;

        try {
            const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
            audioChunks = []; // Очищаем буфер
            
            const arrayBuffer = await audioBlob.arrayBuffer();
            const base64Data = arrayBufferToBase64(arrayBuffer);
            
            app.ws.send({
                type: 'audio_data',
                data: base64Data,
                format: 'webm',
                step: app.currentStep,
                frequency: app.stepsData[app.currentStep-1]?.frequency,
                temperature: app.stepsData[app.currentStep-1]?.temperature
            });

        } catch (error) {
            app.log(`Ошибка обработки аудио: ${error.message}`, 'error');
        }
    }

    function stop() {
        if (mediaRecorder && isRecording) {
            mediaRecorder.stop();
            mediaStream.getTracks().forEach(track => track.stop());
            isRecording = false;
            updateRecordingStatus(false);
            app.log('Запись остановлена', 'info');
        }
    }

    function updateRecordingStatus(recording) {
        const statusElement = document.getElementById('recordingStatus');
        if (statusElement) {
            statusElement.innerHTML = recording 
                ? '<i class="bi bi-record-circle-fill text-danger"></i> Запись: Активна'
                : '<i class="bi bi-record-circle"></i> Запись: Не активна';
        }
    }

    function arrayBufferToBase64(buffer) {
        let binary = '';
        const bytes = new Uint8Array(buffer);
        for (let i = 0; i < bytes.byteLength; i++) {
            binary += String.fromCharCode(bytes[i]);
        }
        return window.btoa(binary);
    }

    return {
        start,
        stop,
        isRecording: () => isRecording
    };
}