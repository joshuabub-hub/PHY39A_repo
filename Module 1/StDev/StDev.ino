void setup() {
  Serial.begin(9600);

}

void loop() {
  float sum = 0;
  float sumSqares = 0;
    for (int i = 0; i < 100; i++){
      float x = analogRead(A0);
      sum += x;
      sumSqares += x * x;
      delay(1);
    }
    float mean = sum / 100;
    float var = abs((sumSqares / 100) - (mean * mean));
    float dev = sqrt(var);
    Serial.print("mean: ");
    Serial.println(mean);
    Serial.print("Sdev: ");
    Serial.println(dev);
    delay(100);
}
