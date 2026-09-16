## Program explanations

- Fixed_Direction/Fixed_Direction.ino: This Arduino sketch reads the thermistor and trim potentiometer, converts the ADC values into temperature and PWM, and drives only one H-bridge channel at a time. The direction is fixed in the code, so it is useful for a simple one-direction heater or cooler test.

- Switch_Control/Switch_Control.ino: This version is similar to the fixed-direction sketch, but it reads a direction switch to decide whether the H-bridge should be driving heating or cooling. It uses the switch state to select which PWM pin is active and reports the chosen mode over serial.

- Python/serial_plot.py: This Python program listens to the Arduino's serial output, parses temperature, time, PWM, and heat/cool data, and plots temperature versus time in a GUI window. It also saves the measurements to a CSV file for later analysis.

## Table
Arduino board and port - Check?	
Thermistor pin	- A0
H-bridge control pins - 9,10	
PWM starts at zero?	- Fixed right now
Module 2 motor test completed with TEC disconnected? - Yes	
High-current leads are 18 AWG? - Yes
Prepared TEC and thermal-switch wiring inspected? - 	
Heat exchanger connected to 12 V and operating?	- 
Power supply voltage - 12V
Power supply current limit - 10A	
Thermal cutoff identified? - No
Instructor Check - Yes

m+ waveform - square wave, PWM Frq - 500Hz, PWM duty cycle - 0.25
m- waveform - square wave, PWM Frq - 500Hz, PWM duty cycle - 0.25
pin 10 waveform - square wave, PWM Frq - 500Hz, PWM duty cycle - 0.25
pin 9 waveform - square wave, PWM Frq - 500Hz, PWM duty cycle - 0.25