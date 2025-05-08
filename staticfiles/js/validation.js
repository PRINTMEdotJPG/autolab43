// static/js/validation.js
function setupValidation(app) {
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
    
    return {
        validateFrequency,
        validateTemperature
    };
}

window.setupValidation = setupValidation;