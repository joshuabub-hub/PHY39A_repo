## What this project does

This is a continuation of the Module 3/4 thermoelectric cooler (TEC)
heating/cooling test rig. Module 4 was open-loop: the PWM value you set in
the GUI was exactly the PWM value driven, with no automatic adjustment
based on temperature. This module closes the loop with **proportional
(P) only control** - the Python GUI can now compute the PWM/direction
command itself from the measured temperature and a target setpoint,
instead of requiring a human to pick it by hand.

The Arduino sketch (`Arduino/PWM_Serial_Control/PWM_Serial_Control.ino`) is
an unchanged copy of Module 4's: it still averages about 1000 raw
thermistor-voltage samples per loop before converting that average to a
temperature, still parses `SET PWM <n> DIR <HEAT|COOL>` commands, still
drives the H-bridge (one pin at a time), and still enforces its own
independent, latching, hysteretic over-temperature cutoff (trip at 60 °C,
reset at 55 °C) regardless of what either control mode commands. All of the
closed-loop logic lives entirely in the new Python script.

## Hardware: what's connected to which pin

| Signal | Pin | Notes |
| --- | --- | --- |
| Thermistor | A0 | Thermistor to +5 V, 100 kΩ fixed resistor to GND, A0 reads the midpoint of that divider. |
| H-bridge HEAT input | 9 | Experimentally verified: driving pin 9 produces **heating**. |
| H-bridge COOL input | 10 | Experimentally verified: driving pin 10 produces **cooling**. |

## The Python GUI: two control modes

`Python/serial_plot_mod5.py` adds a Control Mode switch to Module 4's GUI:

- **Manual** - identical to Module 4. Pick a PWM value and direction by
  hand with the slider/radio buttons and it's sent to the Arduino as-is.
- **P Control** - every time a new (already 1000-sample-averaged)
  temperature arrives from the Arduino, the script:
  1. reads the measured temperature `T` straight from that Arduino report,
  2. computes the error `e = Tset - T`, where `Tset` is the setpoint from
     the GUI's spinbox,
  3. computes the control signal `u = Kp * e`, where `Kp` is the gain from
     the GUI's spinbox,
  4. converts the **sign** of `u` into a direction (`u >= 0` -> HEAT, since
     a positive error means we're colder than the setpoint; `u < 0` ->
     COOL),
  5. converts `|u|`, rounded to the nearest integer, into a PWM magnitude,
  6. clamps that magnitude to the valid 0-255 range,
  7. sends direction and PWM magnitude to the Arduino as one
     `SET PWM <magnitude> DIR <HEAT|COOL>` command - the same command
     format Manual mode uses.

Only one mode drives the Arduino at a time: the manual slider/radio buttons
are disabled while P Control is active, so the two control paths can never
send conflicting commands over the same serial link.

The GUI keeps plotting temperature, PWM, direction, setpoint, and error:
the temperature strip chart overlays a dashed setpoint line, the PWM strip
chart is still split into red (heating) / blue (cooling) segments by
direction, and a new error strip chart (with a dashed zero line) shows
`Tset - T` directly. All of this - including setpoint, `Kp`, and error - is
also written to `data/temperature_log.csv` alongside the existing time/
temperature/PWM/direction columns.

## Choosing the initial gain: keep the loop gain under 1

Module 4's step-test data gives the plant's steady-state susceptibility -
how many degrees C the steady-state temperature moves per PWM count:

| Direction | Susceptibility (°C / PWM count) |
| --- | --- |
| Heat | +0.516 |
| Cool | +0.137 |

For a proportional loop, the "loop gain" is the product of the controller
gain and the plant gain it's driving:

```
L = Kp * (temperature susceptibility)
```

Keeping `L < 1` means a single proportional correction can't out-drive the
error it's responding to, which is a simple, conservative starting point
before any real tuning - it avoids the controller immediately overshooting
past the setpoint on its very first correction. Since both measured
susceptibilities above are already less than 1 °C/PWM, starting with:

```
Kp = 1.0   (PWM counts per degree C of error)
```

keeps `L = Kp * susceptibility < 1` in both directions right out of the
gate (`L ≈ 0.516` heating, `L ≈ 0.137` cooling) without needing to shrink
`Kp` below 1. This is deliberately small next to Module 4's useful PWM
ranges (up to 45 heating, up to 115 cooling) - a 10 °C error only commands
a PWM magnitude of 10. **`Kp = 1.0` is only a starting point, not a tuned
value** - raise it gradually from here and watch for sustained oscillation
or the PWM slamming into 0/255 before going any higher.

## Gain-tuning log

This is a single continuous run (no restarts) recorded start-to-finish in
`data/temperature_log.csv`: MANUAL at PWM 0 first, then P Control stepped
through `Kp = 1.0, 1.5, 2.0, 3.0, 5.0` in order, each held until it reached
steady state before advancing to the next gain. Ambient, taken as the last
MANUAL-mode reading before switching to P Control, was **21.42 °C**.
Setpoint for the whole sequence is 30.0 °C, so the starting error is
+8.58 °C - direction is HEAT, and Module 4's heat susceptibility
(`χT,h = 0.516 °C/PWM`) is the one used below. That fixes two reference PWM
values for this setpoint: the predicted output at the initial `Kp = 1.0`
gain comes out to **8.58**, and the PWM magnitude needed to fully close an
8.58 °C error at steady state comes out to

```
Prequired ≈ |Tset - Tamb| / χT,h = 8.58 / 0.516 ≈ 16.63 PWM counts
```

The results below were computed directly from `data/temperature_log.csv`:
each row's Final Temp/Final PWM are the mean over the last 60 s of that
gain's segment (segments identified by contiguous `mode`/`kp` values), and
Steady-State Droop is `Setpoint - Final Temp`.

| Kp (PWM/°C) | Predicted P₀ | Required P | Setpoint (°C) | Segment (s) | Final Temp (°C) | Steady-State Droop (°C) | Final PWM | Notes |
| --- | ---: | ---: | ---: | --- | ---: | ---: | ---: | --- |
| 1.0 | 8.58 | 16.63 | 30.0 | 11.50 - 187.70 | 23.93 | 6.07 | 6 | Below Prequired; clean PWM=0 start from 21.42 °C ambient. Last 60 s held steady at PWM 6, 23.83-24.00 °C. |
| 1.5 | 12.87 | 16.63 | 30.0 | 187.84 - 390.13 | 25.01 | 4.99 | 7 | Below Prequired. Last 60 s: PWM mostly 7 (occasionally 8), 24.98-25.03 °C. |
| 2.0 | 17.16 | 16.63 | 30.0 | 390.26 - 518.41 | 25.73 | 4.27 | 9 | ~ Prequired. Last 60 s: PWM 8-9 (mode 9), 25.67-25.76 °C. |
| 3.0 | 25.74 | 16.63 | 30.0 | 518.54 - 636.83 | 26.54 | 3.46 | 10 | Above Prequired. Last 60 s: steady at PWM 10, 26.50-26.59 °C. |
| 5.0 | 42.90 | 16.63 | 30.0 | 636.96 - 990.23 | 27.70 | 2.30 | 12 | Above Prequired. Last 60 s: PWM 11-12 (mode 12), 27.69-27.72 °C. |

Droop drops monotonically and smoothly as `Kp` increases (6.07 -> 4.99 ->
4.27 -> 3.46 -> 2.30 °C), as expected from a single clean, continuously
warming run with no restarts or stale starting temperatures.

## Predicted vs. measured steady-state droop

Closing the loop `T = Tamb + χT,h P` with `P = Kp(Tset - T)` and solving for
the steady-state error gives

```
Tset - T = (Tset - Tamb) / (1 + χT,h Kp)
```

Using Module 4's measured heating susceptibility `χT,h = 0.516 °C/PWM
count`, the ambient measured in this run (`Tamb = 21.42 °C`), and
`Tset = 30.0 °C` (so `Tset - Tamb = 8.58 °C`) gives the predicted droop
below for each gain tested above:

| Kp (PWM/°C) | χT,h Kp (dimensionless) | Predicted Steady-State Droop (°C) | Predicted Final Temp (°C) | Measured Steady-State Droop (°C) |
| --- | ---: | ---: | ---: | ---: |
| 1.0 | 0.52 | 5.66 | 24.34 | 6.07 |
| 1.5 | 0.77 | 4.84 | 25.16 | 4.99 |
| 2.0 | 1.03 | 4.22 | 25.78 | 4.27 |
| 3.0 | 1.55 | 3.37 | 26.63 | 3.46 |
| 5.0 | 2.58 | 2.40 | 27.60 | 2.30 |

The predicted droop tracks the measured droop closely at every gain (all
within ~0.4 °C), which is expected now that the whole sweep comes from one
continuous, cold-started run rather than several disjoint restarts.

## How to upload and run the paired programs

1. **Upload the Arduino sketch.** In the Arduino IDE, open
   `Arduino/PWM_Serial_Control/PWM_Serial_Control.ino`, select your board
   and serial port, and upload it. Leave the Arduino IDE's Serial Monitor
   **closed** afterward - only one program can hold the serial port open at
   a time, and Python needs it next.
2. **Set up the Python environment** (first time only). Create the venv
   *outside* this repo (and outside any iCloud-synced folder like
   `~/Documents`) - a venv left inside an iCloud "Desktop & Documents"
   synced folder can intermittently get its files evicted/re-hydrated by
   iCloud, which breaks PySide6's Qt platform plugin (`cocoa`) with an
   abort on launch:
   ```bash
   python3 -m venv ~/.venvs/phy39a_repo
   source ~/.venvs/phy39a_repo/bin/activate
   cd "Module 5"
   pip install -r requirements.txt
   ```
3. **Point `serial_plot_mod5.py` at the right port.** Open
   `Python/serial_plot_mod5.py` and set `SERIAL_PORT` near the top to your
   Arduino's port (e.g. `"/dev/cu.usbmodem101"`), or set it to `None` to
   have the script auto-detect it (only works if exactly one serial device
   is plugged in).
4. **Run it:**
   ```bash
   source ~/.venvs/phy39a_repo/bin/activate
   cd "Module 5"
   python Python/serial_plot_mod5.py
   ```
   Run from the `Module 5` directory (not `Module 5/Python`) since
   measurements are logged to `data/temperature_log.csv`, a path relative
   to the current working directory. The GUI starts in Manual mode with
   PWM 0/COOL, matching Module 4's default; switch to P Control once the
   serial port has connected and the setpoint/`Kp` are set the way you want.
