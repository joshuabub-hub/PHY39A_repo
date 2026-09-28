#include <math.h>

// Thermistor measurement is unchanged from Switch_Control/Fixed_Direction.
const int thermistorPin = A0;

// H-bridge pins, unchanged. This mapping was experimentally verified on the
// bench: driving pin 9 produces heating, driving pin 10 produces cooling.
// Only one of these two pins is ever driven at a time.
const int hBridgeHeatPwmPin = 9;
const int hBridgeCoolPwmPin = 10;

// There is no trim pot (A1) and no direction switch (pin 11) in this sketch.
// PWM and direction now come entirely from serial commands sent by the
// Python GUI, in the form:
//   SET PWM 120 DIR HEAT
//   SET PWM 45 DIR COOL
// Start at PWM 0 so nothing turns on until the Python GUI sends its first
// command (the GUI does this automatically as soon as it connects).
int currentPwm = 0;
bool currentDirectionIsHeat = false;  // false = cooling, matches the other sketches' default

const float supplyVoltage = 5.0;
const float fixedResistance = 100000.0;
const float nominalResistance = 100000.0;
const float nominalTemperatureC = 25.0;
const float betaCoefficient = 3950.0;
const int samplesPerMeasurement = 1000;

// Software over-temperature cutoff, independent of whatever the Python GUI
// commands: once the thermistor reads above cutoffTripTemperatureC, the
// H-bridge is forced off regardless of currentPwm/currentDirectionIsHeat,
// and stays off until the temperature drops below cutoffResetTemperatureC.
// The gap between trip/reset (hysteresis) stops the cutoff from chattering
// on and off right at the trip point.
const float cutoffTripTemperatureC = 60.0;
const float cutoffResetTemperatureC = 55.0;
bool cutoffActive = false;

void setup() {
  Serial.begin(9600);
  pinMode(hBridgeHeatPwmPin, OUTPUT);
  pinMode(hBridgeCoolPwmPin, OUTPUT);
}

void loop() {
  // Check for (and apply) a new command before every measurement, so the
  // H-bridge is always driven with the most recently received setting.
  readSerialCommand();

  float thermistorAdc = averageADCSamples(thermistorPin);
  float voltage = adcToVoltage(thermistorAdc);
  // Thermistor is connected to +5 V; the fixed resistor is connected to GND.
  float thermistorResistance = voltageToResistance(voltage);
  float temperatureC = resistanceToCelsius(thermistorResistance);

  updateCutoff(temperatureC);
  driveHBridge();

  printHumanReadable(temperatureC);

  delay(10);
}

// ---------------------------------------------------------------------
// Serial command parsing
// ---------------------------------------------------------------------
// Reads one line of text from the Arduino IDE / Python GUI, if one is
// waiting, and updates currentPwm / currentDirectionIsHeat from it.
//
// Expected format (case-sensitive, exactly one space between tokens):
//   SET PWM <integer> DIR HEAT
//   SET PWM <integer> DIR COOL
//
// Safety behavior: this function is deliberately conservative. Any line
// that doesn't match the expected format - a typo, a partial line, a stray
// newline, noise on the serial port - is ignored completely and leaves
// currentPwm / currentDirectionIsHeat exactly as they were. We never guess
// at a malformed command, and we never let a bad line turn a pin on.
void readSerialCommand() {
  if (Serial.available() <= 0) {
    return;  // nothing waiting, leave the current setting alone
  }

  String line = Serial.readStringUntil('\n');
  line.trim();  // drop the trailing '\r' (and any stray whitespace)
  if (line.length() == 0) {
    return;
  }

  int requestedPwm = 0;
  char directionWord[8];  // big enough for "HEAT"/"COOL" plus the null terminator

  // sscanf fills in requestedPwm and directionWord only if the whole line
  // matches this exact pattern; it returns how many of the two it managed
  // to fill in, so we can tell a full match from a partial/garbled one.
  int fieldsMatched = sscanf(line.c_str(), "SET PWM %d DIR %7s", &requestedPwm, directionWord);
  if (fieldsMatched != 2) {
    return;  // line didn't look like "SET PWM <n> DIR <word>" - ignore it
  }

  // Safety clamp: no matter what number was requested, never send the
  // H-bridge a PWM value outside the valid 0-255 range.
  currentPwm = constrain(requestedPwm, 0, 255);

  if (strcmp(directionWord, "HEAT") == 0) {
    currentDirectionIsHeat = true;
  } else if (strcmp(directionWord, "COOL") == 0) {
    currentDirectionIsHeat = false;
  }
  // Any other direction word (a typo, etc.) is ignored: the PWM value above
  // still gets applied, but the direction keeps its last known-good state
  // rather than us guessing which pin to drive.
}

// ---------------------------------------------------------------------
// Over-temperature cutoff
// ---------------------------------------------------------------------
// Latching, hysteretic trip: once tripped by crossing the trip temperature,
// stays tripped until the temperature falls below the (lower) reset
// temperature, so driveHBridge() can force the outputs off for the whole
// time the system is too hot, not just on the single sample that tripped it.
void updateCutoff(float temperatureC) {
  if (!cutoffActive && temperatureC > cutoffTripTemperatureC) {
    cutoffActive = true;
  } else if (cutoffActive && temperatureC < cutoffResetTemperatureC) {
    cutoffActive = false;
  }
}

// ---------------------------------------------------------------------
// H-bridge output
// ---------------------------------------------------------------------
// Only the active pin (chosen by currentDirectionIsHeat) ever receives a
// nonzero PWM value; the other pin is always explicitly held at 0. This is
// the same one-pin-at-a-time safety behavior as Switch_Control/
// Fixed_Direction, so heating and cooling can never be driven at once.
// This is open-loop: whatever PWM/direction was last commanded is applied
// directly, with no feedback from the measured temperature, except for the
// over-temperature cutoff above which always wins and forces both pins off.
void driveHBridge() {
  int activePwmPin = currentDirectionIsHeat ? hBridgeHeatPwmPin : hBridgeCoolPwmPin;
  int inactivePwmPin = currentDirectionIsHeat ? hBridgeCoolPwmPin : hBridgeHeatPwmPin;
  int commandedPwm = cutoffActive ? 0 : currentPwm;

  analogWrite(activePwmPin, commandedPwm);
  analogWrite(inactivePwmPin, 0);
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

void printHumanReadable(float temperatureC) {
  // Heat/Cool here reflects the direction we are actually driving right
  // now (1 = observed heating, 0 = observed cooling) - it mirrors
  // currentDirectionIsHeat, the same value driveHBridge() just used to pick
  // the active pin, not merely the last command's wording.
  int heatCool = currentDirectionIsHeat ? 1 : 0;

  Serial.print("Temperature (C): ");
  Serial.print(temperatureC, 2);
  Serial.print(", Time (s): ");
  Serial.print(millis() / 1000.0, 2);
  Serial.print(", PWM: ");
  Serial.print(cutoffActive ? 0 : currentPwm);
  Serial.print(", Heat/Cool: ");
  Serial.print(heatCool);
  Serial.print(", Cutoff: ");
  Serial.println(cutoffActive ? 1 : 0);
}
