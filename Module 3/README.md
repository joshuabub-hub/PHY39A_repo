## What this project does

This is a thermoelectric cooler (TEC) heating/cooling test rig. An Arduino
reads a thermistor to measure temperature and drives an H-bridge to either
heat or cool, one direction at a time. A companion Python GUI (`serial_plot.py`)
lets you set the PWM level and direction from your computer, sends those
settings to the Arduino over serial, and plots the temperature and PWM the
Arduino reports back in real time. There is **no feedback/closed-loop
control** anywhere in this project - the PWM value you set is exactly the
PWM value that gets driven, with no automatic adjustment based on
temperature.

The `Fixed_Direction` and `Switch_Control` sketches are earlier, simpler
bench tests that ran the H-bridge from a trim pot and (for `Switch_Control`)
a physical switch, with no PC involved. `PWM_Serial_Control` is the current
sketch, meant to be paired with `serial_plot.py`.

## Hardware: what's connected to which pin

| Signal | Pin | Notes |
| --- | --- | --- |
| Thermistor | A0 | Thermistor to +5 V, 100 kΩ fixed resistor to GND, A0 reads the midpoint of that divider. |
| H-bridge HEAT input | 9 | Experimentally verified: driving pin 9 produces **heating**. |
| H-bridge COOL input | 10 | Experimentally verified: driving pin 10 produces **cooling**. |
| Trim pot (`Fixed_Direction`, `Switch_Control` only) | A1 | Sets PWM by hand. Not present/used in `PWM_Serial_Control`. |
| Direction switch (`Switch_Control` only) | 11 | `INPUT_PULLUP`; open = cooling, closed to GND = heating. Not present/used in `PWM_Serial_Control`. |

Only one H-bridge pin is ever driven with a nonzero PWM value at a time in
every sketch here - the inactive pin is always explicitly held at 0 so
heating and cooling can never be commanded simultaneously.

## Which sketch pairs with which Python program

| Arduino sketch | Paired Python program | How direction/PWM are set |
| --- | --- | --- |
| `PWM_Serial_Control/PWM_Serial_Control.ino` | `serial_plot.py` | Set from the Python GUI (slider/text box/Heat-Cool switch), sent over serial. This is the current, actively used pairing. |
| `Switch_Control/Switch_Control.ino` | none (standalone) | Trim pot (A1) sets PWM, physical switch (pin 11) sets direction. Does not read serial commands, so `serial_plot.py`'s controls have no effect on it. |
| `Fixed_Direction/Fixed_Direction.ino` | none (standalone) | Trim pot (A1) sets PWM, direction is fixed at compile time in the sketch. |

## How to upload and run the paired programs

1. **Upload the Arduino sketch.** In the Arduino IDE, open
   `PWM_Serial_Control/PWM_Serial_Control.ino`, select your board and serial
   port, and upload it. Leave the Arduino IDE's Serial Monitor **closed**
   afterward - only one program can hold the serial port open at a time, and
   Python needs it next.
2. **Set up the Python environment** (first time only):
   ```bash
   cd "Module 3"
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
3. **Point `serial_plot.py` at the right port.** Open `serial_plot.py` and
   set `SERIAL_PORT` near the top to your Arduino's port (e.g.
   `"/dev/cu.usbmodem101"`), or set it to `None` to have the script
   auto-detect it (only works if exactly one serial device is plugged in).
4. **Run it:**
   ```bash
   cd "Module 3"
   source venv/bin/activate
   python serial_plot.py
   ```
   The GUI window will open, the controls will enable once the serial port
   connects, and it will immediately send a starting PWM/direction command.

## Example serial line and field meanings

The Arduino reports its state once per loop, e.g.:

```
Temperature (C): 27.73, Time (s): 645.06, PWM: 120, Heat/Cool: 1
```

| Field | Meaning |
| --- | --- |
| `Temperature (C)` | Measured thermistor temperature, in Celsius. |
| `Time (s)` | Time since the Arduino booted (`millis() / 1000.0`), in seconds - not wall-clock time. |
| `PWM` | The 0-255 PWM value currently being written to whichever H-bridge pin is active. |
| `Heat/Cool` | `1` = actively driving the HEAT pin (9), `0` = actively driving the COOL pin (10). Reflects what's actually being driven right now, not just the last command's wording. |

Separately, Python sends *commands* to the Arduino in this format (not a
report line - this is Python writing, not the Arduino):

```
SET PWM 120 DIR HEAT
SET PWM 45 DIR COOL
```

## Where the Python code reads, parses, saves, plots, and sends serial data

All of this lives in `serial_plot.py`:

- **Reads** incoming lines from the Arduino: `SerialReader.run()` - runs in a
  background thread so the GUI never freezes waiting on serial data. It
  opens the port with `serial.Serial(...)` and calls `connection.readline()`
  in a loop.
- **Parses** each line: still inside `SerialReader.run()`, using the
  `LINE_PATTERN` regular expression to pull out temperature, time, PWM, and
  heat/cool as separate values, then emits them via the `measurement` Qt
  signal.
- **Saves** measurements to `temperature_log.csv`:
  `TemperaturePlotWindow.on_measurement()`, which receives that `measurement`
  signal and writes one row per measurement with `self.csv_writer`.
- **Plots** the data: `TemperaturePlotWindow.redraw_plots()`, run on a timer
  (`self.redraw_timer`, every `PLOT_UPDATE_INTERVAL_MS`). It updates the
  temperature strip chart (`self.temperature_curve`) and the PWM strip chart
  (`self.pwm_heat_curve` / `self.pwm_cool_curve`, colored red/blue by
  direction).
- **Sends** commands to the Arduino: `SerialReader.send_command()` writes a
  line to the same open connection. It's called from
  `TemperaturePlotWindow.send_current_settings()`, which is triggered
  whenever the PWM slider, the PWM text box, or the Heat/Cool switch changes
  in the GUI.

## Program explanations

- `Fixed_Direction/Fixed_Direction.ino`: Reads the thermistor and trim
  potentiometer, converts the ADC values into temperature and PWM, and
  drives only one H-bridge channel at a time. The direction is fixed in the
  code, so it's useful for a simple one-direction heater or cooler test.

- `Switch_Control/Switch_Control.ino`: Similar to the fixed-direction
  sketch, but reads a direction switch to decide whether the H-bridge
  should be heating or cooling. Uses the switch state to select which PWM
  pin is active and reports the chosen mode over serial.

- `PWM_Serial_Control/PWM_Serial_Control.ino`: Keeps the same thermistor
  measurement and one-pin-at-a-time H-bridge behavior, but has no trim pot
  or switch. PWM and direction instead come from `SET PWM <n> DIR
  <HEAT|COOL>` serial commands sent by `serial_plot.py`. Starts at PWM 0
  until the first command arrives.

- `serial_plot.py`: PySide6 + pyqtgraph GUI. Listens to the Arduino's
  serial output, parses temperature/time/PWM/heat-cool data, plots
  temperature and PWM versus time, logs every measurement to CSV, and sends
  PWM/direction commands back to the Arduino based on the GUI controls
  (slider, text box, Heat/Cool switch). Pair it with
  `PWM_Serial_Control.ino` - the other two sketches don't read serial
  commands, so the GUI's controls won't do anything with them connected.

## Hardware verification checklist

| Item | Status |
| --- | --- |
| Arduino board and port | Yes |
| Thermistor pin | A0 |
| H-bridge control pins | 9, 10 |
| PWM starts at zero? | yes |
| Module 2 motor test completed with TEC disconnected? | Yes |
| High-current leads are 18 AWG? | Yes |
| Prepared TEC and thermal-switch wiring inspected? | Yes |
| Heat exchanger connected to 12 V and operating? | Yes |
| Power supply voltage | 12 V |
| Power supply current limit | 10 A |
| Thermal cutoff identified? | Yes — 75 °C |
| Instructor check | Yes |

Waveform measurements: square wave, PWM frequency 500 Hz, PWM duty cycle
0.25, observed on m+, m-, pin 10, and pin 9.

## Manual Testing

Before powering the TEC, use an oscilloscope to confirm that the Arduino is producing the expected PWM waveform. This check helps verify that the H-bridge is receiving the intended signal and reduces the risk of unsafe or unexpected operation.

Also, with the white insulating foam in place over the TEC, the thermal switch should be tested to confirm that it operates correctly at the expected temperature. Verifying the switch in a controlled setup helps prevent future failures and gives a known safety point to check if a fault occurs.

## Questions

- Parts of the GUI code are still unclear

## AI Assistance

AI helped generate much of the Arduino and Python GUI code, but the project still required manual debugging and hardware validation. The sketches were tested on real hardware through the Arduino IDE and serial monitoring, and the README was also refined for clarity and readability.

We can explain the Arduino sketches and the serial communication workflow at a practical level, but deeper questions about the specific implementation details of the Python GUI may require additional code review or direct inspection of the script itself.