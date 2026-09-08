# Module 1

This folder contains the Arduino sketches, results, and supporting evidence for
Module 1 of PHY39A.

## Project Files

### Arduino sketches

- [Blink_example.ino](Blink_example.ino): Arduino's built-in LED example. It
	toggles `LED_BUILTIN` on and off once per second.
- [Blink/Blink.ino](Blink/Blink.ino): A modified blink sketch that controls an
	LED on digital pin 9 and switches it on and off with 10 millisecond delays.
- [Blink/Blink.txt](Blink/Blink.txt): Short description of the Blink sketch.
- [AnalogReadSerial1/AnalogReadSerial1.ino](AnalogReadSerial1/AnalogReadSerial1.ino):
	Reads the voltage level from analog pin A0 and prints the raw 10-bit ADC
	reading to the Serial Monitor at 9600 baud.
- [Seq_Avg_volt_1/Seq_Avg_volt_1.ino](Seq_Avg_volt_1/Seq_Avg_volt_1.ino):
	Compares sequential readings with 1,000-sample averages, calculates means and
	standard deviations, measures averaging time, converts the average to a
	voltage, and maps the result to PWM output on pin 9.
- [StDev/StDev.ino](StDev/StDev.ino): Takes 100 analog readings from A0 and
	reports their mean and standard deviation through the Serial Monitor.

### Evidence and results

- [module_01_evidence.md](module_01_evidence.md): Module 1 evidence document,
	including team information, apparatus documentation, ADC digitization
	results, and links to the Arduino sketches.
- [Apparatus.jpeg](Apparatus.jpeg): Photograph of the experimental apparatus
	referenced by the evidence document.
- [Transition.png](Transition.png): Plot showing the transition between
	`N=100` and `N=1000`.



