Run the GUI from the repo root (use the venv outside iCloud, see Module 7 notes):

```bash
~/.venvs/phy39a_repo/bin/python "Module 8/Python/serial_plot_mod8.py"
```

Module 8 is the Module 7 six-thermistor rig driven with a sinusoidal base temperature (Angstrom method). `Arduino/PWM_Serial_Control` is an unchanged copy of the Module 7 sketch. Files:

- `Python/serial_plot_mod8.py`: Module 7 GUI plus Open loop / P-only / PI modes, feedforward `uff(Tset)`, a sinusoidal setpoint `Tset(t) = Ta + Tb sin(2πt/τ)` (Ta = mean, Tb = amplitude, τ ≥ 100 s, peak Ta + Tb limited to 58 °C), room-temperature entry, and a choice of feedback sensor (TEC or T1). Writes `data/raw_mod8_<time>.csv` and `data/pi_log_mod8_<time>.csv` (the PI log adds `u_ff`, `feedback_C`, `feedback_sensor`).
- `Python/feedforward_curve_mod8.py`: inverts the measured susceptibility curves (`data/pwm_steady_state.csv`, from Module 4) into `uff(Tset)`; writes `data/feedforward_uff_mod8.csv/.png`.
- `Python/analyze_angstrom_mod8.py`: boundary metrics, per-sensor amplitude/phase, ordering check, settling criterion, one summary row per run in `data/angstrom_summary_mod8.csv`.
- `Python/calibrate_thermistors_mod8.py`: unchanged copy of the optional relative calibration.

## 1. Channel and safety verification

| Item | Status |
|------|--------|
| Channels | `tec_C` = A0 (TEC base), `rod1_C`…`rod5_C` = A1…A5 = T1…T5; all in °C (sketch conversion identical for all six) |
| Safety limits (sketch) | TEC-base cutoff trips above 60 °C, resets below 55 °C; TEC fault if ADC outside 10–1013 counts forces output off; GUI setpoint limited to 0–50 °C; PWM clamped 0–255 |
| Correction coefficients | None in the repo (no `data/calibration/` folder), so raw readings are used |
| Common-bath result | Not recorded in the repo. First record of the 20261104 run, before heating: rods 26.25–26.62 °C, TEC 25.69 °C (spread 0.93 °C, under the 1 °C limit). This is not a bath check; record the real one here |
| Positions from rod 1 | T1 = 0, T2 = 0.025 m, T3 = 0.05 m, T4 = 0.10 m, T5 = 0.15 m (hand-measured, ±3 mm assumed); L = 0.283 m |
| T1 lowest / nearest TEC, T2–T5 increasing distance | Consistent with the Module 7 step response: rises 17.9, 15.6, 13.9, 11.3, 9.5 °C and 50% response times 53, 89, 129, 226, 334 s for T1…T5, monotonic in the stated order |

`analyze_angstrom_mod8.py` repeats the ordering check on every sinusoid run (amplitude falls and lag rises from T1 to T5).

## 3. Feedforward (steady-state inversion)

Heating slope 0.516 °C/PWM, cooling slope 0.137 °C/PWM, ratio r = 3.76, fitted unpowered baseline 26.3 °C (enter the measured room temperature in the GUI). `uff(peak 56 °C)` = +57.6 PWM (heat), `uff(trough 24 °C)` = −16.8 PWM (cool), from `Tset = 40 + 16 sin(2πt/100 s)`. The curve comes from the TEC alone (Module 4); the attached rod adds side and axial loss, so expect extra droop in open loop.

Conventions: PWM > 0 with direction HEAT drives pin 9 (heating); direction COOL drives pin 10 (cooling); the GUI shows applied PWM from the Arduino record and the sign from `heat_cool` (1 = heat). Confirm with TEC power off and a small command before energizing.

## Run procedure (hardware steps still to do)

1. Start the GUI, confirm six temperatures, mode, setpoint and applied PWM update and a new `raw_mod8_*` / `pi_log_mod8_*` pair appears. Enter the measured room temperature.
2. Ta = 40 °C (mean), Tb = 16 °C (amplitude), τ = 100 s, so Tset swings 24 to 56 °C. Run **Open loop**, **P-only**, and **PI** with the same drive settings (same Ta, Tb, P, feedback sensor and feedforward setting), for at least 8 cycles each. Inspect T1, not the command.
3. For each run: `analyze_angstrom_mod8.py <stamp> --t0 <s> --t1 <s> --period 100 --label OPEN|P|PI`, then `--compare`.
4. If no mode gives an adequate T1 sinusoid, try P = 150 s or Tb = 10 °C and retune Kp, Ki. Never use P < 100 s (the GUI enforces it).
5. Keep ≥ 5 complete settled cycles (settling criterion in `analyze_angstrom_mod8.py`: per-cycle change in amplitude < 2%, phase < 2°, mean < 0.15 °C on every sensor) with measurable amplitude and phase on ≥ 3 rod sensors.
6. Pick a second period from the attenuation, phase lag and base tracking; repeat, wait for the transient to settle, retain ≥ 5 cycles.
