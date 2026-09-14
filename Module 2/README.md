# Module 2

This folder contains the Arduino sketches for Module 2 of PHY39A. The sketches
use averaged analog measurements to control an H-bridge and to estimate
temperature from an NTC thermistor.

## Project Files

### Arduino sketches

- [hbridge/hbridge.ino](hbridge/hbridge.ino): Reads a trim potentiometer on
  analog pin A1, averages 1,000 ADC samples, and uses the result to control
  heating or cooling through two PWM outputs.
- [Thermistor_volt/Thermistor_volt.ino](Thermistor_volt/Thermistor_volt.ino):
  Reads a thermistor voltage on analog pin A0, averages 1,000 ADC samples,
  converts the measurement to resistance, and estimates temperature with the
  beta-parameter equation.

## hbridge

### Connections

The sketch assumes the following connections:

| Signal | Arduino pin |
| --- | --- |
| Trim potentiometer wiper | A1 |
| H-bridge heating PWM input | 9 |
| H-bridge cooling PWM input | 10 |

The potentiometer reading is compared with the midpoint ADC value, 512. Values
above the midpoint produce heating PWM, while values below the midpoint produce
cooling PWM. At the midpoint both outputs are set to zero. The active output is
mapped from 0 to 255, the Arduino PWM range; the two outputs are never driven
simultaneously by this control logic.

The Serial Monitor should be set to 9600 baud. Each update reports the averaged
ADC value, the midpoint, and the heating and cooling PWM values.

## Thermistor voltage measurement

### Connections and component values

The sketch assumes a voltage divider with the thermistor connected to `+5 V`,
the fixed resistor connected to `GND`, and the divider output connected to A0.
The code uses these nominal values:

- Supply voltage: 5.0 V
- Fixed resistor: 100 kOhm
- Thermistor resistance at the nominal temperature: 100 kOhm
- Nominal temperature: 25 C
- Beta coefficient: 3950 K
- Analog samples per measurement: 1,000

The measurement is converted in three steps:

1. The averaged 10-bit ADC reading is converted to voltage using
	`voltage = ADC * 5.0 / 1023.0`.
2. The divider voltage is converted to thermistor resistance using
	`R_thermistor = R_fixed * voltage / (5.0 - voltage)`.
3. The resistance is converted to temperature using the beta equation:

	`1 / T = 1 / T_nominal + ln(R / R_nominal) / beta`

	where temperatures in the equation are in kelvin. The result is printed in
	degrees Celsius.

The Serial Monitor should be set to 9600 baud. Each update reports elapsed time,
average ADC value, voltage, thermistor resistance in kOhm, estimated temperature
in C, and the number of samples used.

## Sampling behavior

Both sketches take 1,000 consecutive analog readings and average them before
using the result. This reduces the effect of short-term measurement variation,
but it also means that each update takes longer than a single `analogRead()`.
After each update, the sketches wait 10 ms before starting the next measurement.
