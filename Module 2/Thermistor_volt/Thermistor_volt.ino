#include <math.h>

const int thermistorPin = A0;
const float supplyVoltage = 5.0;
const float fixedResistance = 100000.0;
const float nominalResistance = 100000.0;
const float nominalTemperatureC = 25.0;
const float betaCoefficient = 3950.0;
const int samplesPerMeasurement = 1000;

void setup() {
  Serial.begin(9600);
}

void loop() {
  float aveADC = averageADCSamples();
  
  float voltage = adcToVoltage(aveADC);

  // Thermistor is connected to +5 V; the fixed resistor is connected to GND.
  float thermistorResistance = voltageToResistance(voltage);
  float temperatureC = resistanceToCelcius(thermistorResistance);

  printHumanReadable(aveADC, voltage, thermistorResistance, temperatureC);
  //Serial.println(temperatureC);
  delay(10);
}

float averageADCSamples() {
  unsigned long adcSum = 0;

  for (int sample = 0; sample < samplesPerMeasurement; sample++) {
    adcSum += analogRead(thermistorPin);
  }

  float averageAdc = adcSum / (float)samplesPerMeasurement;
  return averageAdc;
}

float adcToVoltage(float aveADC) {
  float voltage = aveADC * (supplyVoltage / 1023.0);
  return voltage;
}

float voltageToResistance(float voltage){
  float thermistorResistance = fixedResistance * voltage / (supplyVoltage - voltage);
  return thermistorResistance;
}

float resistanceToCelcius(float thermistorResistance){
  float temperatureK = 1.0 / (1.0 / (nominalTemperatureC + 273.15)
                              + log(thermistorResistance / nominalResistance) / betaCoefficient);
  float temperatureC = temperatureK - 273.15;
  return temperatureC;
}

void printHumanReadable(float aveADC, float voltage, float thermistorResistance, float temperatureC){
  Serial.print("time = ");
  Serial.print(millis() / 1000.0, 2);
  Serial.print(" s    average ADC = ");
  Serial.print(aveADC, 1);
  Serial.print("    voltage = ");
  Serial.print(voltage, 3);
  Serial.print(" V    resistance = ");
  Serial.print(thermistorResistance / 1000.0, 2);
  Serial.print(" kOhm    temperature = ");
  Serial.print(temperatureC, 1);
  Serial.print(" C    samples = ");
  Serial.println(samplesPerMeasurement);
}