/**
 * Специфичный функционал для студентов
 */
class StudentApp {
    constructor() {
      this.initExperimentList();
      this.initResultSubmission();
    }
  
    initExperimentList() {
      document.querySelectorAll('.experiment-item').forEach(item => {
        item.addEventListener('click', () => {
          this.loadExperiment(item.dataset.id);
        });
      });
    }
  
    async loadExperiment(experimentId) {
      try {
        const response = await fetch(`/api/get-experiment/${experimentId}/`);
        const data = await response.json();
        this.displayExperimentData(data);
      } catch (error) {
        console.error('Ошибка загрузки:', error);
      }
    }
  
    initResultSubmission() {
      document.getElementById('resultsForm')?.addEventListener('submit', async (e) => {
        e.preventDefault();
        await this.submitResults();
      });
    }
  
    async submitResults() {
      const formData = {
        gamma: parseFloat(document.getElementById('gammaInput').value),
        speed: parseFloat(document.getElementById('speedInput').value)
      };
  
      try {
        const response = await fetch('/api/submit-results/', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': this.getCSRFToken()
          },
          body: JSON.stringify(formData)
        });
        
        const result = await response.json();
        this.showResult(result);
      } catch (error) {
        console.error('Ошибка:', error);
      }
    }
  }
  
  // Инициализация для студентов
  if (document.querySelector('.student-dashboard')) {
    window.studentApp = new StudentApp();
  }

function updateFormState(experimentData) {
    console.log('[Form State] updateFormState вызван с данными:', experimentData);
    const studentGammaInput = document.getElementById('student_gamma');
    const studentSpeedInput = document.getElementById('student_speed');
    const submitButton = document.getElementById('submit_results_button');
    const retryButton = document.getElementById('retry_experiment_button'); // Кнопка "Повторить попытку"
    const resultDisplay = document.getElementById('result_display'); // Элемент для отображения результатов

    if (!studentGammaInput || !studentSpeedInput || !submitButton || !retryButton || !resultDisplay) {
        console.error('[Form State] Один или несколько элементов формы не найдены.');
        return;
    }

    // Сначала скроем кнопку "Повторить попытку"
    retryButton.style.display = 'none';
    resultDisplay.innerHTML = ''; // Очищаем предыдущие результаты/сообщения

    const resultsStatus = experimentData.results_processing_status;
    console.log(`[Form State] Статус обработки результатов: ${resultsStatus}`);

    // Заполняем поля, если есть данные от студента (даже если статус fail)
    if (experimentData.student_submitted_results) {
        if (experimentData.student_submitted_results.gamma !== null) {
            studentGammaInput.value = experimentData.student_submitted_results.gamma;
        }
        if (experimentData.student_submitted_results.speed_of_sound !== null) {
            studentSpeedInput.value = experimentData.student_submitted_results.speed_of_sound;
        }
    }

    if (resultsStatus === 'success' || resultsStatus === 'final_completed') {
        console.log('[Form State] Эксперимент успешно завершен. Блокируем поля и кнопку.');
        studentGammaInput.disabled = true;
        studentSpeedInput.disabled = true;
        submitButton.disabled = true;
        submitButton.textContent = 'Результаты приняты';
        resultDisplay.innerHTML = `
            <div class="alert alert-success" role="alert">
                <strong>Успех!</strong> Ваши результаты приняты. <br>
                Гамма: ${experimentData.student_submitted_results?.gamma ?? 'N/A'}, Скорость: ${experimentData.student_submitted_results?.speed_of_sound ?? 'N/A'}. <br>
                Системная гамма: ${experimentData.system_calculated_results?.gamma?.toFixed(3) ?? 'N/A'}.
            </div>
        `;
    } else if (resultsStatus === 'fail') {
        console.log('[Form State] Эксперимент завершен со статусом "fail". Поля остаются активными. Показываем кнопку "Повторить".');
        studentGammaInput.disabled = false;
        studentSpeedInput.disabled = false;
        submitButton.disabled = false;
        submitButton.textContent = 'Отправить результаты'; // Возвращаем исходный текст кнопки
        // Показываем кнопку "Повторить попытку"
        if (retryButton && experimentData.experiment_id) {
            retryButton.style.display = 'inline-block'; // или 'block', в зависимости от верстки
            retryButton.onclick = () => {
                if (confirm('Вы уверены, что хотите сбросить текущую попытку и ввести данные заново?')) {
                    retryCurrentExperiment(experimentData.experiment_id);
                }
            };
        }
        // Отображаем сообщение об ошибке и детали сравнения, если есть
        let failMessage = "<strong>Ошибка!</strong> Ваши результаты не приняты.";
        if (experimentData.error_details) {
            if (experimentData.error_details.message) {
                failMessage += `<br>${experimentData.error_details.message}`;
            }
            if (experimentData.error_details.message_speed) {
                 failMessage += `<br>${experimentData.error_details.message_speed}`;
            }
        } else if (experimentData.system_calculated_results) {
            // Общее сообщение, если нет error_details, но есть системные значения для сравнения
            failMessage += `<br>Введенная гамма: ${studentGammaInput.value || 'N/A'}, системная: ${experimentData.system_calculated_results.gamma?.toFixed(3) ?? 'N/A'}.`;
             // Можно добавить аналогично для скорости
        }

        resultDisplay.innerHTML = `
            <div class="alert alert-danger" role="alert">
                ${failMessage} <br>
                Пожалуйста, проверьте ваши расчеты и попробуйте снова.
            </div>
        `;
    } else if (resultsStatus === 'pending_student_input' || resultsStatus === null || resultsStatus === undefined) {
        console.log('[Form State] Эксперимент ожидает ввода данных студентом. Поля активны.');
        studentGammaInput.disabled = false;
        studentSpeedInput.disabled = false;
        submitButton.disabled = false;
        submitButton.textContent = 'Отправить результаты';
        resultDisplay.innerHTML = '<div class="alert alert-info" role="alert">Введите рассчитанные значения и отправьте результаты.</div>';
    } else {
        console.log(`[Form State] Неизвестный статус обработки результатов: ${resultsStatus}. Поля активны по умолчанию.`);
        studentGammaInput.disabled = false;
        studentSpeedInput.disabled = false;
        submitButton.disabled = false;
        submitButton.textContent = 'Отправить результаты';
        resultDisplay.innerHTML = `
            <div class="alert alert-warning" role="alert">
                Не удалось определить статус обработки ваших результатов. Поля ввода активны.
            </div>
        `;
    }
}

async function submitResults(experimentId) {
    const studentGamma = document.getElementById('student_gamma').value;
    const studentSpeed = document.getElementById('student_speed').value;
    const submitButton = document.getElementById('submit_results_button');
    const resultDisplay = document.getElementById('result_display');

    // Простая валидация на клиенте
    if (!studentGamma || !studentSpeed) {
        resultDisplay.innerHTML = '<div class="alert alert-warning" role="alert">Пожалуйста, заполните оба поля.</div>';
        return;
    }
    if (isNaN(parseFloat(studentGamma)) || isNaN(parseFloat(studentSpeed))) {
        resultDisplay.innerHTML = '<div class="alert alert-warning" role="alert">Значения должны быть числами. Используйте точку в качестве десятичного разделителя.</div>';
        return;
    }

    submitButton.disabled = true;
    submitButton.textContent = 'Отправка...';
    resultDisplay.innerHTML = '<div class="alert alert-info" role="alert">Отправка результатов...</div>';

    try {
        const response = await fetch(`/lab_data/api/experiments/${experimentId}/save_results/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken()
            },
            body: JSON.stringify({
                student_gamma: parseFloat(studentGamma),
                student_speed: parseFloat(studentSpeed)
            })
        });

        const data = await response.json();
        console.log("Ответ от save_results:", data);

        if (response.ok && data.status === 'success') {
            // Обновляем состояние формы и отображение на основе ответа сервера
            // Мы ожидаем, что data будет содержать актуальные experimentData или хотя бы обновленные статусы
            // Для простоты, перезагрузим данные эксперимента целиком, чтобы UI обновился
            await loadExperimentData(experimentId); // Эта функция должна обновить все, включая updateFormState

            // Можно показать немедленное сообщение перед полной перезагрузкой данных
            let message = data.message || "Результаты обработаны.";
            if (data.results_status === 'success') {
                 resultDisplay.innerHTML = `<div class="alert alert-success" role="alert">${message} Статус: Успешно.</div>`;
            } else if (data.results_status === 'fail') {
                 resultDisplay.innerHTML = `<div class="alert alert-danger" role="alert">${message} Статус: Провал. ${data.comparison_message || ''}</div>`;
                 // Кнопка отправки будет разблокирована через loadExperimentData -> updateFormState
            } else {
                 resultDisplay.innerHTML = `<div class="alert alert-info" role="alert">${message}</div>`;
            }
        } else {
            // Ошибка на сервере или в логике ответа
            console.error("Ошибка при сохранении результатов:", data.message || response.statusText);
            resultDisplay.innerHTML = `<div class="alert alert-danger" role="alert">Ошибка при сохранении: ${data.message || 'Проверьте введенные данные или попробуйте позже.'}</div>`;
            submitButton.disabled = false; // Разблокируем кнопку, чтобы студент мог исправить
            submitButton.textContent = 'Отправить результаты';
        }
    } catch (error) {
        console.error('Сетевая ошибка или ошибка выполнения при отправке результатов:', error);
        resultDisplay.innerHTML = '<div class="alert alert-danger" role="alert">Сетевая ошибка при отправке результатов. Пожалуйста, проверьте ваше соединение.</div>';
        submitButton.disabled = false;
        submitButton.textContent = 'Отправить результаты';
    }
}

async function retryCurrentExperiment(experimentId) {
    console.log(`[Retry] Попытка сброса для эксперимента ${experimentId}`);
    const resultDisplay = document.getElementById('result_display');
    try {
        const response = await fetch(`/lab_data/experiments/${experimentId}/retry/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken()
            },
        });
        const data = await response.json(); // Предполагаем, что сервер вернет JSON

        if (response.ok && data.status === 'success') {
            console.log(`[Retry] Эксперимент ${experimentId} успешно сброшен.`);
            // alert(data.message || 'Попытка сброшена. Можете ввести данные заново.');
            // После успешного сброса, перезагружаем данные эксперимента,
            // чтобы обновить UI (поля должны очиститься или стать активными)
            loadExperimentData(experimentId);
        } else {
            console.error(`[Retry] Ошибка сброса эксперимента ${experimentId}:`, data.message || response.statusText);
            if (resultDisplay) {
                 resultDisplay.innerHTML = `<div class="alert alert-danger" role="alert">Не удалось сбросить попытку: ${data.message || 'Серверная ошибка.'}</div>`;
            } else {
                alert(`Не удалось сбросить попытку: ${data.message || 'Серверная ошибка.'}`);
            }
        }
    } catch (error) {
        console.error(`[Retry] Сетевая ошибка при сбросе эксперимента ${experimentId}:`, error);
        if (resultDisplay) {
            resultDisplay.innerHTML = '<div class="alert alert-danger" role="alert">Сетевая ошибка при сбросе попытки.</div>';
        } else {
            alert('Сетевая ошибка при сбросе попытки.');
        }
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const experimentDetailsDiv = document.getElementById('experiment_details');
    if (experimentDetailsDiv) {
        const experimentId = experimentDetailsDiv.dataset.experimentId;
        if (experimentId) {
            loadExperimentData(experimentId);
        } else {
            console.error('ID эксперимента не найден в data-атрибутах.');
            experimentDetailsDiv.innerHTML = '<div class="alert alert-danger">Ошибка: ID эксперимента не указан.</div>';
        }
    }

    const submitButton = document.getElementById('submit_results_button');
    if (submitButton) {
        submitButton.addEventListener('click', () => {
            const experimentId = document.getElementById('experiment_details').dataset.experimentId;
            if (experimentId) {
                submitResults(experimentId);
            } else {
                console.error('ID эксперимента не найден для отправки результатов.');
                document.getElementById('result_display').innerHTML = '<div class="alert alert-danger">Ошибка: ID эксперимента не определен для отправки.</div>';
            }
        });
    }
});