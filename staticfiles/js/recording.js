function setupRecording(app) {
    let mediaRecorder = null;
    let mediaStream = null;
    let isRecording = false;
    let audioChunks = [];

    async function start() {
        app.logger.info('[RECORDER] start function called.');
        if (!app.ws.isConnected()) {
            app.logger.error('[RECORDER] WebSocket not connected in start().');
            throw new Error('WebSocket не подключен');
        }
        
        try {
            app.logger.info('[RECORDER] Requesting user media (microphone)...');
            mediaStream = await navigator.mediaDevices.getUserMedia({ 
                audio: {
                    sampleRate: 44100,
                    channelCount: 1,
                    echoCancellation: false,
                    noiseSuppression: false,
                    autoGainControl: false
                }
            });
            app.logger.info('[RECORDER] User media obtained.', mediaStream);
            
            app.logger.info('[RECORDER] Initializing MediaRecorder...');
            mediaRecorder = new MediaRecorder(mediaStream, {
                mimeType: 'audio/webm;codecs=opus',
                audioBitsPerSecond: 128000
            });
            app.logger.info('[RECORDER] MediaRecorder initialized:', mediaRecorder);
    
            audioChunks = [];
            
            mediaRecorder.ondataavailable = (e) => {
                app.logger.debug('[RECORDER] mediaRecorder.ondataavailable event.', e.data);
                if (e.data.size > 0) {
                    audioChunks.push(e.data);
                }
            };
            app.logger.info('[RECORDER] mediaRecorder.ondataavailable assigned.');

            mediaRecorder.onstop = async () => {
                app.logger.info('[RECORDER] mediaRecorder.onstop event fired.');
                await sendCompleteRecording();
            };
            app.logger.info('[RECORDER] mediaRecorder.onstop assigned.');

            mediaRecorder.onerror = (event) => {
                app.logger.error('[RECORDER] MediaRecorder error:', event.error);
            };
            app.logger.info('[RECORDER] mediaRecorder.onerror assigned.');
    
            mediaRecorder.start();
            app.logger.info(`[RECORDER] mediaRecorder.start() called. Current state: ${mediaRecorder.state}`);
            isRecording = true;
            
            app.logger.info('[RECORDER] Запись начата (isRecording = true)');
            updateRecordingStatus(true);
            
        } catch (error) {
            app.logger.error(`[RECORDER] Ошибка при запуске записи (start function): ${error.message}`, error);
            stop(); // Попытка остановить, если что-то пошло не так
            throw error;
        }
    }

    async function sendCompleteRecording() {
        app.logger.info('[RECORDER] Attempting to send complete recording...');
        app.logger.info(`[RECORDER] Audio chunks length: ${audioChunks.length}`);
        app.logger.info(`[RECORDER] WS connected: ${app.ws.isConnected()}`);

        if (audioChunks.length === 0 || !app.ws.isConnected()) {
            app.logger.warn('[RECORDER] Conditions not met to send recording. Aborting.');
            return;
        }

        try {
            app.logger.info('[RECORDER] Processing audio blob...');
            const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
            const arrayBuffer = await audioBlob.arrayBuffer();
            const base64Data = arrayBufferToBase64(arrayBuffer);
            
            const message = {
                type: 'complete_audio',
                data: base64Data,
                format: 'webm',
                step: app.currentStep,
                frequency: app.stepsData[app.currentStep-1]?.frequency,
                temperature: app.stepsData[app.currentStep-1]?.temperature,
                duration: audioBlob.size / (128000 / 8) // Примерная длительность
            };
            app.logger.info('[RECORDER] Sending complete_audio message:', message);
            app.ws.send(JSON.stringify(message));
            app.logger.info('[RECORDER] complete_audio message sent.');

        } catch (error) {
            app.logger.error(`[RECORDER] Ошибка обработки аудио: ${error.message}`, error);
        }
    }

    async function stop() { // Изменено на async, так как start может его вызывать и быть await
        app.logger.info('[RECORDER] stop function called.');
        if (mediaRecorder) {
            app.logger.info(`[RECORDER] In stop: mediaRecorder.state = ${mediaRecorder.state}, isRecording = ${isRecording}`);
        } else {
            app.logger.warn('[RECORDER] In stop: mediaRecorder is null.');
        }

        if (mediaRecorder && isRecording) {
            app.logger.info('[RECORDER] Calling native mediaRecorder.stop()');
            mediaRecorder.stop(); // Это синхронный вызов, onstop будет асинхронным
            app.logger.info(`[RECORDER] Native mediaRecorder.stop() called. Current state: ${mediaRecorder.state}`);
            
            if (mediaStream) {
                mediaStream.getTracks().forEach(track => track.stop());
                app.logger.info('[RECORDER] MediaStream tracks stopped.');
            }
            isRecording = false;
            updateRecordingStatus(false);
            app.logger.info('[RECORDER] Запись остановлена (isRecording = false)');
        } else {
            app.logger.warn('[RECORDER] Native mediaRecorder.stop() NOT called. Conditions: mediaRecorder exists? C1', !!mediaRecorder, `isRecording=${isRecording}`);
            // Если isRecording уже false, но mediaRecorder существует и может быть в состоянии 'recording' или 'paused', все равно пытаемся остановить
            if (mediaRecorder && (mediaRecorder.state === 'recording' || mediaRecorder.state === 'paused')) {
                app.logger.warn('[RECORDER] Attempting to stop mediaRecorder anyway as isRecording was false but state was not inactive.');
                mediaRecorder.stop();
                if (mediaStream) {
                    mediaStream.getTracks().forEach(track => track.stop());
                }
            }
            isRecording = false; // Убедимся, что флаг сброшен
            updateRecordingStatus(false);
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