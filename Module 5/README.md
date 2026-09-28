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

Setpoint for this sequence is 30.0 °C. Taking ambient as Module 4's
measured baseline (~26.0 °C at PWM 0 - re-check the live ambient reading
before each run, since it drifts) puts the starting error at +4.0 °C, so
the initial direction is HEAT and Module 4's heat susceptibility
(0.516 °C/PWM) is the one used below. That fixes two reference PWM values
for this setpoint: the predicted output at the initial `Kp = 1.0` gain
comes out to **4.0**, and the PWM magnitude needed to fully close a 4.0 °C
error at steady state (per the heat susceptibility) comes out to
**~7.75**.

The five gains below start at that initial `Kp = 1.0` and climb past the
~7.75 point, so the run sequence brackets it from both sides before pushing
further into over-driven territory:

| Kp (PWM/°C) | Predicted P₀ | Required P | Setpoint (°C) | Final Temp (°C) | Steady-State Droop (°C) | Final PWM | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1.0 | 4.0 | 7.75 | 30.0 | 27.7 | 2.3 | 2 | Initial gain (= Pnaught); L < 1 in both directions (see above). Measured from `data/temperature_log.csv`, the MANUAL(PWM 0)->P transition at t≈2063.6 s through t≈2383 s: temperature climbs from ambient and settles into a small limit cycle (mostly PWM 2, occasionally 3, from integer PWM rounding) rather than reaching the 30.0 °C setpoint - the expected residual droop for a below-Prequired proportional gain. |
| 1.5 | 6.0 | 7.75 | 30.0 | 27.7 | 2.3 | 3 | Below Prequired. Note: not a fresh PWM=0 start - `Kp` was bumped live from 1.0 to 1.5 at t≈2457.5 s while still in P mode, starting from the Kp=1.0 run's settled state (~27.5 °C, PWM≈2) rather than from ambient. Settled (last 60 s through t≈2623 s) at PWM mostly 3, occasionally 4. Droop came out nearly the same as Kp=1.0 - expected, since the predicted droop only drops from ~2.6 °C to ~2.25 °C between these two gains. |
| 2.0 | 8.0 | 7.75 | 30.0 | 27.9 | 2.1 | 4 | ~ Prequired. `Kp` was stepped 1.5->1.6->...->2.0 while in MANUAL with PWM held at 0, then switched to P at t≈2707.6 s - so this trial does start clean from PWM=0, same as Kp=1.0. Noticeably more oscillation than the lower gains (last 60 s of t≈2882.7 s ranged 27.58-29.62 °C, vs. <1 °C spread at Kp=1.0/1.5) - expected since this gain sits right at Prequired. Droop dropped modestly to 2.1 °C, in line with the predicted ~2.0 °C. |
| 3.0 | 12.0 | 7.75 | 30.0 | 28.8 | 1.2 | 3-4 | Above Prequired. **Post-restart data**: the script crashed around t≈3000 s (of the prior run) and was restarted, which truncates `data/temperature_log.csv` (opened in `"w"` mode on startup) - only data from after the restart is usable/reflected here. `Kp` was stepped 1.0->...->3.0 in MANUAL with PWM held at 0, then switched to P at t≈13.7 s (restarted clock), so this is a clean PWM=0 start. Starting temperature was already ~28.8-29.0 °C rather than ~27 °C ambient - the rig was still warm from the pre-restart runs, not cold-started - so treat the Predicted P0/Required P reference values (computed from the ~26 °C ambient baseline) as less accurate for this trial. Reached a tight steady band almost immediately (last 60 s through t≈168 s: 28.67-29.00 °C) alternating between PWM 3 and 4. Droop continued the expected downward trend (2.3 -> 2.3 -> 2.1 -> 1.2 °C). |
| 5.0 | 20.0 | 7.75 | 30.0 | TBD | TBD | TBD | Above Prequired. Previous run at this gain discarded - hardware issue, not a valid closed-loop result. Re-run and refill. |

## How to upload and run the paired programs

1. **Upload the Arduino sketch.** In the Arduino IDE, open
   `Arduino/PWM_Serial_Control/PWM_Serial_Control.ino`, select your board
   and serial port, and upload it. Leave the Arduino IDE's Serial Monitor
   **closed** afterward - only one program can hold the serial port open at
   a time, and Python needs it next.
2. **Set up the Python environment** (first time only):
   ```bash
   cd "Module 5"
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
3. **Point `serial_plot_mod5.py` at the right port.** Open
   `Python/serial_plot_mod5.py` and set `SERIAL_PORT` near the top to your
   Arduino's port (e.g. `"/dev/cu.usbmodem101"`), or set it to `None` to
   have the script auto-detect it (only works if exactly one serial device
   is plugged in).
4. **Run it:**
   ```bash
   cd "Module 5"
   source venv/bin/activate
   python Python/serial_plot_mod5.py
   ```
   Run from the `Module 5` directory (not `Module 5/Python`) since
   measurements are logged to `data/temperature_log.csv`, a path relative
   to the current working directory. The GUI starts in Manual mode with
   PWM 0/COOL, matching Module 4's default; switch to P Control once the
   serial port has connected and the setpoint/`Kp` are set the way you want.
