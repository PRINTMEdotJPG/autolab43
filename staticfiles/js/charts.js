// static/js/charts.js
function renderMinimaChart(minimaData, stepNumber, frequency) {
    const ctx = document.getElementById(`chart-step-${stepNumber}`);
    if (!ctx) return;

    new Chart(ctx, {
        type: 'line',
        data: {
            labels: minimaData.map(m => m.position),
            datasets: [{
                label: `Шаг ${stepNumber} (${frequency} Гц)`,
                data: minimaData.map(m => m.amplitude),
                borderColor: ['#3e95cd', '#8e5ea2', '#3cba9f'][stepNumber - 1],
                fill: false,
                tension: 0.1
            }]
        },
        options: {
            scales: {
                x: { title: { display: true, text: 'Положение (м)' } },
                y: { title: { display: true, text: 'Амплитуда' } }
            }
        }
    });
}

function renderCombinedChart(stepsData) {
    const ctx = document.getElementById('finalChart');
    if (!ctx) return;

    new Chart(ctx, {
        type: 'line',
        data: {
            labels: stepsData[0].minima.map((_, i) => i),
            datasets: stepsData.map((step, idx) => ({
                label: `Шаг ${step.step} (${step.frequency} Гц)`,
                data: step.minima.map(m => m.amplitude),
                borderColor: ['#3e95cd', '#8e5ea2', '#3cba9f'][idx],
                fill: false,
                tension: 0.1
            }))
        },
        options: {
            scales: {
                x: { title: { display: true, text: 'Положение (м)' } },
                y: { title: { display: true, text: 'Амплитуда' } }
            }
        }
    });
}