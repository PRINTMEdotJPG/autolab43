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