// static/js/charts.js
function renderMinimaChart(minimaData, stepNumber, frequency) {
    console.log('[CHARTS] Начало отрисовки графика:', {
        stepNumber,
        frequency,
        minimaCount: minimaData?.length || 0
    });
    
    // Проверка входных данных
    if (!minimaData || !Array.isArray(minimaData) || minimaData.length === 0) {
        console.error('[CHARTS] Некорректные данные для графика:', minimaData);
        return;
    }

    // Получение canvas элемента
    const canvasId = `chart-step-${stepNumber}`;
    const ctx = document.getElementById(canvasId);
    if (!ctx) {
        console.error(`[CHARTS] Canvas элемент не найден: ${canvasId}`);
        return;
    }

    // Проверка, что Chart.js доступен
    if (typeof Chart === 'undefined') {
        console.error('[CHARTS] Chart.js не загружен');
        return;
    }

    console.log('[CHARTS] Canvas найден, создаём график...');
    
    try {
        // Уничтожаем существующий график, если он есть
        const existingChart = Chart.getChart(ctx);
        if (existingChart) {
            console.log('[CHARTS] Уничтожаем существующий график');
            existingChart.destroy();
        }

        // Подготовка данных с прореживанием точек
        const decimationFactor = Math.ceil(minimaData.length / 100); // Оставляем максимум 100 точек
        const decimatedData = minimaData.filter((_, index) => index % decimationFactor === 0);

        const chartData = {
            labels: decimatedData.map(m => m.time),
            datasets: [{
                label: `Шаг ${stepNumber} (${frequency} Гц)`,
                data: decimatedData.map(m => m.amplitude),
                borderColor: ['#3e95cd', '#8e5ea2', '#3cba9f'][stepNumber - 1] || '#3e95cd',
                fill: false,
                tension: 0.1,
                pointRadius: 2, // Уменьшаем размер точек
                borderWidth: 1.5 // Уменьшаем толщину линии
            }]
        };

        // Создание нового графика с оптимизированными настройками
        new Chart(ctx, {
            type: 'line',
            data: chartData,
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: {
                    duration: 0 // Отключаем анимацию для улучшения производительности
                },
                elements: {
                    line: {
                        tension: 0 // Отключаем сглаживание для улучшения производительности
                    }
                },
                scales: {
                    x: { 
                        title: { 
                            display: true, 
                            text: 'Время (с)',
                            font: { size: 11 }
                        },
                        ticks: {
                            maxTicksLimit: 10, // Ограничиваем количество делений на оси
                            font: { size: 10 }
                        }
                    },
                    y: { 
                        title: { 
                            display: true, 
                            text: 'Амплитуда',
                            font: { size: 11 }
                        },
                        ticks: {
                            maxTicksLimit: 8,
                            font: { size: 10 }
                        }
                    }
                },
                plugins: {
                    legend: {
                        display: true,
                        position: 'top',
                        labels: {
                            boxWidth: 12,
                            padding: 8,
                            font: { size: 11 }
                        }
                    },
                    tooltip: {
                        enabled: true,
                        mode: 'index',
                        intersect: false,
                        bodyFont: { size: 11 },
                        titleFont: { size: 11 }
                    }
                }
            }
        });
        
        console.log('[CHARTS] График успешно создан');
    } catch (error) {
        console.error('[CHARTS] Ошибка при создании графика:', error);
    }
}

function renderCombinedChart(stepsData) {
    console.log('[CHARTS] Начало отрисовки итогового графика:', {
        stepsCount: stepsData?.length || 0
    });

    // Проверка входных данных
    if (!stepsData || !Array.isArray(stepsData) || stepsData.length === 0) {
        console.error('[CHARTS] Некорректные данные для итогового графика:', stepsData);
        return;
    }

    const ctx = document.getElementById('finalChart');
    if (!ctx) {
        console.error('[CHARTS] Canvas элемент не найден: finalChart');
        return;
    }

    try {
        // Уничтожаем существующий график, если он есть
        const existingChart = Chart.getChart(ctx);
        if (existingChart) {
            console.log('[CHARTS] Уничтожаем существующий итоговый график');
            existingChart.destroy();
        }

        // Подготовка данных с прореживанием точек
        const datasets = stepsData.map((step, idx) => {
            const decimationFactor = Math.ceil(step.minima.length / 100);
            const decimatedData = step.minima.filter((_, index) => index % decimationFactor === 0);
            
            return {
                label: `Шаг ${step.step} (${step.frequency} Гц)`,
                data: decimatedData.map(m => m.amplitude),
                borderColor: ['#3e95cd', '#8e5ea2', '#3cba9f'][idx] || '#3e95cd',
                fill: false,
                tension: 0,
                pointRadius: 2,
                borderWidth: 1.5
            };
        });

        new Chart(ctx, {
            type: 'line',
            data: {
                labels: datasets[0].data.map((_, i) => i),
                datasets: datasets
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: {
                    duration: 0
                },
                elements: {
                    line: {
                        tension: 0
                    }
                },
                scales: {
                    x: { 
                        title: { 
                            display: true, 
                            text: 'Положение (м)',
                            font: { size: 11 }
                        },
                        ticks: {
                            maxTicksLimit: 10,
                            font: { size: 10 }
                        }
                    },
                    y: { 
                        title: { 
                            display: true, 
                            text: 'Амплитуда',
                            font: { size: 11 }
                        },
                        ticks: {
                            maxTicksLimit: 8,
                            font: { size: 10 }
                        }
                    }
                },
                plugins: {
                    legend: {
                        display: true,
                        position: 'top',
                        labels: {
                            boxWidth: 12,
                            padding: 8,
                            font: { size: 11 }
                        }
                    },
                    tooltip: {
                        enabled: true,
                        mode: 'index',
                        intersect: false,
                        bodyFont: { size: 11 },
                        titleFont: { size: 11 }
                    }
                }
            }
        });
        
        console.log('[CHARTS] Итоговый график успешно создан');
    } catch (error) {
        console.error('[CHARTS] Ошибка при создании итогового графика:', error);
    }
}