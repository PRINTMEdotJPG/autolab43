/**
 * Модуль работы с оборудованием
 */
class EquipmentManager {
    constructor(core) {
      this.core = core;
      this.port = null;
      this.reader = null;
    }
  
    async connect() {
      try {
        this.port = await navigator.serial.requestPort();
        await this.port.open({ baudRate: 9600 });
        this.core.equipmentConnected = true;
        this.core.updateEquipmentStatus();
        this.startReading();
      } catch (error) {
        console.error('Ошибка подключения:', error);
        this.core.useSimulation();
      }
    }
  
    async startReading() {
      this.reader = this.port.readable.getReader();
      while (true) {
        try {
          const { value, done } = await this.reader.read();
          if (done) break;
          this.core.processEquipmentData(value);
        } catch (error) {
          console.error('Ошибка чтения:', error);
          break;
        }
      }
    }
  
    async disconnect() {
      if (this.reader) {
        await this.reader.cancel();
        this.reader = null;
      }
      if (this.port) {
        await this.port.close();
        this.port = null;
      }
      this.core.equipmentConnected = false;
      this.core.updateEquipmentStatus();
    }
  }