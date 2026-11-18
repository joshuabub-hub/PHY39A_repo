Run the GUI from the repo root (use the venv outside iCloud, see Module 7 notes):

```bash
~/.venvs/phy39a_repo/bin/python "Module 8/Python/serial_plot_mod8.py"
```

Module 8 is the Module 7 six-thermistor rig driven with a sinusoidal base temperature (Angstrom method). Control calculations run in the Python GUI; the Arduino reads the sensors, applies signed PWM commands, and enforces the TEC cutoff. Files:

- `Python/serial_plot_mod8.py`: Manual, feedforward-only, P-only, PI, and two diagnostic raw-PWM modes, plus a sinusoidal setpoint `Tset(t) = Ta + Tb sin(2πt/τ)` (τ ≥ 100 s, commanded peak limited to 58 °C), room-temperature entry, and a choice of feedback sensor (TEC or T1). Writes `data/raw_mod8_<time>.csv` and `data/pi_log_mod8_<time>.csv`.
- `Python/feedforward_curve_mod8.py`: inverts the measured susceptibility curves (`data/pwm_steady_state.csv`, from Module 4) into `uff(Tset)`; writes `data/feedforward_uff_mod8.csv/.png`.
- `Python/analyze_angstrom_mod8.py`: boundary metrics, per-sensor amplitude/phase, ordering check, settling criterion, one summary row per run in `data/angstrom_summary_mod8.csv`.
- `Python/calibrate_thermistors_mod8.py`: unchanged copy of the optional relative calibration.

## 1. Channel and safety verification

| Item | Status |
|------|--------|
| Channels | Experimenter confirmed `tec_C` = A0 (embedded TEC thermistor) and `rod1_C`…`rod5_C` = A1…A5 = T1…T5, in increasing distance from the TEC. Temperatures are in °C; time is in seconds. The sketch uses the same conversion for all six channels. |
| Safety limits (sketch) | TEC-temperature software cutoff trips **above** 60 °C and resets **below** 55 °C; a TEC ADC fault outside 10–1013 counts forces output off. PWM is clamped to 0–255. A rod-channel fault reports `nan` but does not itself trip the Arduino cutoff. |
| Physical thermal cutoff | Experimenter reports that it works and cuts off at 60 °C; location and independent test details are not recorded. Do not run near the cutoff. |
| Correction coefficients | The Module 8 GUI and analyzer use raw readings; no Module 8 correction files are present. Two Module 7 calibration tables exist, but their TEC reference varied only from 21.21 to 21.22 °C and their fitted slopes are near zero. They are not validated across the experiment's temperature range and are **not applied**. |
| Common-bath result | Not performed. At the start of the current run, all six channels read 23.71–23.91 °C, a 0.20 °C spread. The experimenter also reports agreement within 1 °C at room temperature. This is not a common-bath test or proof of agreement across the working range. |
| Positions from rod 1 | T1 = 0, T2 = 0.025 m, T3 = 0.050 m, T4 = 0.075 m, T5 = 0.100 m; L = 0.283 m. Positions and analysis length confirmed by the experimenter; position uncertainty not confirmed |
| Initial placement | T1 is in the first hole at x = 0; T2–T5 follow at approximately one-inch intervals. This is the current oscillatory measurement map, separate from the earlier Module 7 stationary-profile map. |

`analyze_angstrom_mod8.py` repeats the ordering check on every sinusoid run (amplitude falls and lag rises from T1 to T5).

### GUI control and logging

Select **Oscillate PWM ±** for `ub sin(2πt/τ)` or **Raw PWM heating** for `ua + ub sin(2πt/τ)`. For the symmetric diagnostic, enter `ub = 100 PWM` and choose a period of 100, 200, or 500 s; press **Start sinusoid**. The requested command ranges from −100 (cooling) to +100 (heating), without feedforward or cooling compensation. The PWM plot shows cooling as negative. Press **Stop sinusoid** to request zero PWM before changing the period. Both modes require `ub > 0`; heating-only also requires `ua > ub`. Heating-only is not temperature-regulated: adjust its settings based on measured TEC temperature, while respecting the cutoff.

Feedforward-only interpolates the measured `pwm_steady_state.csv` curve, shifted so its zero-PWM point matches the entered room temperature. A target outside the measured curve is extrapolated linearly from the nearest measured segment (the PWM is still clamped to ±255). Control is stopped only by the over-temperature cutoff: if the TEC thermistor reads above 58 C, the GUI switches to Manual with PWM 0. P and PI optionally add feedforward to their heating-equivalent controller command. The negative combined command is multiplied by the fitted slope ratio `r = χh/χc` before saturation; negative feedforward is converted to the same units first so it is not compensated twice. Conditional integration checks the compensated candidate against saturation. Manual and diagnostic PWM bypass compensation.

The Arduino still sends its original `DATA,time_s,tec_C,rod1_C,rod2_C,rod3_C,rod4_C,rod5_C,pwm,heat_cool,setpoint_C,safety` record; the GUI writes each accepted raw record unchanged to the raw CSV. The separate PI log records the GUI's mode, waveform parameters, controller output, ratio, observed signed PWM, and all rod readings. Its requested command is computed **after** the measurement and sent for a subsequent sample, while observed PWM is from the current Arduino record; they are not an atomic command/measurement pair. A new Arduino-origin combined record with millisecond timestamps and controller metadata has **not** been implemented. Malformed lines and missing records are reported; after more than three seconds without a record the GUI requests PWM zero. This is not a hardware communication watchdog and cannot stop output if the serial link has failed. The Arduino's independent TEC cutoff remains necessary.

The [placement rationale](https://sethfraden.github.io/Phys39F26-course/labs/lab-09/#choose-sensor-positions-for-the-quantity-being-measured) balances a measurable downstream amplitude against enough separation to resolve phase and amplitude differences. After short- and long-period pilots, move sensors closer if the downstream signal is too small, or farther apart if neighboring changes are too small to resolve. Remeasure and record all positions and uncertainties after any change; retain at least three sensors with measurable amplitude and phase at each selected period. No pilot-based changes have yet been recorded.

**Trial safety:** The experimenter has changed the stop criterion to use the TEC temperature (also called T0), rather than a T1 threshold. The existing Arduino software cutoff forces PWM off above 60 °C and resets only below 55 °C; preserve this hysteresis and the independent physical cutoff. Do not run near the cutoff: choose a lower target and allow for overshoot. Use periods of at least 100 s, monitor sensor validity and safety status, and stop the trial if a safety limit or the physical cutoff is reached. The current GUI permits a commanded sinusoidal peak up to 58 °C; that setpoint limit does not guarantee the measured TEC temperature will stay below the cutoff.

## 2. Prediction: a periodically heated rod

### Model and boundary

Following [Module 7, Part III](https://sethfraden.github.io/Phys39F26-course/labs/lab-08/#model), let the excess temperature be θ(x,t) = T(x,t) − T∞. Here T∞ is the surrounding room temperature: the room is treated as a large reservoir whose temperature is not appreciably changed by the rod. Initially model the rod as semi-infinite, x ≥ 0:

```text
∂θ/∂t = κ ∂²θ/∂x² − νθ
```

The left side is local thermal storage, the first term on the right is axial diffusion, and the second is lateral heat loss to the room. Every term has units K/s. Thermal diffusivity κ = α = k/(ρc) has units m²/s; Module 7 used α for the same quantity. The lateral loss rate ν = hP/(ρcA) has units s⁻¹, where k is thermal conductivity, ρ density, c specific heat, h the lateral heat-transfer coefficient, P the perimeter, and A the cross-sectional area. Assume constant material properties, linear lateral heat loss, constant T∞, and uniform temperature across each cross section.

The measured rod temperature T1 at the first hole defines the analysis base, not the TEC setpoint or its embedded thermistor. For the oscillating component, choose the time origin so that

```text
θosc(0,t) = θb cos(ωt),       ω = 2π/τ,
```

where τ is the period in seconds, ω is in rad/s, and θb is the measured T1 oscillation amplitude. We seek the settled periodic response, after initial transients have decayed. If T1 oscillates about a mean above room temperature, the total excess temperature also has a stationary mean profile: θ = θmean(x) + θosc(x,t). Linearity permits treating the two separately; the boundary above applies to the oscillating component, not necessarily the total excess temperature.

### Qualitative prediction, before solving

Sketch of the **oscillating component** versus time at the base and two increasing distances, 0 < xa < xb. All three rows use the same vertical scale and their own zero line; the symbols are schematic, not measurements:

```text
time →       0               τ
T1           █ ▇ ▄ ▂ ▁ ▂ ▄ ▇ █ ▇ ▄ ▂ ▁
at xa        ▆ ▆ ▆ ▄ ▂ ▂ ▂ ▄ ▆ ▆ ▆ ▄ ▂
at xb        ▄ ▅ ▅ ▅ ▄ ▃ ▃ ▃ ▄ ▅ ▅ ▅ ▄
```

Predict that all locations eventually oscillate at the **same period** as T1, but their amplitudes decrease and their peaks occur later as distance increases. Their mean temperatures need not be equal: the stationary mean profile is separate from the oscillation. A **shorter period** should make the oscillation attenuate more rapidly with distance and increase the phase lag at a fixed distance. The corresponding time delay need not increase: phase lag and delay in seconds are related by Δt = Δφ/ω.

### Check against the solution

Write θosc = Re[θb exp(iωt − qx)], with q = a + ib and a > 0 so the response remains bounded as x → ∞. Substitution gives κq² = ν + iω. For ω > 0,

```text
a = sqrt((sqrt(ν² + ω²) + ν)/(2κ))
b = sqrt((sqrt(ν² + ω²) − ν)/(2κ))

θosc(x,t) = θb exp(−ax) cos(ωt − bx).
```

Thus the amplitude ratio relative to T1 is exp(−ax), the phase lag is bx radians, and the delay is bx/ω seconds. Both a and b increase with ω, supporting the shorter-period prediction for attenuation and phase. Compare phases without confusing a lag modulo one cycle with the accumulated lag; unwrap phases where necessary.

This is a **semi-infinite** prediction, not a guarantee for the actual finite rod. The tip's importance for an oscillation depends on the period. Departures from the sketch can reflect finite-length effects, transients, imperfect base forcing, sensor uncertainty, or limitations of the model.

### Quantitative predictions

Use the Module 7 planning values k = 167 W/(m K) and h = 10 W/(m² K), with estimated aluminum properties ρ = 2700 kg/m³ and c = 900 J/(kg K). These are **assumed planning inputs**, not measured properties. For the confirmed diameter d = 0.011 m, P/A = 4/d, giving

```text
κ = k/(ρc) = 6.87 × 10⁻⁵ m²/s
ν = 4h/(dρc) = 1.50 × 10⁻³ s⁻¹.
```

The periods below are examples, not claims about the current run. At 150 s, ω = 0.04189 rad/s, a = 17.77 m⁻¹ and b = 17.15 rad/m. At 100 s, ω = 0.06283 rad/s, a = 21.64 m⁻¹ and b = 21.13 rad/m. The resulting predictions use measured T1 as the base; multiply a listed amplitude ratio by the fitted T1 amplitude to obtain the amplitude in °C or K.

| Sensor | x (m) | 150 s amplitude / T1 | 150 s phase lag (°) | 150 s delay (s) | 100 s amplitude / T1 | 100 s phase lag (°) | 100 s delay (s) |
|--------|-------|----------------------|---------------------|-----------------|----------------------|---------------------|-----------------|
| T1 | 0.000 | 1.000 | 0.0 | 0.0 | 1.000 | 0.0 | 0.0 |
| T2 | 0.025 | 0.641 | 24.6 | 10.2 | 0.582 | 30.3 | 8.4 |
| T3 | 0.050 | 0.411 | 49.1 | 20.5 | 0.339 | 60.5 | 16.8 |
| T4 | 0.075 | 0.264 | 73.7 | 30.7 | 0.197 | 90.8 | 25.2 |
| T5 | 0.100 | 0.169 | 98.3 | 40.9 | 0.115 | 121.1 | 33.6 |

For example, at T5 the shorter period lowers the predicted amplitude ratio from 0.169 to 0.115 and increases the phase lag from 98.3° to 121.1°, even though the delay in seconds decreases. At these periods aL is about 5.0 and 6.1, respectively, so the oscillation is already strongly attenuated by the tip in the semi-infinite prediction. That does not establish the tip condition or the validity of the stationary profile.

For an absolute-temperature prediction, a room-temperature estimate and the measured T1 mean are also needed. With an insulated-tip assumption the stationary component is

```text
Tmean(x) = T∞ + (T1,mean − T∞) cosh[m(L − x)] / cosh(mL),
m = sqrt(ν/κ) = 4.67 m⁻¹.
```

Add θosc(x,t) to this mean, using the fitted T1 amplitude and phase. The beginning of `raw_mod8_20261109_103950.csv` has PWM off and rod readings 23.71–23.91 °C; their first-sample average is 23.83 °C. Use this only as a **room-temperature proxy** for that run, assuming the rod was equilibrated with the room; the log does not independently measure room temperature. Do not apply it to a different day's run.

### Return to the sketch: current run

The current `20261109_103950` recording, checked through 522.25 s, was in MANUAL mode with PWM = 0 and a constant 30 °C setpoint. It therefore supplies a baseline, **not a sinusoidal pilot**. Measured amplitudes, lags, and a comparison with the predictions cannot yet be determined from it. The prediction table above uses the confirmed current sensor positions and assumed material and loss parameters; it does not use a previous run.

For a settled pilot, plot measured T1 and two farther rod temperatures on the same time axis, subtracting each fitted mean and drift to compare oscillations. Record the actual period, window, amplitudes and phase lags relative to T1, and compare with the table. Check base-waveform quality and settling before interpreting disagreements. Repeat at a shorter period, provided the signal remains measurable. The analyzer's printed diffusivity estimate assumes zero side loss; it is not the κ estimate for the model above when ν is nonzero.

## 3. Feedforward (steady-state inversion)

The GUI's feedforward curve was calibrated on the TEC alone, before the current rod configuration; it is a controller input, not a measurement of this run. Enter the measured room temperature in the GUI. The attached rod adds side and axial loss, so expect extra droop in open loop.

### Open-loop sinusoid: prediction vs. measurement

Run `20261118_105010`, second sinusoid segment (started at 1139.8 s), feedforward-only (OPEN) with `Tset(t) = 40 + 16 sin(2πt/100 s)` °C, feedback and temperature from `tec_C`.

| | u_a (PWM) | u_b (PWM) | Mean temperature (°C) | Oscillation amplitude (°C) | Temperature phase lag relative to set point (°) |
|---|---|---|---|---|---|
| Steady-state prediction | 31.3 | 31.0 | 40.0 | 16.0 | 0 |
| Measured response | 31.2 | 31.4 | 40.9 | 4.03 | 79.0 |

- **Prediction:** u_a = (T_a − T_room)/χ_h and u_b = T_b/χ_h, using the Module 4 heating susceptibility χ_h = 0.516 °C/PWM. T_room = 23.85 °C is the average of all six channels during the first 9 s of the log, when PWM was 0 (range 23.66–23.97 °C). The room-temperature entry in the GUI for this segment, inferred from the logged feedforward (the entry itself is not logged), was ≈ 23.8 °C, consistent with this value. The predicted temperature response follows from the same steady-state susceptibility: mean = T_room + χ_h·u_a = 23.85 + 0.516 × 31.3 = 40.0 °C, and oscillation amplitude = χ_h·u_b = 0.516 × 31.0 = 16.0 °C. A steady-state (quasi-static) model assumes the temperature follows the command instantly, so the predicted phase lag is 0°.
- **Measured:** least-squares fit of `mean + A sin(ωt) + B cos(ωt)` at the commanded 100 s period over the 9 complete steady-state cycles, 1639.8–2539.8 s (1282 samples). Each of these cycles meets the settling criterion relative to the previous cycle (change in mean < 0.15 °C, amplitude < 2%, phase < 2°). The first five cycles (from 1139.8 s) were still warming (fitted means 33.5, 38.4, 39.8, 40.3, 40.6 °C) and are excluded. Per-cycle fits over the steady window range from 40.69 to 41.12 °C in mean (a slow upward drift of ≈ 0.4 °C over 9 cycles), 4.02–4.04 °C in amplitude, and 78.5–79.5° in lag. u_a and u_b are the mean and fundamental amplitude of the applied signed PWM (`u_applied`, range 0 to +63, so it never switched to cooling).
- The feedforward command matches the prediction (u_a, u_b within about 1%), and the mean temperature comes within 1 °C of T_a. The oscillation does not: at τ = 100 s the TEC's thermal lag cuts the amplitude to 25% of the set-point amplitude and delays it by 79° (≈ 22 s). The quasi-static prediction holds for the mean but not for the oscillation at this period.
- An earlier sinusoid segment in the same log (18.8–625 s) had only one cycle that met the settling criterion, and its GUI room entry was ≈ 22 °C, giving u_a ≈ 34.7 PWM and mean ≈ 42.3 °C. It is not used here.

### P / PI control with the sinusoid

All runs: `Tset(t) = 40 + 16 sin(2πt/τ)` °C, feedforward on, room entry 23.8 °C, feedback from `tec_C`. Requested amplitude is 16 °C. Each row is fitted at the commanded period over complete cycles that meet the settling criterion (change from the previous cycle in mean < 0.15 °C, amplitude < 2%, phase < 2°). RMS tracking error is `sqrt(mean((Tset − T_TEC)²))` over the same samples. PWM saturation is the fraction of samples with |applied PWM| = 255.

| Period (s) | Trial | Kp (PWM/°C) | Ki (PWM/(°C·s)) | Sample intervals | Mean TEC temp (°C) | Amplitude ratio (fitted/requested) | Phase lag (°) | RMS tracking error (°C) | PWM saturation | Notes |
|---|---|---|---|---|---|---|---|---|---|---|
| 100 | P only | 3 | 0 | 515.6–1115.6 s (6 cycles, 852 samples) | 40.2 | 0.554 (8.87 / 16 °C) | 58.0 (≈ 16 s) | 9.6 | 0% (applied −140 to +100) | Run `20261118_114015`. Settled from the 3rd cycle. Compared with open loop (0.25, 79°), amplitude ratio more than doubled, lag fell by 21°. Matches the linear prediction for Kp = 3 (0.56, 60°). TEC range 31.6–49.2 °C. |
| 100 | Initial PI | | | | | | | | | |
| 100 | PI tuning | | | | | | | | | |
| 200 | PI with selected 100 s gains | | | | | | | | | |
| 200 | PI retuning if needed | | | | | | | | | |
| 300 | PI with selected 200 s gains | | | | | | | | | |
| 300 | PI tuning if needed | | | | | | | | | |

Conventions: PWM > 0 with direction HEAT drives pin 9 (heating); direction COOL drives pin 10 (cooling); the GUI shows applied PWM from the Arduino record and the sign from `heat_cool` (1 = heat). Confirm with TEC power off and a small command before energizing.

## Run procedure (hardware steps still to do)

1. Start the GUI, confirm six temperatures, mode, setpoint and applied PWM update and a new `raw_mod8_*` / `pi_log_mod8_*` pair appears. Enter the measured room temperature.
2. Select Ta and Tb with a target well below the TEC cutoff to leave room for overshoot, and choose τ ≥ 100 s. Run **Open loop**, **P-only**, and **PI** with the same drive settings (same Ta, Tb, period, feedback sensor and feedforward setting), for at least 8 cycles each unless a stop condition is reached. Inspect measured TEC and T1, not just the command; a lower commanded peak does not guarantee the TEC stays below the cutoff.
3. For each run, from the repo root: `~/.venvs/phy39a_repo/bin/python "Module 8/Python/analyze_angstrom_mod8.py" <stamp> --t0 <s> --t1 <s> --period <s> --label OPEN|P|PI --positions 0 0.025 0.05 0.075 0.1`, then run the script with `--compare`. The explicit positions are essential: the script's defaults still use the old T4 and T5 positions.
4. If no mode gives an adequate T1 sinusoid, try P = 150 s or Tb = 10 °C and retune Kp, Ki. Never use P < 100 s (the GUI enforces it).
5. Keep ≥ 5 complete settled cycles (settling criterion in `analyze_angstrom_mod8.py`: per-cycle change in amplitude < 2%, phase < 2°, mean < 0.15 °C on every sensor) with measurable amplitude and phase on ≥ 3 rod sensors.
6. Pick a second period from the attenuation, phase lag and base tracking; repeat, wait for the transient to settle, retain ≥ 5 cycles.
