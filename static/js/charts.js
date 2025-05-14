// static/js/charts.js
function renderMinimaChart(data, step, frequency) {
    if (!data || !Array.isArray(data) || data.length === 0) {
        console.error('[CHARTS] Некорректные данные для графика:', data);
        return;
    }
    
    const canvasId = `chart-step-${step}`;
    const canvas = document.getElementById(canvasId);
    if (!canvas) {
        console.error(`[CHARTS] Canvas ${canvasId} не найден`);
        return;
    }
    
    // Уничтожаем существующий график, если есть
    const existingChart = Chart.getChart(canvas);
    if (existingChart) {
        existingChart.destroy();
    }
    
    // Подготавливаем данные
    const labels = data.map((_, index) => index + 1);
    const chartData = {
        labels: labels,
        datasets: [{
            label: `Минимумы (${frequency} Гц)`,
            data: data,
            borderColor: 'rgb(75, 192, 192)',
            tension: 0.1,
            pointRadius: 3
        }]
    };
    
    // Создаем новый график
    new Chart(canvas, {
        type: 'line',
        data: chartData,
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                title: {
                    display: true,
                    text: `Этап ${step} - ${frequency} Гц`
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    title: {
                        display: true,
                        text: 'Амплитуда'
                    }
                },
                x: {
                    title: {
                        display: true,
                        text: 'Номер минимума'
                    }
                }
            }
        }
    });
}

function renderCombinedChart(data) {
    if (!data || !data.datasets || !Array.isArray(data.datasets)) {
        console.error('[CHARTS] Некорректные данные для итогового графика:', data);
        return;
    }
    
    const canvas = document.getElementById('finalChart');
    if (!canvas) {
        console.error('[CHARTS] Canvas finalChart не найден');
        return;
    }
    
    // Уничтожаем существующий график, если есть
    const existingChart = Chart.getChart(canvas);
    if (existingChart) {
        existingChart.destroy();
    }
    
    // Создаем новый график
    new Chart(canvas, {
        type: 'line',
        data: {
            labels: data.labels,
            datasets: data.datasets.map(ds => ({
                label: ds.label,
                data: ds.data,
                borderColor: ds.label.includes('Этап 1') ? 'rgb(75, 192, 192)' :
                           ds.label.includes('Этап 2') ? 'rgb(255, 99, 132)' :
                           'rgb(255, 205, 86)',
                tension: 0.1,
                pointRadius: 3
            }))
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                title: {
                    display: true,
                    text: 'Сводный график минимумов'
                },
                legend: {
                    display: true,
                    position: 'top'
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    title: {
                        display: true,
                        text: 'Амплитуда'
                    }
                },
                x: {
                    title: {
                        display: true,
                        text: 'Номер минимума'
                    }
                }
            }
        }
    });
}