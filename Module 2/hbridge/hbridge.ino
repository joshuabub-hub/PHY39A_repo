const int trimPotPin = A1;
const int hBridgeHeatPwmPin = 9;
const int hBridgeCoolPwmPin = 10;
const int samplesPerMeasurement = 1000;
const int controlMidpoint = 512;

void setup() {
  Serial.begin(9600);
  pinMode(hBridgeHeatPwmPin, OUTPUT);
  pinMode(hBridgeCoolPwmPin, OUTPUT);
}

void loop() {
  unsigned long adcSum = 0;

  for (int sample = 0; sample < samplesPerMeasurement; sample++) {
    adcSum += analogRead(trimPotPin);
  }

  int averageAdc = adcSum / samplesPerMeasurement;
  int heatPwm = 0;
  int coolPwm = 0;

  if (averageAdc > controlMidpoint) {
    heatPwm = map(averageAdc, controlMidpoint, 1023, 0, 255);
  } else if (averageAdc < controlMidpoint) {
    coolPwm = map(averageAdc, 0, controlMidpoint, 255, 0);
  }

  analogWrite(hBridgeHeatPwmPin, heatPwm);
  analogWrite(hBridgeCoolPwmPin, coolPwm);

  Serial.print("trim-pot average ADC = ");
  Serial.print(averageAdc);
  Serial.print("    midpoint = ");
  Serial.print(controlMidpoint);
  Serial.print("    heat PWM (pin 9) = ");
  Serial.print(heatPwm);
  Serial.print(" / 255    cool PWM (pin 10) = ");
  Serial.print(coolPwm);
  Serial.println(" / 255");

  delay(10);
}
