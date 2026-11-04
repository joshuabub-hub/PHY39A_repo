```bash
cd "/Users/joshbub/Documents/PHYS39A_Repo/PHY39A_repo/Module 7" && venv/bin/python Python/serial_plot_mod7.py
```

Starting point: `Arduino/PWM_Serial_Control` and `Python/serial_plot_mod7.py` come from Module 6 (PI controller GUI).

Each GUI run creates two new files in `data/` (existing files are never overwritten), joined on `time_s`:
- `raw_mod7_YYYYMMDD_HHMMSS.csv`: every accepted DATA record exactly as received, columns `time_s,tec_C,rod1_C,rod2_C,rod3_C,rod4_C,rod5_C,pwm,heat_cool,setpoint_C,safety`. No calibration applied.
- `pi_log_mod7_YYYYMMDD_HHMMSS.csv`: the GUI's setpoint, Kp/Ki, error, and PI terms for each of those records.

The sketch reads six thermistors: A0 = TEC base (the only channel used for PI feedback, the 60/55 °C cutoff, and the sensor-fault check), A1–A5 = rod thermistors 1–5. It prints a header once at startup, then one record per acquisition cycle (~0.75 s):

```
DATA,time_s,tec_C,rod1_C,rod2_C,rod3_C,rod4_C,rod5_C,pwm,heat_cool,setpoint_C,safety
DATA,12.50,23.41,23.38,23.36,23.34,23.31,23.29,120,1,nan,OK
```

`setpoint_C` is always `nan` from the Arduino (the setpoint lives in the Python GUI and is logged there). `safety` is `OK`, `CUTOFF`, or `SENSOR_FAULT`; a faulted channel reads `nan`. Nothing else the sketch prints starts with `DATA`.

## Rod properties

| Material | Specific heat (J/(kg·K)) | Diameter (m) | Physical length (m) | Analysis length (m) | Cross-sectional area (m²) | Perimeter (m) |
|----------|--------------------------|--------------|---------------------|---------------------|---------------------------|---------------|
|          |                          | 0.011        | 0.300               | 0.283               | ~9.50 × 10⁻⁵               | ~0.0346        |

Cylinder: area = πd²/4 = π(0.011 m)²/4, perimeter = πd = π(0.011 m).

## Thermistor labels

| A0       | A1 | A2 | A3 | A4 | A5 |
|----------|----|----|----|----|----|
| TEC-base |    |    |    |    |    |
| Orange   | Red | White | Grey | Green | Blue |

## Calibration

`Python/calibrate_thermistors_mod7.py` fits `tec_C = a_i + b_i * rod_i_C` for each rod over a range you choose (by time or by TEC temperature; only `safety = OK` rows are used) and writes new files to `data/calibration/` without touching the raw CSV:

```bash
venv/bin/python Python/calibrate_thermistors_mod7.py data/raw_mod7_<run>.csv --time 120 900
venv/bin/python Python/calibrate_thermistors_mod7.py data/raw_mod7_<run>.csv --temp 18 40
```

Outputs: `_table.csv` (a, b, n, range, residual mean/std/max), `_corrected.csv` (all raw columns + `rod1_corrected_C`…`rod5_corrected_C`), `_fits.png`, `_residuals.png`.

## Step response and stationary profile (run `raw_mod7_20261104_091551`)

Setpoint stepped 20 → 45 °C at t = 788.9 s (PI, Kp = 45, Ki = 0.5). Rod positions from rod 1's hole: 0, 0.025, 0.05, 0.10, 0.15 m (hand-measured, ±3 mm assumed). L = 0.283 m, d = 0.011 m. T∞ = 26.4 °C from the first 30 s of the log (room temperature was not logged, ±1 °C assumed).

Scripts (run with `~/.venvs/phy39a_repo/bin/python`, from the repo root):
- `Python/plot_step_response_mod7.py` → `data/step_response_mod7.png` (all six temperatures; commanded TEC, measured TEC and rod T(0,t)) and `data/step_boundary_condition_mod7.csv`.
- `Python/fit_stationary_profile_mod7.py` → `data/stationary_profile_mod7.png` (θ(x) with error bars, both fits, residuals) and `data/stationary_profile_mod7.csv`.

Farther sensors respond later and with smaller rises: heat diffuses along the rod (delay ~ x²/α) and side loss removes heat along the way. Time to 50% of rise after the step, rods 1–5: about 53, 89, 129, 226, 334 s.

Steady-state check, data to t = 3777 s, criterion |dT/dt| < 0.02 °C/min on every rod for 10 min: **not met**. Last-10-min drift, rods 1–5: +0.011, +0.015, +0.018, +0.024, +0.029 °C/min (TEC steady). The last window that passed ended at 3277 s. The profile below is a near-stationary average of the final 5 min (3477–3777 s), so treat it as provisional.

Predicted (planning values h = 10 W/m²K, k = 167 W/mK; computed after the run): m = 4.67 m⁻¹, 1/m = 0.214 m, mL = 1.32.

| Model | m (m⁻¹) | 1/m (m) | χ²/dof |
|-------|---------|---------|--------|
| Finite, insulated tip | 5.35 ± 0.23 | 0.187 ± 0.008 | 1.13/3 |
| Semi-infinite | 4.33 ± 0.28 | 0.231 ± 0.015 | 3.07/3 |

- Ignoring the tip lowers m by 1.02 m⁻¹ (19%), 4.5× the finite-fit uncertainty, so the rod is not semi-infinite (fitted mL ≈ 1.5).
- Changing T∞ by ±1 °C shifts m by about ±0.4 m⁻¹, larger than the fit error.
- Measured θ at rods 2–5 is 0.6–0.9 °C below the prediction; fitted m is 15% above predicted (implied h ≈ 13 W/m²K at k = 167).
- Fitted m gives Bi⊥ ≈ 2×10⁻⁴ ≪ 1, so each cross section can be treated as one temperature.
- Unresolved: room-temperature drift (all rods dipped near 2000 s), rod 1 contact offset below the TEC, and that the sensors only reach x = 0.15 m so the tip condition is assumed, not measured.
