/*
 * Скетч для измерения расстояния с помощью ультразвукового датчика HC-SR04
 * и отправки данных через Serial-порт в формате "distance:XX.XX"
 */

// Пины для подключения датчика HC-SR04
const int trigPin = 9;  // Пин подключения вывода TRIG
const int echoPin = 10; // Пин подключения вывода ECHO

// Переменные для временных засечек
long duration;
float distanceMm;

void setup() {
  // Инициализация Serial-порта
  Serial.begin(9600);
  
  // Настройка пинов
  pinMode(trigPin, OUTPUT);
  pinMode(echoPin, INPUT);
  
  // Начальное состояние для TRIG - LOW
  digitalWrite(trigPin, LOW);
  
  // Небольшая задержка для стабилизации датчика
  delay(500);
  
  Serial.println("Датчик расстояния HC-SR04 инициализирован");
}

void loop() {
  // Измеряем расстояние
  distanceMm = measureDistance();
  
  // Отправляем данные через Serial в формате "distance:XX.XX"
  Serial.print("distance:");
  Serial.println(distanceMm);
  
  // Задержка между измерениями (50 мс = 20 измерений в секунду)
  delay(50);
}

float measureDistance() {
  // Очищаем состояние TRIG
  digitalWrite(trigPin, LOW);
  delayMicroseconds(2);
  
  // Отправляем импульс 10 мкс
  digitalWrite(trigPin, HIGH);
  delayMicroseconds(10);
  digitalWrite(trigPin, LOW);
  
  // Читаем длительность импульса от ECHO
  duration = pulseIn(echoPin, HIGH);
  
  // Вычисляем расстояние в миллиметрах
  // Скорость звука = 343 м/с = 0.343 мм/мкс
  // Время делим на 2, так как сигнал идет туда и обратно
  float distanceMm = duration * 0.343 / 2.0;
  
  // Ограничиваем диапазон измерений 0-600 мм (0-60 см)
  if (distanceMm > 600.0) {
    distanceMm = 600.0;
  }
  if (distanceMm < 0.0) {
    distanceMm = 0.0;
  }
  
  return distanceMm;
} 