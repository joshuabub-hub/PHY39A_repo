float sum = 0;
float sumSqares = 0;
double Vavg = 0;
const int ledPin = 9;
const float Vref = 5.0;
void setup() {
  Serial.begin(9600);
  pinMode(ledPin, OUTPUT);
}

void loop() {
  int i = 0;
  int j = 0;
  int k = 0;
  sum = 0;
  sumSqares = 0;
  //Serial.println(sensorValue);
  while (i < 100) {
    double sensorValue = analogRead(A0);
    double Vactual = sensorValue;
    sum += sensorValue;
    sumSqares += sensorValue * sensorValue;
    Serial.print("V Sequential:");
    Serial.print(Vactual);
    Serial.print("  count:");
    Serial.println(i);
    i = i + 1;
  }
  float mean = sum / 100;
    float var = abs((sumSqares / 100) - (mean * mean));
    float dev = sqrt(var);
    Serial.print("mean (seq): ");
    Serial.println(mean);
    Serial.print("Sdev (seq): ");
    Serial.println(dev);
  delay(100);
  sum = 0;
  sumSqares = 0;
  unsigned long totalAvgTime = 0;
  while (j < 100) {
    k = 0;
    unsigned long startTime = micros();
    while (k < 1000) {
      double sensorValue = analogRead(A0);
      Vavg = (Vavg + sensorValue);
      k = k + 1;
    }
    unsigned long endTime = micros();
    totalAvgTime += (endTime - startTime);
    Vavg = (Vavg / 1000);
    sum += Vavg;
    sumSqares += Vavg * Vavg;
    Serial.print("V average:");
    Serial.print(Vavg);
    Serial.print("  count:");
    Serial.println(j);
    j = j + 1;
  }
  mean = sum / 100;
  var = abs((sumSqares / 100) - (mean * mean));
  dev = sqrt(var);
  Serial.print("mean (ave): ");
  Serial.println(mean);
  Serial.print("Sdev (ave): ");
  Serial.println(dev);
  double avgTimeUs = totalAvgTime / 100.0;
  double conversionsPerSecond = 1000.0 / (avgTimeUs * 1.0e-6);
  Serial.print("avg time per 1000-sample average (us): ");
  Serial.println(avgTimeUs);
  Serial.print("analogRead() conversions per second: ");
  Serial.println(conversionsPerSecond);

  float voltage = mean * (Vref / 1023.0);
  int pwmValue = (int)(voltage / Vref * 255.0);
  pwmValue = constrain(pwmValue, 0, 255);
  analogWrite(ledPin, pwmValue);
  Serial.print("Voltage (ave): ");
  Serial.println(voltage);
  Serial.print("PWM value: ");
  Serial.println(pwmValue);

  delay(10000);
}
//nmax = 1023
//nmid = 511.5
