/**
 * Основной модуль управления экспериментом
 */
class ExperimentCore {
    constructor() {
      this.currentExperimentId = null;
      this.currentStudentId = null;
      this.equipmentConnected = false;
      this.isRecording = false;
      this.experimentData = {
        parameters: {},
        measurements: [],
        results: {}
      };
  
      this.init();
    }
  
    init() {
      this.initDOMReferences();
      this.initEventListeners();
      this.checkEquipmentSupport();
    }
  
    initDOMReferences() {
      this.dom = {
        startBtn: document.getElementById('startExperiment'),
        studentSelect: document.getElementById('studentSelect'),
        equipmentStatus: document.getElementById('equipmentStatus'),
        recordBtn: document.getElementById('recordBtn'),
        paramsForm: document.getElementById('paramsForm')
      };
    }
  
    initEventListeners() {
      if (this.dom.startBtn) {
        this.dom.startBtn.addEventListener('click', () => this.startExperiment());
      }
  
      if (this.dom.recordBtn) {
        this.dom.recordBtn.addEventListener('click', () => this.toggleRecording());
      }
  
      if (this.dom.paramsForm) {
        this.dom.paramsForm.addEventListener('submit', (e) => {
          e.preventDefault();
          this.saveParameters();
        });
      }
    }
  
    async startExperiment() {
      if (!this.currentStudentId) {
        this.showAlert('Выберите студента!', 'error');
        return;
      }
  
      try {
        const response = await this.apiCall('/api/start-experiment/', {
          student_id: this.currentStudentId
        });
  
        if (response.status === 'success') {
          this.currentExperimentId = response.experiment_id;
          this.showExperimentUI();
          this.connectToEquipment();
        }
      } catch (error) {
        this.showAlert(`Ошибка: ${error.message}`, 'error');
      }
    }
  
    async connectToEquipment() {
      try {
        if (window.SerialPort) {
          this.port = await navigator.serial.requestPort();
          await this.port.open({ baudRate: 9600 });
          this.equipmentConnected = true;
          this.updateEquipmentStatus();
          this.startReadingData();
        } else {
          this.useSimulation();
        }
      } catch (error) {
        this.showAlert(`Ошибка подключения: ${error.message}`, 'error');
      }
    }
  
    async startReadingData() {
      const reader = this.port.readable.getReader();
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        this.processEquipmentData(value);
      }
    }
  
    processEquipmentData(data) {
      try {
        const parsed = JSON.parse(data);
        this.experimentData.measurements.push(parsed);
        this.updateLiveData(parsed);
      } catch (e) {
        console.error('Ошибка обработки данных:', e);
      }
    }
  
    toggleRecording() {
      this.isRecording = !this.isRecording;
      if (this.isRecording) {
        this.experimentData.measurements = [];
        this.dom.recordBtn.textContent = 'Стоп';
      } else {
        this.saveMeasurements();
        this.dom.recordBtn.textContent = 'Запись';
      }
    }
  
    async saveMeasurements() {
      try {
        await this.apiCall(`/api/save-data/${this.currentExperimentId}/`, {
          measurements: this.experimentData.measurements
        });
        this.showAlert('Данные сохранены!', 'success');
      } catch (error) {
        this.showAlert(`Ошибка сохранения: ${error.message}`, 'error');
      }
    }
  
    async saveParameters() {
      const params = {
        temperature: parseFloat(document.getElementById('temperature').value),
        frequency: parseFloat(document.getElementById('frequency').value)
      };
  
      try {
        await this.apiCall(`/api/save-params/${this.currentExperimentId}/`, params);
        this.experimentData.parameters = params;
        this.showAlert('Параметры сохранены!', 'success');
      } catch (error) {
        this.showAlert(`Ошибка сохранения: ${error.message}`, 'error');
      }
    }
  
    async apiCall(url, data) {
      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': this.getCSRFToken()
        },
        body: JSON.stringify(data)
      });
      return await response.json();
    }
  
    getCSRFToken() {
      return document.querySelector('[name=csrfmiddlewaretoken]').value;
    }
  
    updateEquipmentStatus() {
      if (this.dom.equipmentStatus) {
        this.dom.equipmentStatus.innerHTML = `
          <div class="alert ${this.equipmentConnected ? 'alert-success' : 'alert-danger'}">
            Оборудование: ${this.equipmentConnected ? 'Подключено' : 'Отключено'}
          </div>
        `;
      }
    }
  
    showAlert(message, type) {
      const alert = document.createElement('div');
      alert.className = `alert alert-${type}`;
      alert.textContent = message;
      document.getElementById('alertsContainer').appendChild(alert);
      setTimeout(() => alert.remove(), 3000);
    }
  
    useSimulation() {
      console.log('Using simulated data');
      this.equipmentConnected = true;
      this.updateEquipmentStatus();
      // Здесь можно добавить логику симуляции данных
    }
  }
  
  // Инициализация только для лаборантов
  if (document.getElementById('experimentApp')) {
    window.experimentCore = new ExperimentCore();
  }