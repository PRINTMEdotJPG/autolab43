export function setupValidation(app) {
    function validateFrequency(freq) {
        const isValid = freq >= 1000 && freq <= 6000;
        if (!isValid) app.log(`Частота ${freq} Гц вне диапазона`, 'error');
        return isValid;
    }
    
    function validateTemperature(temp) {
        const isValid = temp >= 10 && temp <= 40;
        if (!isValid) app.log(`Температура ${temp}°C вне диапазона`, 'error');
        return isValid;
    }
    
    async function validateResults(studentData) {
        try {
            const response = await app.ws.sendAndWait({
                type: 'final_results',
                studentSpeed: studentData.speed,
                studentGamma: studentData.gamma
            });
            
            return response.isValid;
        } catch (error) {
            app.log(`Ошибка валидации: ${error}`, 'error');
            return false;
        }
    }
    
    return {
        validateFrequency,
        validateTemperature,
        validateResults
    };
}