float sum = 0;
float sumSqares = 0;
double Vavg = 0;
void setup() {
  Serial.begin(9600);

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
    /*Serial.print("V Sequential:");
    Serial.print(Vactual);
    Serial.print("  count:");
    Serial.println(i);*/
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
  while (j < 100) {
    k = 0;
    micros();
    while (k < 1000) {
      double sensorValue = analogRead(A0);
      Vavg = (Vavg + sensorValue);
      k = k + 1;
    }
    Vavg = (Vavg / 1000);
    sum += Vavg;
    sumSqares += Vavg * Vavg;
    micros();
    /*Serial.print("V average:");
    Serial.print(Vavg);
    Serial.print("  count:");
    Serial.println(j);*/
    j = j + 1;
  }
  mean = sum / 100;
  var = abs((sumSqares / 100) - (mean * mean));
  dev = sqrt(var);    
  Serial.print("mean (ave): ");
  Serial.println(mean);
  Serial.print("Sdev (ave): ");
  Serial.println(dev);
  delay(10000);
}
//nmax = 1023
//nmid = 511.5
