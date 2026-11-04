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
cd "/Users/joshbub/Documents/PHYS39A_Repo/PHY39A_repo/Module 7" && venv/bin/python Python/calibrate_thermistors_mod7.py data/raw_mod7_<run>.csv
```

Restrict the fit range (otherwise the whole file is used); add `--no-show` to save plots without opening windows:

```bash
venv/bin/python Python/calibrate_thermistors_mod7.py data/raw_mod7_<run>.csv --time 120 900
venv/bin/python Python/calibrate_thermistors_mod7.py data/raw_mod7_<run>.csv --temp 18 40
```

**Decision: no correction is applied.** A steady-temperature check (`raw_mod7_20261028_112155.csv`, TEC ≈ 21.2 °C) gave rod − TEC offsets of +0.94, −0.43, +0.76, +0.31, +0.13 °C for rods 1–5, which we judged uniform enough. `serial_plot_mod7.py` plots, logs, and controls on the uncorrected temperatures.

Outputs: `_stats.csv` (per thermistor over the range: n, mean, std dev, std error, min, max, rod − TEC offset ± std), `_vs_time.png` (all six thermistors vs time on one graph, range shaded, mean ± std in the legend), `_table.csv` (a, b, n, range, residual mean/std/max), `_corrected.csv` (all raw columns + `rod1_corrected_C`…`rod5_corrected_C`), `_fits.png`, `_residuals.png`.

## Steady-state fin analysis (Phase 4, 11/02 run)

`Python/plot_step_mod7.py` plots all six thermistors through a setpoint step and stops at steady state (|dT/dt| < 0.02 °C/min on every channel, line fit over a trailing 2 min). `Python/fit_steady_state_mod7.py` averages the rods over the final interval of that hold and fits the profile:

```bash
venv/bin/python Python/plot_step_mod7.py data/raw_mod7_20261102_093130.csv --from 20 --to 45
venv/bin/python Python/fit_steady_state_mod7.py data/raw_mod7_20261102_093130.csv --from 20 --to 45 --end 7400
```

Phase 4 is the 45 °C hold after the 20 → 45 °C step at t = 3251 s. The record was still being written when analysed, so it is pinned at `--end 7400`. Sensor positions from analysis-length 0: rods 1–5 at x = 0, 1.0, 3.9, 10.1, 15.2 cm (±1 mm); L = 0.283 m. T∞ = 22.54 ± 0.17 °C is the mean ± std of all six thermistors at t = 0, before any heating. Outputs are in `data/steady_state/`.

### Steady-state interval

The criterion is first met on all six channels at t = 4874 s. The averaging interval is the **final 5 min of Phase 4, t = 7100–7400 s** (425 rows; TEC = 45.000 ± 0.007 °C). It starts 37 min after the criterion is first met and 2.5 min after the disturbance at t ≈ 6830–6950 s (see Room-temperature drift) has settled.

| Sensor | x (cm) | Mean T (°C) | dT/dt over 5 min (°C/min) | Largest 2-min \|dT/dt\| inside (°C/min) |
|--------|--------|-------------|---------------------------|-----------------------------------------|
| Rod 1 | 0.0 | 38.364 | +0.015 | 0.028 |
| Rod 2 | 1.0 | 36.361 | +0.012 | 0.031 |
| Rod 3 | 3.9 | 35.143 | +0.007 | 0.030 |
| Rod 4 | 10.1 | 32.807 | −0.003 | 0.031 |
| Rod 5 | 15.2 | 31.460 | −0.015 | 0.034 |

Over the full 5 min, every rod satisfies |dT/dt| < 0.02 °C/min. Shorter 2-min sub-windows reach 0.03 °C/min, which is fluctuation about a flat level, not a trend: the slope uncertainty from read noise alone is ~0.002 °C/min. The statistical error on each mean is 0.001 °C. The error bar on each sensor is instead the ±0.54 °C scatter of the rod − TEC offsets from the 10/28 equal-temperature check, which dominates.

### Fits

θ = T − T∞. Finite insulated tip: θ = θ₀ cosh(m(L − x))/cosh(mL). Semi-infinite: θ = θ₀ e^(−mx). θ₀ and m are free in both (weighted least squares, 3 dof). The TEC thermistor is on the base, not the rod, and is not fitted.

| Model | m (m⁻¹) | 1/m (m) | θ₀ (°C) | mL | χ²/dof | p |
|-------|---------|---------|---------|----|--------|---|
| Finite, insulated tip | **4.80 ± 0.34 ± 0.12** | **0.208 ± 0.015 ± 0.005** | 15.09 ± 0.38 | 1.36 | 3.57/3 | 0.31 |
| Semi-infinite | 3.64 ± 0.40 ± 0.14 | 0.275 ± 0.030 ± 0.010 | 14.98 ± 0.37 | 1.03 | 4.60/3 | 0.20 |

The first uncertainty is from the fit and the second is systematic (budget below).

- θ vs x with both fits and both sets of residuals: [`raw_mod7_20261102_093130_fin_fits.png`](data/steady_state/raw_mod7_20261102_093130_fin_fits.png)
- Rod temperatures after steady state, with m fitted in every 5-min window: [`raw_mod7_20261102_093130_fin_windows.png`](data/steady_state/raw_mod7_20261102_093130_fin_windows.png)
- Every fit and residual: [`raw_mod7_20261102_093130_fin_results.csv`](data/steady_state/raw_mod7_20261102_093130_fin_results.csv)

**Ignoring the finite end** changes m by **−1.16 m⁻¹ (−24%)** and the decay length 1/m by +0.066 m (+32%).
- That shift is 3.4× the finite fit's statistical σ and 3.2× its total σ (0.36 m⁻¹). It is still 2.2× the two fit σ's combined in quadrature, which is conservative because both fits use the same data.
- The shift is the same in all seven 5-min windows after steady state (−1.10 to −1.17 m⁻¹), while m itself moves by only 0.10 m⁻¹ (std) between windows.
- Over the sensors, the two fitted curves never differ by more than 0.19 °C (a third of one error bar), and χ² rises by only 1.0. The residuals therefore cannot show the error; it appears as a biased m.

### Discussion: error sources and the tip boundary condition

Systematic budget on m (finite fit; semi-infinite in brackets):

| Source | How it was tested | δm (m⁻¹) |
|--------|-------------------|----------|
| Sensor positions ±1 mm | 2000-trial Monte Carlo | 0.023 (0.028) |
| T∞ ± 0.17 °C | refit at T∞ ± σ | 0.047 (0.056) |
| Room drift / stability | std of m across seven 5-min windows, t = 5000–7100 s | 0.10 (0.12) |
| Thermistor offsets | refit with the 10/28 offsets removed | 0.024 (0.028) |
| Tip condition | refit with convective-tip length L + d/4 = 0.2857 m | 0.023 |
| **Total (quadrature)** | | **0.12 (0.14)** |

All of these are smaller than the statistical σ (0.34). None of them is close to the −1.16 m⁻¹ shift from ignoring the finite end.

**Sensor-position error.** Near the base, the profile falls at 0.063 °C per mm. A ±1 mm position error is therefore worth ≤0.06 °C, an order of magnitude below the ±0.54 °C sensor scatter. The Monte Carlo spread in m (0.023 m⁻¹) confirms that position error is negligible. A common shift of the x origin is absorbed almost entirely into θ₀.

**Room-temperature drift.** T∞ was measured once, at the start of the run (09:31). The run then lasted more than 2 h with no ambient sensor.
- Between t ≈ 5000 and 6800 s, every rod kept rising while the TEC held 45.00 °C: rod 1 by 0.44 °C, rod 5 by 0.87 °C. The far sensors rose most, and window-to-window m fell from 5.07 to 4.74 m⁻¹. This is consistent with the room warming, or with h falling as air flow changed, on top of the rod's slow final approach.
- At t ≈ 6830–6950 s there was an abrupt disturbance. Rod 5 dropped 0.24 °C in one sample at t = 6829 s and rod 4 dropped 0.26 °C at t = 6874 s. Rods 1–3 then fell about 0.5 °C over 2 min while the TEC stayed at 45.00 °C. The cause was not logged.
- Changes common to all sensors act like a change in T∞ and are largely absorbed into θ₀. m moved by only ±0.05 for a ±0.17 °C change in T∞, and by 0.10 (std, range 4.74–5.07 m⁻¹) from window to window.
- Fitting T∞ instead of measuring it once would remove this weakness. So would logging room temperature with a spare thermistor.

**Imperfect contact.**
- *TEC to rod:* the TEC base reads 45.00 °C, but the fitted rod base is 22.54 + 15.09 = 37.63 °C. About 7.4 °C, or 33% of the TEC's excess over ambient, is lost across the interface. Forcing θ₀ to the TEC value gives χ² = 366 (finite) and 375 (semi-infinite) for 4 dof, so the "base at TEC temperature" boundary condition is rejected. With θ₀ free, the contact drop changes only the amplitude and does not bias m.
- *Thermistor to rod:* the per-sensor offsets (±0.54 °C) dominate the error budget, and they explain most of the residual pattern. Rod 1 sits +0.74 °C above the fit and rod 2 sits −0.65 °C below it, which matches their 10/28 offsets of +0.94 and −0.43 °C. Removing the offsets lowers χ² from 3.57 to 2.02 and changes m by 0.02 m⁻¹. The 10/28 offsets were measured near 21 °C, not at 31–38 °C, so the correction is used only as a check.

**Tip boundary condition: measured evidence.** No sensor lies beyond x = 15.2 cm (54% of L), so the last 13 cm of the profile, including the tip, is extrapolated. The data constrain the tip only weakly:
1. The insulated-tip model fits slightly better (Δχ² = 1.0, about 1σ).
2. Fitting L as a free parameter gives a best L of 0.18 m. The Δχ² ≤ 1 range is L = 0.16–0.35 m, which includes the real 0.283 m. The semi-infinite limit (L → ∞) is 1.7 above the minimum, disfavoured at only about 1.3σ.
3. An insulated tip and a convective tip cannot be told apart here: replacing L with L + d/4 changes m by 0.023 m⁻¹ (<0.1σ), because the tip face is tiny compared with the side surface.

So the data are **consistent with** an insulated, finite tip but do not establish it independently. The finite fit predicts a tip temperature of θ(L) = θ₀/cosh(mL) = 0.48 θ₀, about 29.8 °C. A thermistor at x = L would test the tip condition directly.

### Comparison with the prediction record

| Assumption | Measured evidence | Verdict |
|------------|-------------------|---------|
| Steady state | 5-min \|dT/dt\| ≤ 0.015 °C/min on every rod; m stable to 0.10 m⁻¹ across seven windows | Supported |
| 1-D fin with uniform h and T∞ | Both models fit with p = 0.2–0.3; residuals follow the sensor offsets, not x | Supported at the ±0.5 °C level |
| Rod base at TEC temperature | 7.4 °C contact drop; χ² = 366 with θ₀ fixed | **Not supported**: θ₀ must be free |
| Insulated tip | Δχ² = 1.0 in favour; free-L range 0.16–0.35 m includes L; no sensor near the tip | Consistent, not directly tested |
| Semi-infinite rod (mL ≫ 1) | mL = 1.36 ± 0.10, so tip θ is still 48% of θ₀; e^(−mx) gives m 24% low (3σ) | **Not supported** |

**The finite insulated-tip model is the more adequate one.** It fits at least as well, it is consistent with the rod's actual length, and the semi-infinite model can only match the sensors by lowering m by 3σ. Any h derived from m² = hP/(kA) would come out 42% low with the semi-infinite fit.

**Prediction record:** _to be added (predicted m, profile and assumptions, compared against the table above)._

**Unexplained discrepancies:**
- After the 10/28 offsets are removed, rod 3 is left −0.66 °C below the fit. The offsets explain rods 1 and 2 but not rod 3.
- The size of the 7.4 °C TEC–rod contact drop. A contact resistance cannot be computed without the rod's k and the heat flow.
- The slow 0.4–0.9 °C rise of the rods between t ≈ 5000 and 6800 s while the TEC was constant, which was larger at the far end.
- The abrupt disturbance at t ≈ 6830–6950 s.
