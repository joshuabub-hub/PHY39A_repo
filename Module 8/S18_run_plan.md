# Module 8 S18 Run Plan

This plan organizes the remaining S18.1-S18.4 work from the Module 8 README
and assignment checklist. It is for the raw-PWM experiment; the separate
Angstrom open-loop/P/PI procedure in `README.md` is a different experiment.

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
| 4 | Positive-only sinusoidal PWM: `period = 100 s`, same `ub` as Run 3, choose `ua > ub` and `ua + ub <= 255` | Keep the requested PWM positive and unclipped. Adjust `ua` toward the intended mean temperature only while monitoring safety. Record any change to `ub` and account for it in the comparison. |

For Run 4, `ua = ub + 5 PWM counts` is only a conservative initial suggestion
for a small positive minimum command, not a validated safe setting. For
example, if the selected `ub` is 50, this gives `ua = 55` and a requested range
of +5 to +105 PWM. Do not reuse the previous `ua = 70, ub = 50` settings:
the 2026-11-16 log recorded 135 cutoff-state samples and a measured TEC
temperature of 60.29 °C with those settings.

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
