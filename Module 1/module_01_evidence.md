## A1 Evidence

## Team Members

- Josh Bub
- Eli Spielman

## Date

09/02/2026

## URL

https://github.com/joshuabub-hub/PHY39A_repo.git

## Apparatus

![Apparatus](Images/Apparatus.jpeg)

## Arduino Sketches

- [Blink.ino](Blink/Blink.ino)
- [AnalogReadSerial1.ino](AnalogReadSerial1/AnalogReadSerial1.ino)
- [Seq_Avg_volt_1.ino](Seq_Avg_volt_1/Seq_Avg_volt_1.ino)
  - Seq_Avg_volt_1 contains the code for parts 3B-4

## ADC Digitization Results

The results from the ADC digitization of our input voltage include a maximum ADC reading of 1,023, a minimum of 0, and a mid-point of ~511. Because our input voltage was 5 volts, the ADC readings have a resolution of about 5 millivolts. This resolution discribes the discrete levels the ADC reading allows (steps of ~5 millivolts). Because the Arduino uses a digital chip, it can only approximate the continuous voltage changes the chip recieves as input.

## Transition Between N=100 - N=1000

![Transition](Images/Transition.png)

## Measured Time for Analog Read

Average time for 1000 samples: 121853 µs
analogread() conversions per second: 8206.6

## Oscilloscope Results

![Oscilloscope](Images/Oscilloscope.jpg)

## Potentiometer Averaging Results

| Potentiometer block | Reported points | Readings averaged per point *N* | Mean voltage | Sample standard deviation *s* | *s* / *s*₁ measured | *s* / *s*₁ predicted |
| --- | ---: | ---: | --- | --- | ---: | ---: |
| Unaveraged | 100 | 1 |  | 0.48(Not mv in pwm steps)mV | 1.000 | 1.000 |
| Long average | 100 | 1000 |  | 0.2(Not mv in pwm steps)mV |  | 0.0316 |

## Oscilloscope VS Seiral Plotter

## Questions 9 and 10
