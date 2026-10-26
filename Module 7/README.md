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
