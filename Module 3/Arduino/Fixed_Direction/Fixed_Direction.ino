#include <math.h>

const int thermistorPin = A0;
const int trimPotPin = A1;
const int hBridgeHeatPwmPin = 9;
const int hBridgeCoolPwmPin = 10;

// Fixed direction: only one H-bridge pin is ever driven. Swap which pin is
// "active" here to switch the sketch between heating and cooling.
const int activePwmPin = hBridgeCoolPwmPin;
const int inactivePwmPin = hBridgeHeatPwmPin;

const float supplyVoltage = 5.0;
const float fixedResistance = 100000.0;
const float nominalResistance = 100000.0;
const float nominalTemperatureC = 25.0;
const float betaCoefficient = 3950.0;
const int samplesPerMeasurement = 1000;

void setup() {
  Serial.begin(9600);
  pinMode(hBridgeHeatPwmPin, OUTPUT);
  pinMode(hBridgeCoolPwmPin, OUTPUT);
}

void loop() {
  float thermistorAdc = averageADCSamples(thermistorPin);
  float voltage = adcToVoltage(thermistorAdc);
  // Thermistor is connected to +5 V; the fixed resistor is connected to GND.
  float thermistorResistance = voltageToResistance(voltage);
  float temperatureC = resistanceToCelsius(thermistorResistance);

  float trimPotAdc = averageADCSamples(trimPotPin);
  int pwm = trimPotAdcToPwm(trimPotAdc);

  analogWrite(activePwmPin, pwm);
  analogWrite(inactivePwmPin, 0);

  printHumanReadable(temperatureC, pwm);

  delay(10);
}

float averageADCSamples(int pin) {
  unsigned long adcSum = 0;

  for (int sample = 0; sample < samplesPerMeasurement; sample++) {
    adcSum += analogRead(pin);
  }

  float averageAdc = adcSum / (float)samplesPerMeasurement;
  return averageAdc;
}

float adcToVoltage(float aveADC) {
  float voltage = aveADC * (supplyVoltage / 1023.0);
  return voltage;
}

float voltageToResistance(float voltage) {
  float thermistorResistance = fixedResistance * voltage / (supplyVoltage - voltage);
  return thermistorResistance;
}

float resistanceToCelsius(float thermistorResistance) {
  float temperatureK = 1.0 / (1.0 / (nominalTemperatureC + 273.15)
                              + log(thermistorResistance / nominalResistance) / betaCoefficient);
  float temperatureC = temperatureK - 273.15;
  return temperatureC;
}

int trimPotAdcToPwm(float aveADC) {
  int pwm = round(aveADC * (255.0 / 1023.0));
  return pwm;
}

void printHumanReadable(float temperatureC, int pwm) {
  Serial.print("Temperature (C): ");
  Serial.print(temperatureC, 2);
  Serial.print(", Time (s): ");
  Serial.print(millis() / 1000.0, 2);
  Serial.print(", PWM: ");
  Serial.print(pwm);
  Serial.print(", Active PWM pin: ");
  Serial.println(activePwmPin);
}
