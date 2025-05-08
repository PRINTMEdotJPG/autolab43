function setupRecording(app) {
    let mediaRecorder = null;
    let mediaStream = null;
    let isRecording = false;
    let audioChunks = [];

    async function start() {
        if (!app.ws.isConnected()) {
            throw new Error('WebSocket не подключен');
        }
        
        try {
            mediaStream = await navigator.mediaDevices.getUserMedia({ 
                audio: {
                    sampleRate: 44100,
                    channelCount: 1,
                    echoCancellation: false,
                    noiseSuppression: false,
                    autoGainControl: false
                }
            });
            
            mediaRecorder = new MediaRecorder(mediaStream, {
                mimeType: 'audio/webm;codecs=opus',
                audioBitsPerSecond: 128000
            });
    
            audioChunks = [];
            
            mediaRecorder.ondataavailable = (e) => {
                if (e.data.size > 0) {
                    audioChunks.push(e.data);
                }
            };

            mediaRecorder.onstop = async () => {
                await sendCompleteRecording();
            };
    
            mediaRecorder.start();
            isRecording = true;
            
            app.logger.info('Запись начата');
            updateRecordingStatus(true);
            
        } catch (error) {
            app.logger.error(`Ошибка при запуске записи: ${error.message}`);
            stop();
            throw error;
        }
    }

    async function sendCompleteRecording() {
        if (audioChunks.length === 0 || !app.ws.isConnected()) return;

        try {
            const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
            const arrayBuffer = await audioBlob.arrayBuffer();
            const base64Data = arrayBufferToBase64(arrayBuffer);
            
            app.ws.send({
                type: 'complete_audio',
                data: base64Data,
                format: 'webm',
                step: app.currentStep,
                frequency: app.stepsData[app.currentStep-1]?.frequency,
                temperature: app.stepsData[app.currentStep-1]?.temperature,
                duration: audioBlob.size / (128000 / 8) // Примерная длительность
            });

        } catch (error) {
            app.logger.error(`Ошибка обработки аудио: ${error.message}`);
        }
    }

    function stop() {
        if (mediaRecorder && isRecording) {
            mediaRecorder.stop();
            mediaStream.getTracks().forEach(track => track.stop());
            isRecording = false;
            updateRecordingStatus(false);
            app.logger.info('Запись остановлена');
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