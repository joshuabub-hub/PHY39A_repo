#include <math.h>

// Six thermistors, all wired and converted the same way as the original
// single thermistor. A0 is the TEC-base thermistor: it is the ONLY channel
// used for the over-temperature cutoff and the sensor-fault check below, and
// it is the temperature the Python GUI's PI controller uses for feedback.
// A1-A5 are rod thermistors 1-5; they are measured and reported only.
const int tecThermistorPin = A0;
const int rodThermistorPins[] = {A1, A2, A3, A4, A5};
const int rodThermistorCount = 5;

// H-bridge pins, unchanged. This mapping was experimentally verified on the
// bench: driving pin 9 produces heating, driving pin 10 produces cooling.
// Only one of these two pins is ever driven at a time.
const int hBridgeHeatPwmPin = 9;
const int hBridgeCoolPwmPin = 10;

// There is no trim pot and no direction switch (pin 11) in this sketch.
// PWM and direction come entirely from serial commands sent by the Python
// GUI (which also runs the PI controller), in the form:
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

// The divider's source impedance (~50 kOhm) is well above the ~10 kOhm the
// ADC's sample capacitor wants, so right after switching channels the first
// readings are pulled toward the previous channel's voltage. These readings
// are thrown away before averaging so the channels don't bleed into each other.
const int settlingReadsPerChannel = 5;

// Software over-temperature cutoff, independent of whatever the Python GUI
// commands: once the TEC-base thermistor reads above cutoffTripTemperatureC,
// the H-bridge is forced off regardless of currentPwm/currentDirectionIsHeat,
// and stays off until the temperature drops below cutoffResetTemperatureC.
// The gap between trip/reset (hysteresis) stops the cutoff from chattering
// on and off right at the trip point. Rod thermistors never affect this.
const float cutoffTripTemperatureC = 60.0;
const float cutoffResetTemperatureC = 55.0;
bool cutoffActive = false;

// Sensor-fault check on the TEC-base thermistor: an open or shorted divider
// pins the averaged ADC reading at (or very near) one of the rails, and the
// resulting "temperature" (around -273 C) would never trip the cutoff above.
// While the TEC reading is outside this window, the H-bridge is forced off
// and the TEC temperature is reported as nan. A rod channel outside the
// window is just reported as nan.
const float minValidAdc = 10.0;
const float maxValidAdc = 1013.0;
bool tecSensorFault = false;

// Every measurement record starts with this tag, and nothing else this
// sketch prints may start with it, so Python and the serial microSD logger
// can pick out records without being confused by diagnostic text. The header
// below is printed once at startup; every later DATA line is one measurement.
// setpoint_C is always nan: the setpoint lives in the Python GUI, which logs
// it in its own CSV. The column is kept so the record layout stays fixed.
const char recordHeader[] =
    "DATA,time_s,tec_C,rod1_C,rod2_C,rod3_C,rod4_C,rod5_C,pwm,heat_cool,setpoint_C,safety";

void setup() {
  Serial.begin(9600);
  pinMode(hBridgeHeatPwmPin, OUTPUT);
  pinMode(hBridgeCoolPwmPin, OUTPUT);
  analogWrite(hBridgeHeatPwmPin, 0);
  analogWrite(hBridgeCoolPwmPin, 0);

  Serial.println(recordHeader);
}

void loop() {
  // One acquisition cycle = one DATA record. Commands are checked between
  // every channel (about every 110 ms, the same rate as the old one-channel
  // loop), so a GUI command takes effect just as quickly as before even
  // though a full six-channel cycle now takes about 0.7 s.
  serviceCommands();

  float timeS = millis() / 1000.0;

  // TEC-base thermistor first: it drives the safety logic, and the H-bridge
  // is updated as soon as it is read.
  float tecAdc = averageADCSamples(tecThermistorPin);
  tecSensorFault = !adcIsValid(tecAdc);
  float tecTemperatureC = tecSensorFault ? NAN : adcToCelsius(tecAdc);
  if (!tecSensorFault) {
    updateCutoff(tecTemperatureC);
  }
  driveHBridge();

  float rodTemperaturesC[rodThermistorCount];
  for (int rod = 0; rod < rodThermistorCount; rod++) {
    serviceCommands();
    float rodAdc = averageADCSamples(rodThermistorPins[rod]);
    rodTemperaturesC[rod] = adcIsValid(rodAdc) ? adcToCelsius(rodAdc) : NAN;
  }

  serviceCommands();
  printDataRecord(timeS, tecTemperatureC, rodTemperaturesC);

  delay(10);
}

// Apply any commands that arrived, then drive the H-bridge with the result.
void serviceCommands() {
  readSerialCommands();
  driveHBridge();
}

// ---------------------------------------------------------------------
// Serial command parsing
// ---------------------------------------------------------------------
// Reads every complete line of text waiting from the Arduino IDE / Python
// GUI and updates currentPwm / currentDirectionIsHeat from each in turn, so
// the most recent command wins and no backlog builds up between cycles.
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
void readSerialCommands() {
  while (Serial.available() > 0) {
    String line = Serial.readStringUntil('\n');
    line.trim();  // drop the trailing '\r' (and any stray whitespace)
    if (line.length() == 0) {
      continue;
    }

    int requestedPwm = 0;
    char directionWord[8];  // big enough for "HEAT"/"COOL" plus the null terminator

    // sscanf fills in requestedPwm and directionWord only if the whole line
    // matches this exact pattern; it returns how many of the two it managed
    // to fill in, so we can tell a full match from a partial/garbled one.
    int fieldsMatched = sscanf(line.c_str(), "SET PWM %d DIR %7s", &requestedPwm, directionWord);
    if (fieldsMatched != 2) {
      continue;  // line didn't look like "SET PWM <n> DIR <word>" - ignore it
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
}

// ---------------------------------------------------------------------
// Over-temperature cutoff
// ---------------------------------------------------------------------
// Latching, hysteretic trip: once tripped by crossing the trip temperature,
// stays tripped until the temperature falls below the (lower) reset
// temperature, so driveHBridge() can force the outputs off for the whole
// time the system is too hot, not just on the single sample that tripped it.
// Only ever called with the TEC-base temperature, and only when that sensor
// reads valid, so a fault holds the cutoff in whatever state it was in.
void updateCutoff(float temperatureC) {
  if (!cutoffActive && temperatureC > cutoffTripTemperatureC) {
    cutoffActive = true;
  } else if (cutoffActive && temperatureC < cutoffResetTemperatureC) {
    cutoffActive = false;
  }
}

bool outputForcedOff() {
  return cutoffActive || tecSensorFault;
}

// ---------------------------------------------------------------------
// H-bridge output
// ---------------------------------------------------------------------
// Only the active pin (chosen by currentDirectionIsHeat) ever receives a
// nonzero PWM value; the other pin is always explicitly held at 0. This is
// the same one-pin-at-a-time safety behavior as Switch_Control/
// Fixed_Direction, so heating and cooling can never be driven at once.
// Whatever PWM/direction was last commanded is applied directly (the PI
// feedback happens in the Python GUI), except that the over-temperature
// cutoff and the TEC sensor fault always win and force both pins off.
void driveHBridge() {
  int activePwmPin = currentDirectionIsHeat ? hBridgeHeatPwmPin : hBridgeCoolPwmPin;
  int inactivePwmPin = currentDirectionIsHeat ? hBridgeCoolPwmPin : hBridgeHeatPwmPin;
  int commandedPwm = outputForcedOff() ? 0 : currentPwm;

  analogWrite(activePwmPin, commandedPwm);
  analogWrite(inactivePwmPin, 0);
}

// ---------------------------------------------------------------------
// Thermistor measurement (identical conversion for all six channels)
// ---------------------------------------------------------------------
float averageADCSamples(int pin) {
  for (int read = 0; read < settlingReadsPerChannel; read++) {
    analogRead(pin);
  }

  unsigned long adcSum = 0;

  for (int sample = 0; sample < samplesPerMeasurement; sample++) {
    adcSum += analogRead(pin);
  }

  float averageAdc = adcSum / (float)samplesPerMeasurement;
  return averageAdc;
}

bool adcIsValid(float aveADC) {
  return aveADC >= minValidAdc && aveADC <= maxValidAdc;
}

float adcToCelsius(float aveADC) {
  float voltage = adcToVoltage(aveADC);
  // Thermistor is connected to +5 V; the fixed resistor is connected to GND.
  float thermistorResistance = voltageToResistance(voltage);
  return resistanceToCelsius(thermistorResistance);
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

// ---------------------------------------------------------------------
// Measurement record
// ---------------------------------------------------------------------
// One line per acquisition cycle, fields in the order of recordHeader:
//   time_s      Arduino time at the start of the cycle (s)
//   tec_C       TEC-base temperature (nan while the sensor is faulted)
//   rodN_C      rod thermistor N temperature (nan if that channel is faulted)
//   pwm         PWM actually being driven right now (0 when forced off)
//   heat_cool   direction actually selected (1 = heating, 0 = cooling); it
//               mirrors currentDirectionIsHeat, the same value driveHBridge()
//               uses to pick the active pin, not merely the last command's wording
//   setpoint_C  always nan (the setpoint lives in the Python GUI)
//   safety      OK, CUTOFF (over-temperature), or SENSOR_FAULT (TEC sensor)
void printTemperatureField(float temperatureC) {
  Serial.print(',');
  if (isnan(temperatureC)) {
    Serial.print("nan");
  } else {
    Serial.print(temperatureC, 2);
  }
}

void printDataRecord(float timeS, float tecTemperatureC, const float rodTemperaturesC[]) {
  const char *safety = "OK";
  if (tecSensorFault) {
    safety = "SENSOR_FAULT";
  } else if (cutoffActive) {
    safety = "CUTOFF";
  }

  Serial.print("DATA,");
  Serial.print(timeS, 2);
  printTemperatureField(tecTemperatureC);
  for (int rod = 0; rod < rodThermistorCount; rod++) {
    printTemperatureField(rodTemperaturesC[rod]);
  }
  Serial.print(',');
  Serial.print(outputForcedOff() ? 0 : currentPwm);
  Serial.print(',');
  Serial.print(currentDirectionIsHeat ? 1 : 0);
  Serial.print(",nan,");
  Serial.println(safety);
}
