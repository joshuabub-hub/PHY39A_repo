# Module 8 S18 Run Plan

This plan organizes the remaining S18.1-S18.4 work from the Module 8 README
and assignment checklist. It is for the raw-PWM experiment; the separate
Angstrom open-loop/P/PI procedure in `README.md` is a different experiment.

## Status update (2026-11-19)

The new run pair is `data/raw_mod8_20261119_102636.csv` and
`data/pi_log_mod8_20261119_102636.csv`. The experimenter reports room
temperature was approximately 22.4 °C; treat this as an estimate.

| Run | Finding | Action |
|---|---|---|
| Zero-centered, 200 s, `ua=0`, `ub=50` | Five consecutive settled cycles are available in the recorded interval 2905.86-3904.98 s (about 5 periods). | No repeat needed for the S18.3 experimental fit. |
| Zero-centered, 300 s, `ua=0`, `ub=50` | Seven complete cycles were recorded, but only the final cycle-to-cycle comparison met the settling checks. | Repeat or extend. Record until the cycle checks show at least five consecutive settled cycles. |
| Zero-centered, 100 s, `ua=0`, `ub=50` | Five complete cycles were recorded; none of the cycle-to-cycle comparisons met all settling checks. | Repeat or extend. Record until the cycle checks show at least five consecutive settled cycles. |
| Positive-only, 100 s | Attempts at `ua=55, ub=50` and `ua=55, ub=40` did not provide five settled cycles. The TEC reading reached about 58 °C. | Do not repeat these settings. Reassess the positive-only drive with the instructor/operator and use a lower mean and/or amplitude with close temperature monitoring. No safe positive-only setting has been established by these logs. |

The 200 s five-cycle fit and the model calculations are documented in
`S18_results_20261119.md`. The reported room temperature is not a calibrated
measurement, and the 200 s run's mean-minus-room value should be presented as
approximate.

### Runs still needed

1. **300 s zero-centered:** `ua=0`, initially `ub=50`; retain this amplitude
   only if temperatures remain comfortably within the limits. Extend the run
   beyond the previous 7.5-cycle recording until at least five consecutive
   complete cycles pass the settling checks. Reduce `ub` and record the change
   if needed for safety.
2. **100 s zero-centered:** `ua=0`, initially `ub=50`; extend beyond the prior
   5.9-cycle recording until at least five consecutive complete cycles pass
   the settling checks. Reduce `ub` and record the change if needed.
3. **100 s positive-only:** do not reuse `ua=55` with either `ub=50` or
   `ub=40`. First review the near-cutoff results with the instructor/operator.
   If approved to proceed, choose a lower positive-only mean and/or amplitude,
   keep `ua > ub` and `ua + ub <= 255`, and use a short monitored pilot before
   attempting a settled run. Stop well before either thermal limit; there is
   no verified-safe numeric setting in the present data. If `ub` differs from
   the zero-centered baseline, record the change and account for it in the
   comparison.

The common-bath check and S18.2's required single complete Arduino record
remain outstanding unless completed and documented separately.

## Before running

### S18.1: verify channels, placement, and safety

- Confirm that TEC is A0 and T1-T5 are A1-A5, in order along the rod. Confirm
  the displayed and recorded temperatures are in °C.
- Record the current sensor positions and their measurement uncertainties.
  The documented nominal positions are T1 = 0 m, T2 = 0.025 m, T3 = 0.050 m,
  T4 = 0.075 m, and T5 = 0.100 m from the rod base.
- Perform and document a common-bath check. The existing room-temperature
  readings are not a substitute for this test.
- Document any correction coefficients used. Current Module 8 files use raw
  readings; do not apply unvalidated Module 7 coefficients.
- Confirm the software cutoff and physical thermal cutoff are active. The
  Arduino TEC cutoff trips above 60 °C and resets below 55 °C. These are
  protection limits, not operating targets. Keep the measured rod-base
  temperature at or below 56 °C, allow margin for overshoot, and stop if a
  safety limit or physical cutoff is reached.
- Do not use a forcing period shorter than 100 s.

### S18.2: verify display and recording

- Connect the Arduino and start the GUI. Verify that TEC and all five rod
  temperatures, setpoint, control mode, and PWM update plausibly.
- Confirm the raw local file contains every complete record received.
- The requested assignment record contains:
  `time_ms,run_state,control_mode,step,Ta_C,Tb_C,period_s,setpoint_C,feedforward_pwm,TEC_C,T1_C,T2_C,T3_C,T4_C,T5_C,controller_pwm,heating_to_cooling_ratio,signed_pwm`
- Current behavior is not yet equivalent: the Arduino sends a shorter record,
  while some GUI metadata is saved in a separate PI log. Before treating S18.2
  as complete, either implement and document the required single-record format
  or confirm an accepted alternative with the instructor. Preserve startup
  transients, mode/frequency changes, and safety events; do not overwrite raw
  data with cleaned files.

## Run sequence

Use the same rig configuration and record measured room temperature, sensor
map, run settings, and safety status. Let the apparatus return to a stable
starting condition before each run. Monitor TEC and T1 continuously.

| Run | Mode and requested settings | Purpose and notes |
|---|---|---|
| 1 | Zero-centered sinusoidal PWM: `ua = 0`, `ub = 50 PWM counts`, `period = 300 s` | Initial safety check at the longest required period. Reduce `ub` if needed to maintain safe measured temperatures; record the selected value. |
| 2 | Zero-centered: `ua = 0`, same selected `ub` as Run 1, `period = 200 s` | Keep amplitude fixed. |
| 3 | Zero-centered: `ua = 0`, same selected `ub`, `period = 100 s` | Keep amplitude fixed. This is the S18.4 baseline. |
| 4 | Positive-only sinusoidal PWM: `period = 100 s`, same `ub` as Run 3 if approved safe, choose `ua > ub` and `ua + ub <= 255` | Proceed only after reviewing the near-cutoff results with the instructor/operator. No positive-only parameter has been verified safe. Do not reuse `ua = 55` with `ub = 50` or `ub = 40`; those runs reached about 58 °C at the TEC. If approved, use a lower mean and/or amplitude, pilot cautiously, and record any settings change for the comparison. |

The assignment suggests bringing the positive-only mean near 40 °C, but safety
takes priority. Use a lower mean or reduce the amplitude if needed; a requested
setpoint or command does not guarantee the measured TEC temperature will stay
below its limit.

For every run:

- Keep all six temperatures and applied signed PWM visible and logged.
- Wait for startup transients to decay, then retain at least five complete
  settled cycles where safe and practical. Do not continue a run to meet a
  cycle count after a stop condition occurs.
- Save the raw CSV unchanged, plus the settings, room temperature, run start
  and end times, any safety events, and observations.
- If sensor readings are invalid, the safety state changes, or a cutoff is
  reached, stop the trial and document it.

## Analysis and deliverables

### S18.3: zero-centered runs

For each 300, 200, and 100 s run:

- Plot measured TEC temperature and signed PWM on aligned time axes.
- Fit the settled TEC temperature to obtain mean, amplitude, and phase lag
  relative to PWM. Report mean minus room temperature.
- Complete the experimental table for all three periods.
- In the Module 6 one-lump model, use room and initial temperatures of 22 °C,
  `tau_th = 80 s`, `chi_h = 0.46 °C/PWM`, `ua = 0`, and the selected fixed
  `ub`. Complete the six requested cases: periods 100, 200, and 300 s with
  `chi_c = 0.23` and `0.46 °C/PWM`.
- Record simulated mean minus room, fundamental amplitude, phase lag, and
  residual amplitude. Save aligned plots for both susceptibility settings at
  one common period; explain the equal-susceptibility result and compare model
  with measurements.

### S18.4: positive-only comparison

- Compare the settled 100 s positive-only run with the 100 s zero-centered
  baseline. Use the applied `ua` and `ub`, not just requested values.
- Complete both experimental and simulation tables with fundamental and
  residual amplitudes.
- Save aligned PWM/temperature/residual plots and explain whether positive-only
  forcing reduced waveform distortion.
- If `ub` had to change for safety, state that explicitly and account for it
  in the comparison.

Keep all original records, including startup and safety events, alongside
plots, tables, predictions, and written observations.
