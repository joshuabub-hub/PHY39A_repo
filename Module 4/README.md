## What this project does

This is a continuation of the Module 3 thermoelectric cooler (TEC)
heating/cooling test rig. An Arduino reads a thermistor to measure
temperature and drives an H-bridge to either heat or cool, one direction at
a time. A companion Python GUI (`serial_plot_mod4.py`) lets you set the PWM
level and direction from your computer, sends those settings to the Arduino
over serial, and plots the temperature and PWM the Arduino reports back in
real time. There is **no feedback/closed-loop control** - the PWM value you
set is exactly the PWM value that gets driven, with no automatic adjustment
based on temperature.

New in this module: the Arduino sketch now includes a software
over-temperature cutoff that forces the H-bridge off independent of
whatever the Python GUI is commanding.

## Hardware: what's connected to which pin

| Signal | Pin | Notes |
| --- | --- | --- |
| Thermistor | A0 | Thermistor to +5 V, 100 kΩ fixed resistor to GND, A0 reads the midpoint of that divider. |
| H-bridge HEAT input | 9 | Experimentally verified: driving pin 9 produces **heating**. |
| H-bridge COOL input | 10 | Experimentally verified: driving pin 10 produces **cooling**. |

Only one H-bridge pin is ever driven with a nonzero PWM value at a time -
the inactive pin is always explicitly held at 0 so heating and cooling can
never be commanded simultaneously.

## Useful PWM range

Bench testing found that PWM values beyond these points stopped producing
meaningfully more heating/cooling effect for this TEC/heat-exchanger setup:

| Direction | Max useful PWM |
| --- | --- |
| Heat | 45 |
| Cool | 115 |

The GUI's slider still allows the full 0-255 range, but there is little
benefit to commanding values above these.

## PWM step-test data

Test points at 0%, 25%, 50%, 75%, and 100% of each direction's max useful
PWM (45 for heat, 115 for cool), holding each PWM steady until the
temperature reaches steady state before recording and moving to the next
value.

### Heat

| PWM | % of max useful | Starting Temp (°C) | Steady-State Temp (°C) | Time Elapsed (s) | Notes |
| --- | --- | --- | --- | --- | --- |
| 0 | 0% | 48.91 | ~26.0 | ~448.2 | Switched to PWM 0 at t=2857.84s (48.91 °C, right after the PWM 45/HEAT test) and ran to t=3306.03s, 26.01 °C. At PWM 0 neither H-bridge pin is driven, so this is the same "power off" segment used for the Cool 0% row below — starting temp is elevated because it follows the 100% heat test rather than starting from ambient. Rate of decline had slowed to ~0.001 °C/s by the end, so steady state (≈ambient) is approximate. |
| 11 | 25% | 10.55 | ~31.9 | ~328.6 | Switched to PWM 11/HEAT at t=1430.3s (10.55 °C). Logging stopped at t=1758.9s, 31.92 °C; temp was still creeping up (~0.01 °C/s) at that point, so steady state is approximate. |
| 23 | 50% | 32.19 | ~38.6 | ~324.7 | Switched to PWM 23/HEAT at t=1819.08s (32.19 °C). Temp plateaued by t≈2040s (38.67 °C) and stayed flat (±0.15 °C noise) through the rest of the log, ending at t=2143.8s, 38.67 °C — true steady state reached. |
| 34 | 75% | 38.62 | ~43.7 | ~216.4 | Switched to PWM 34/HEAT at t=2317.96s (38.62 °C). Logging stopped at t=2534.35s, 43.72 °C; rise had slowed to ~0.002 °C/s by the end (near-flat but not fully settled), so steady state is approximate. |
| 45 | 100% | 43.68 | ~49.2 | ~236.1 | Switched to PWM 45/HEAT at t=2569.02s (43.68 °C). Logging stopped at t=2805.09s, 49.24 °C; still creeping up slowly (~0.0036 °C/s) at the end, so steady state is approximate. |

### Cool

| PWM | % of max useful | Starting Temp (°C) | Steady-State Temp (°C) | Time Elapsed (s) | Notes |
| --- | --- | --- | --- | --- | --- |
| 0 | 0% | 48.91 | ~26.0 | ~448.2 | Same PWM 0 "power off" segment as the Heat 0% row (t=2857.84s, 48.91 °C → t=3306.03s, 26.01 °C) — at PWM 0 neither H-bridge pin is driven, so heat/cool direction has no physical effect. Starting temp is elevated because it follows the 100% heat test rather than starting from ambient; rate of decline had slowed to ~0.001 °C/s by the end, so steady state (≈ambient) is approximate. |
| 29 | 25% | 25.98 | ~22.5 | ~188.7 | Switched to PWM 29/COOL at t=3400.67s (25.98 °C). Logging stopped at t=3589.4s, 22.53 °C; still creeping down slowly (~0.005 °C/s) at the end, so steady state is approximate. |
| 58 | 50% | 22.45 | ~18.8 | ~183.9 | Switched to PWM 58/COOL at t=3611.38s (22.45 °C). Logging stopped at t=3795.25s, 18.78 °C; still creeping down slowly (~0.003 °C/s) at the end, so steady state is approximate. |
| 86 | 75% | 18.53 | ~14.8 | ~213.5 | Switched to PWM 86/COOL at t=3882.39s (18.53 °C). Logging stopped at t=4095.92s, 14.82 °C; still creeping down slowly (~0.004 °C/s) at the end, so steady state is approximate. |
| 115 | 100% | 14.77 | ~10.2 | ~275.2 | Switched to PWM 115/COOL at t=4114.94s (14.77 °C). Logging stopped at t=4390.1s, 10.17 °C; nearly flat over the last ~50s (10.30 → 10.17) with a slight residual decline (~0.003 °C/s), so steady state is close but approximate. |

The table above is also available as data in `data/pwm_steady_state.csv`, and
`Python/plot_steady_state.py` plots it (steady-state temperature vs. signed
PWM, heating in red, cooling in blue) and saves
`data/pwm_steady_state_plot.png`. PWM is signed in the CSV/plot so direction
is encoded on one axis: positive = heating, negative = cooling (e.g. cooling
at PWM 86 is stored/plotted as -86).

## Temperature susceptibility

Fitting a line (least-squares) to steady-state temperature vs. signed PWM
for each direction gives:

| Direction | Susceptibility (°C / signed PWM count) |
| --- | --- |
| Heat | +0.516 |
| Cool | +0.137 |

Both slopes are positive in this signed frame - increasing signed PWM
(more heating, or less cooling) always raises the steady-state temperature.
Heating moves the steady-state temperature about 3.8x more per PWM count
than cooling does over these ranges (45 max useful PWM for heat vs. 115 for
cool). These values are computed and annotated directly on the plot by
`Python/plot_steady_state.py`.

## Heating/cooling asymmetry

Heating and cooling are not mirror images of each other in this system:

| | Heat | Cool | Ratio (heat / cool) |
| --- | --- | --- | --- |
| Max useful PWM | 45 | 115 | 0.39x |
| Susceptibility (°C / signed PWM) | +0.516 | +0.137 | 3.8x |
| Steady-state span over useful range | ~23.2 °C (26.0 → 49.2) | ~15.8 °C (26.0 → 10.2) | 1.5x |

Heating saturates in usefulness at a much lower PWM than cooling (45 vs.
115) but moves the temperature ~3.8x more per PWM count while it's still
useful, and reaches a larger total temperature swing (~23 °C vs. ~16 °C)
over its shorter useful range. In other words, heating is the more
"powerful" and more quickly-saturating direction, while cooling is weaker
per PWM count but stays useful over a much wider PWM range.

Plausible contributors (not verified in this module - would need separate
testing to isolate):
- The Peltier element's heating and cooling efficiencies are not
  symmetric to begin with (typical of TEC modules).
- The heat exchanger/fan setup may dissipate heat more effectively than it
  can supply it, making added cooling PWM "cheaper" per degree than added
  heating PWM.
- Ambient room temperature sits between the two steady-state extremes
  (~26 °C at PWM 0), so heating always works against a bigger fixed
  temperature gradient to ambient as it climbs, while cooling initially has
  less gradient to fight before picking up as it drops further below
  ambient.

## Over-temperature cutoff

`PWM_Serial_Control.ino` includes a latching, hysteretic software cutoff:

- If the thermistor reads above **60 °C**, the cutoff trips and both
  H-bridge pins are forced to 0 regardless of the last commanded PWM/
  direction.
- The cutoff stays active until the temperature drops back below **55 °C**,
  at which point normal control resumes.
- The 5 °C gap between trip and reset (hysteresis) stops the cutoff from
  rapidly switching on/off right at the trip point.
- The Arduino reports whether the cutoff is currently active in every
  serial line (`Cutoff: 1` or `Cutoff: 0`).

## How to upload and run the paired programs

1. **Upload the Arduino sketch.** In the Arduino IDE, open
   `Arduino/PWM_Serial_Control/PWM_Serial_Control.ino`, select your board
   and serial port, and upload it. Leave the Arduino IDE's Serial Monitor
   **closed** afterward - only one program can hold the serial port open at
   a time, and Python needs it next.
2. **Set up the Python environment** (first time only):
   ```bash
   cd "Module 4"
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
3. **Point `serial_plot_mod4.py` at the right port.** Open
   `Python/serial_plot_mod4.py` and set `SERIAL_PORT` near the top to your
   Arduino's port (e.g. `"/dev/cu.usbmodem101"`), or set it to `None` to
   have the script auto-detect it (only works if exactly one serial device
   is plugged in).
4. **Run it:**
   ```bash
   cd "Module 4"
   source venv/bin/activate
   python Python/serial_plot_mod4.py
   ```
   The GUI window will open, the controls will enable once the serial port
   connects, and it will immediately send a starting PWM/direction command.
   Run from the `Module 4` directory (not `Module 4/Python`) since
   measurements are logged to `data/temperature_log.csv`, a path relative
   to the current working directory.

## Example serial line and field meanings

The Arduino reports its state once per loop, e.g.:

```
Temperature (C): 27.73, Time (s): 645.06, PWM: 45, Heat/Cool: 1, Cutoff: 0
```

| Field | Meaning |
| --- | --- |
| `Temperature (C)` | Measured thermistor temperature, in Celsius. |
| `Time (s)` | Time since the Arduino booted (`millis() / 1000.0`), in seconds - not wall-clock time. |
| `PWM` | The 0-255 PWM value currently being written to whichever H-bridge pin is active (0 while the cutoff is tripped). |
| `Heat/Cool` | `1` = actively driving the HEAT pin (9), `0` = actively driving the COOL pin (10). Reflects what's actually being driven right now, not just the last command's wording. |
| `Cutoff` | `1` = over-temperature cutoff is active and forcing the H-bridge off, `0` = normal operation. |

Separately, Python sends *commands* to the Arduino in this format (not a
report line - this is Python writing, not the Arduino):

```
SET PWM 45 DIR HEAT
SET PWM 115 DIR COOL
```

## Where the Python code reads, parses, saves, plots, and sends serial data

All of this lives in `Python/serial_plot_mod4.py` (same behavior as Module
3's `serial_plot.py`, renamed to keep the two modules' scripts distinct):

- **Reads** incoming lines from the Arduino: `SerialReader.run()` - runs in a
  background thread so the GUI never freezes waiting on serial data.
- **Parses** each line: still inside `SerialReader.run()`, using the
  `LINE_PATTERN` regular expression to pull out temperature, time, PWM, and
  heat/cool as separate values, then emits them via the `measurement` Qt
  signal.
- **Saves** measurements to `data/temperature_log.csv`:
  `TemperaturePlotWindow.on_measurement()`, which receives that
  `measurement` signal and writes one row per measurement.
- **Plots** the data: `TemperaturePlotWindow.redraw_plots()`, run on a timer
  (`self.redraw_timer`, every `PLOT_UPDATE_INTERVAL_MS`).
- **Sends** commands to the Arduino: `SerialReader.send_command()`, called
  from `TemperaturePlotWindow.send_current_settings()` whenever the PWM
  slider, the PWM text box, or the Heat/Cool switch changes in the GUI.
