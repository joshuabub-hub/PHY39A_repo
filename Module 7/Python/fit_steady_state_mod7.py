"""Fit the steady-state rod profile with the finite insulated-tip and semi-infinite fin models.

With theta(x) = T(x) - T_inf, the two models are

    finite, insulated tip:  theta = theta0 * cosh(m (L - x)) / cosh(m L)
    semi-infinite:          theta = theta0 * exp(-m x)

Phase 4 is the hold that follows the --from -> --to setpoint step. Each rod
thermistor is averaged over the final --window seconds of that record (ending
at --end, default the last row), after checking that every channel satisfies
|dT/dt| < STEADY_RATE_C_PER_MIN over that interval. theta0 and m are both free;
the TEC-base thermistor is not on the rod and is not used. Weighted least
squares: theta0 is linear, so for each trial m it is solved exactly and chi^2
is minimized over m on a fine grid. Parameter errors come from the Jacobian.

Per-sensor uncertainty = sqrt(interval std error^2 + SENSOR_SIGMA_C^2), where
SENSOR_SIGMA_C is the scatter of the rod - TEC offsets from the 10/28
equal-temperature check (README, Calibration).

Systematic checks (each refits both models): T_inf +/- its scatter, sensor
positions jittered by SENSOR_X_SIGMA_M (Monte Carlo), the 10/28 offsets
removed, every earlier non-overlapping window after steady state (room drift),
the convective-tip corrected length L + d/4, and a fit with L free (tip test).

Outputs in Module 7/data/steady_state/:
  <raw name>_fin_fits.png       theta vs x with both fits + residuals
  <raw name>_fin_windows.png    rod temperatures and the fitted m per window
  <raw name>_fin_results.csv    every fit: m, 1/m, theta0, chi^2, mL, tip ratio

Example (run from the Module 7 folder):
  venv/bin/python Python/fit_steady_state_mod7.py data/raw_mod7_20261102_093130.csv --from 20 --to 45 --end 7400
"""

import argparse
import csv
import math
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from plot_step_mod7 import (ROD_COLORS, STEADY_RATE_C_PER_MIN, find_step, find_steady_time,
                            load_csv, trailing_slope)

ROD_CHANNELS = ["rod1_C", "rod2_C", "rod3_C", "rod4_C", "rod5_C"]
SENSOR_X_M = np.array([0.0, 1.0, 3.9, 10.1, 15.2]) / 100  # from analysis-length 0
SENSOR_X_SIGMA_M = 0.001  # positions read to the nearest mm; thermistor bead ~mm
ROD_LENGTH_M = 0.283  # analysis length (README, Rod properties)
ROD_DIAMETER_M = 0.011

# Mean of all six thermistors at t = 0 of the 11/02 run, before any heating.
T_INF_C = 22.54
T_INF_SIGMA_C = 0.17  # std of those six readings

# 10/28 equal-temperature check: rod - TEC offsets (README, Calibration).
CAL_OFFSETS_C = np.array([0.9406, -0.4337, 0.7638, 0.3055, 0.1307])
SENSOR_SIGMA_C = float(np.std(CAL_OFFSETS_C, ddof=1))

M_GRID = np.linspace(0.1, 60.0, 60_000)  # 1/m
FREE_L_GRID = np.linspace(0.16, 3.0, 285)  # m, must exceed the last sensor
N_POSITION_TRIALS = 2000

OUTPUT_DIR = Path(__file__).resolve().parents[1] / "data" / "steady_state"


def finite_shape(m, x, length=ROD_LENGTH_M):
    return np.cosh(m * (length - x)) / np.cosh(m * length)


def semi_infinite_shape(m, x):
    return np.exp(-m * x)


MODELS = {
    "finite (insulated tip)": finite_shape,
    "semi-infinite": semi_infinite_shape,
}


def chi2_sf(chi2, dof):
    """P(chi^2_dof > chi2) for dof = 2 or 3 (closed forms)."""
    if dof == 2:
        return math.exp(-chi2 / 2)
    return math.erfc(math.sqrt(chi2 / 2)) + math.sqrt(2 * chi2 / math.pi) * math.exp(-chi2 / 2)


def profile_chi2(shape, theta, sigma, x):
    """chi^2 and best theta0 on M_GRID for theta = theta0 * shape(m, x)."""
    weights = 1 / sigma**2
    g = shape(M_GRID[:, None], x[None, :])
    theta0 = (g * theta * weights).sum(axis=1) / (g * g * weights).sum(axis=1)
    chi2 = (((theta - theta0[:, None] * g) / sigma) ** 2).sum(axis=1)
    return chi2, theta0


def fit_model(shape, theta, sigma, x=SENSOR_X_M):
    """Weighted LSQ for theta = theta0 * shape(m, x). Returns a dict of results."""
    chi2, theta0 = profile_chi2(shape, theta, sigma, x)
    k = int(np.argmin(chi2))
    if k in (0, len(M_GRID) - 1):
        raise SystemExit("chi^2 minimum is at the edge of M_GRID; widen it.")
    m, theta0 = M_GRID[k], theta0[k]

    h = 1e-6
    jacobian = np.column_stack([
        theta0 * (shape(m + h, x) - shape(m - h, x)) / (2 * h),
        shape(m, x),
    ]) / sigma[:, None]
    covariance = np.linalg.inv(jacobian.T @ jacobian)
    m_err, theta0_err = np.sqrt(np.diag(covariance))
    dof = len(theta) - 2
    return {
        "m": m, "m_err": m_err, "decay_length": 1 / m, "decay_length_err": m_err / m**2,
        "theta0": theta0, "theta0_err": theta0_err,
        "corr": covariance[0, 1] / (m_err * theta0_err),
        "chi2": chi2[k], "dof": dof, "p": chi2_sf(chi2[k], dof),
        "mL": m * ROD_LENGTH_M, "mL_err": m_err * ROD_LENGTH_M,
        "residuals": theta - theta0 * shape(m, x),
    }


def free_length_profile(theta, sigma):
    """Minimum chi^2 over (m, theta0) for each trial insulated-tip length L."""
    return np.array([profile_chi2(lambda m, x: finite_shape(m, x, length), theta, sigma,
                                  SENSOR_X_M)[0].min() for length in FREE_L_GRID])


def interval_means(data, start, end):
    """Mean, std error, rows, and full-interval dT/dt (°C/min) of each rod over (start, end]."""
    time = data["time_s"]
    rows = (time > start) & (time <= end)
    temps = np.column_stack([data[c][rows] for c in ROD_CHANNELS])
    good = np.all(np.isfinite(temps), axis=1)
    temps, t = temps[good], time[rows][good]
    rates = np.array([np.polyfit(t, temps[:, k], 1)[0] * 60 for k in range(temps.shape[1])])
    return temps.mean(axis=0), temps.std(axis=0, ddof=1) / np.sqrt(len(temps)), len(temps), rates


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("raw_csv", type=Path)
    parser.add_argument("--from", dest="old", type=float, required=True,
                        help="setpoint before the step (°C)")
    parser.add_argument("--to", dest="new", type=float, required=True,
                        help="setpoint after the step (°C)")
    parser.add_argument("--end", type=float, help="end of the record to use (s); default last row")
    parser.add_argument("--window", type=float, default=300.0, help="averaging interval (s)")
    args = parser.parse_args()

    data = load_csv(args.raw_csv)
    pi_log = load_csv(args.raw_csv.with_name(args.raw_csv.name.replace("raw_", "pi_log_", 1)))
    _, step_time = find_step(pi_log, args.old, args.new)
    time = data["time_s"]
    end = args.end if args.end is not None else time[-1]
    end = time[time <= end][-1]
    later_setpoints = pi_log["setpoint_C"][(pi_log["time_s"] > step_time) & (pi_log["time_s"] <= end)]
    if np.any(later_setpoints != args.new):
        raise SystemExit("Setpoint changed after the step; --end must stay inside Phase 4.")
    start = end - args.window

    first_steady = find_steady_time({k: v[time <= end] for k, v in data.items()}, step_time)
    if first_steady is None or start < first_steady:
        raise SystemExit(f"Final interval starts at {start:.0f} s, before steady state "
                         f"(first met at {first_steady} s).")

    # Steady-state check over the final interval: the line fit over the whole
    # interval, and every trailing 2-min slope inside it.
    mean_c, std_error_c, n_rows, rates = interval_means(data, start, end)
    in_window = time[(time > start + 120) & (time <= end)]
    worst_trailing = np.array([max(abs(trailing_slope(time, data[c], e)) for e in in_window)
                               for c in ROD_CHANNELS])
    tec = data["tec_C"][(time > start) & (time <= end)]
    print(f"Phase 4: setpoint {args.new:g} °C from t = {step_time:.0f} s to {end:.0f} s "
          f"(criterion first met at t = {first_steady:.0f} s)")
    print(f"Final interval t = {start:.0f}-{end:.0f} s, {n_rows} rows, "
          f"TEC = {tec.mean():.3f} ± {tec.std(ddof=1):.3f} °C")
    print(f"{'channel':8s} {'x (cm)':>6s} {'T (°C)':>8s} {'stat':>6s} {'dT/dt 5min':>11s} "
          f"{'max 2min':>9s}  (°C/min, limit {STEADY_RATE_C_PER_MIN})")
    for c, x, t, se, r, w in zip(ROD_CHANNELS, SENSOR_X_M, mean_c, std_error_c, rates, worst_trailing):
        print(f"{c:8s} {x * 100:6.1f} {t:8.3f} {se:6.3f} {r:+11.4f} {w:9.4f}")
    passes = np.all(np.abs(rates) < STEADY_RATE_C_PER_MIN)
    print(f"5-min criterion {'MET' if passes else 'NOT MET'} for all rods; "
          f"strictest 2-min check {'met' if np.all(worst_trailing < STEADY_RATE_C_PER_MIN) else 'not met'} "
          f"everywhere inside the interval")

    sigma = np.sqrt(std_error_c**2 + SENSOR_SIGMA_C**2)
    theta = mean_c - T_INF_C
    results = {}

    def run(case, theta_case, x=SENSOR_X_M, sigma_case=sigma):
        for name, shape in MODELS.items():
            results[(case, name)] = fit_model(shape, theta_case, sigma_case, x)

    run("nominal", theta)
    run(f"T_inf {T_INF_C - T_INF_SIGMA_C:.2f} °C", mean_c - (T_INF_C - T_INF_SIGMA_C))
    run(f"T_inf {T_INF_C + T_INF_SIGMA_C:.2f} °C", mean_c - (T_INF_C + T_INF_SIGMA_C))
    run("10/28 offsets removed", theta - CAL_OFFSETS_C)

    # Earlier non-overlapping windows after steady state: drift in room/rod.
    window_ends = np.arange(end - args.window, first_steady + args.window - 1, -args.window)[::-1]
    window_fits = []
    for w_end in window_ends:
        w_mean, w_se, _, w_rates = interval_means(data, w_end - args.window, w_end)
        w_sigma = np.sqrt(w_se**2 + SENSOR_SIGMA_C**2)
        w_fit = fit_model(finite_shape, w_mean - T_INF_C, w_sigma)
        w_semi = fit_model(semi_infinite_shape, w_mean - T_INF_C, w_sigma)
        window_fits.append((w_end, w_mean, w_rates, w_fit, w_semi))
        results[(f"window ending {w_end:.0f} s", "finite (insulated tip)")] = w_fit
        results[(f"window ending {w_end:.0f} s", "semi-infinite")] = w_semi

    # Sensor positions jittered by SENSOR_X_SIGMA_M.
    rng = np.random.default_rng(39)
    position_m = {name: [] for name in MODELS}
    for _ in range(N_POSITION_TRIALS):
        x_trial = np.clip(SENSOR_X_M + rng.normal(0, SENSOR_X_SIGMA_M, len(SENSOR_X_M)), 0, None)
        for name, shape in MODELS.items():
            chi2, _ = profile_chi2(shape, theta, sigma, x_trial)
            position_m[name].append(M_GRID[np.argmin(chi2)])
    position_m_std = {name: float(np.std(v)) for name, v in position_m.items()}

    # Tip boundary condition: convective-tip corrected length, and L free.
    corrected_length = ROD_LENGTH_M + ROD_DIAMETER_M / 4
    results[(f"L_c = L + d/4 = {corrected_length:.4f} m", "finite (insulated tip)")] = fit_model(
        lambda m, x: finite_shape(m, x, corrected_length), theta, sigma)
    length_chi2 = free_length_profile(theta, sigma)
    best_length = FREE_L_GRID[np.argmin(length_chi2)]
    within_1 = FREE_L_GRID[length_chi2 <= length_chi2.min() + 1]
    chi2_at_l = np.interp(ROD_LENGTH_M, FREE_L_GRID, length_chi2)
    print(f"\nL = {ROD_LENGTH_M} m, T_inf = {T_INF_C} ± {T_INF_SIGMA_C} °C, "
          f"sensor sigma = {SENSOR_SIGMA_C:.3f} °C, position sigma = {SENSOR_X_SIGMA_M * 1000:.0f} mm")
    print(f"{'case':30s} {'model':23s} {'m (1/m)':>15s} {'1/m (m)':>15s} {'theta0 (°C)':>15s} "
          f"{'mL':>5s} {'chi2/dof':>9s} {'p':>5s}")
    for (case, name), r in results.items():
        print(f"{case:30s} {name:23s} {r['m']:7.3f} ± {r['m_err']:5.3f} "
              f"{r['decay_length']:6.3f} ± {r['decay_length_err']:5.3f} "
              f"{r['theta0']:7.3f} ± {r['theta0_err']:5.3f} {r['mL']:5.2f} "
              f"{r['chi2']:5.2f}/{r['dof']} {r['p']:5.2f}")

    finite = results[("nominal", "finite (insulated tip)")]
    semi = results[("nominal", "semi-infinite")]
    window_m = np.array([f[3]["m"] for f in window_fits])
    window_semi_m = np.array([f[4]["m"] for f in window_fits])
    x_span = np.linspace(0, SENSOR_X_M[-1], 500)
    curve_gap = np.abs(finite["theta0"] * finite_shape(finite["m"], x_span)
                       - semi["theta0"] * semi_infinite_shape(semi["m"], x_span)).max()
    m_shift = semi["m"] - finite["m"]
    print("\nIgnoring the finite end (nominal):")
    print(f"  m shift = {m_shift:+.3f} 1/m ({100 * m_shift / finite['m']:+.0f}%) = "
          f"{abs(m_shift) / finite['m_err']:.1f} x finite-fit sigma, "
          f"{abs(m_shift) / math.hypot(finite['m_err'], semi['m_err']):.1f} x combined sigma")
    print(f"  1/m shift = {semi['decay_length'] - finite['decay_length']:+.3f} m")
    print(f"  delta chi^2 (semi - finite) = {semi['chi2'] - finite['chi2']:+.2f}; "
          f"max curve difference over sensors = {curve_gap:.3f} °C")
    print(f"  tip ratio 1/cosh(mL) = {1 / np.cosh(finite['mL']):.3f}; finite/semi shape at x5 "
          f"= {finite_shape(finite['m'], SENSOR_X_M[-1]) / semi_infinite_shape(finite['m'], SENSOR_X_M[-1]):.3f}")
    print("Systematics on m (finite / semi-infinite):")
    for label, key in [("T_inf", "T_inf"), ("offsets removed", "10/28")]:
        for name in MODELS:
            shifts = [r["m"] - results[("nominal", name)]["m"]
                      for (case, n), r in results.items() if n == name and case.startswith(key)]
            print(f"  {label:16s} {name:23s} max |dm| = {max(abs(s) for s in shifts):.3f} 1/m")
    for name in MODELS:
        print(f"  {'positions':16s} {name:23s} std(m) = {position_m_std[name]:.3f} 1/m")
    print(f"  {'window-to-window':16s} finite m = {window_m.min():.2f}-{window_m.max():.2f} "
          f"(std {window_m.std(ddof=1):.2f}); semi m = {window_semi_m.min():.2f}-{window_semi_m.max():.2f} "
          f"(std {window_semi_m.std(ddof=1):.2f}); semi - finite = "
          f"{(window_semi_m - window_m).min():+.2f} to {(window_semi_m - window_m).max():+.2f}")
    print(f"Tip test, L free: best L = {best_length:.2f} m, Δχ² ≤ 1 for L = "
          f"{within_1.min():.2f}-{within_1.max():.2f}{'+' if within_1.max() >= FREE_L_GRID[-1] else ''} m; "
          f"χ² at L = {ROD_LENGTH_M} m is {chi2_at_l - length_chi2.min():+.2f} above the minimum, "
          f"semi-infinite limit {semi['chi2'] - length_chi2.min():+.2f}")
    contact_drop = tec.mean() - (T_INF_C + finite["theta0"])
    print(f"Contact: TEC {tec.mean():.2f} °C vs fitted rod base {T_INF_C + finite['theta0']:.2f} °C "
          f"-> {contact_drop:.1f} °C drop ({100 * contact_drop / (tec.mean() - T_INF_C):.0f}% of TEC - T_inf)")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stem = args.raw_csv.stem
    with open(OUTPUT_DIR / f"{stem}_fin_results.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["case", "model", "m_per_m", "m_err", "decay_length_m", "decay_length_err",
                         "theta0_C", "theta0_err", "corr_m_theta0", "mL", "mL_err",
                         "chi2", "dof", "p", *[f"resid_{c}" for c in ROD_CHANNELS]])
        for (case, name), r in results.items():
            writer.writerow([case, name, r["m"], r["m_err"], r["decay_length"], r["decay_length_err"],
                             r["theta0"], r["theta0_err"], r["corr"], r["mL"], r["mL_err"],
                             r["chi2"], r["dof"], r["p"], *r["residuals"]])

    x_full = np.linspace(0, ROD_LENGTH_M, 500)
    fig, (ax, ax_res) = plt.subplots(2, 1, figsize=(10, 8), sharex=True, constrained_layout=True,
                                     gridspec_kw={"height_ratios": [3, 1.3]})
    ax.errorbar(SENSOR_X_M * 100, theta, yerr=sigma, xerr=SENSOR_X_SIGMA_M * 100, fmt="o",
                color="black", capsize=4, zorder=3,
                label=f"rods 1-5, mean over t = {start:.0f}-{end:.0f} s ± σ")
    styles = {"finite (insulated tip)": ("tab:red", "-"), "semi-infinite": ("tab:blue", "--")}
    for name, shape in MODELS.items():
        r = results[("nominal", name)]
        color, line = styles[name]
        ax.plot(x_full * 100, r["theta0"] * shape(r["m"], x_full), line, color=color,
                label=f"{name}: m = {r['m']:.2f} ± {r['m_err']:.2f} m⁻¹, "
                      f"1/m = {r['decay_length']:.3f} ± {r['decay_length_err']:.3f} m, "
                      f"χ² = {r['chi2']:.2f}/{r['dof']}")
        offset = -0.15 if line == "-" else 0.15
        ax_res.errorbar(SENSOR_X_M * 100 + offset, r["residuals"], yerr=sigma, fmt="o",
                        color=color, capsize=3, label=name)
    ax.axhline(0, color="0.5", linestyle=":")
    ax.axvspan(SENSOR_X_M[-1] * 100, ROD_LENGTH_M * 100, color="0.93",
               label="beyond last sensor (extrapolated)")
    ax.set_ylim(bottom=0)
    ax.set_ylabel(f"θ = T − T∞ (°C),  T∞ = {T_INF_C} °C")
    ax.set_title(f"Steady-state rod profile, final {args.window / 60:g} min of Phase 4 "
                 f"(TEC at {args.new:g} °C)")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8.5, loc="lower left")
    ax_res.axhline(0, color="0.4", linewidth=1)
    ax_res.axvspan(SENSOR_X_M[-1] * 100, ROD_LENGTH_M * 100, color="0.93")
    ax_res.set_xlabel("Position along rod, x (cm)")
    ax_res.set_ylabel("θ data − fit (°C)")
    ax_res.grid(True, alpha=0.3)
    ax_res.legend(fontsize=9, loc="lower right")
    fig.savefig(OUTPUT_DIR / f"{stem}_fin_fits.png", dpi=150)

    fig, (ax_t, ax_m) = plt.subplots(2, 1, figsize=(10, 7), sharex=True, constrained_layout=True)
    shown = (time >= first_steady - args.window) & (time <= end)
    for c in ROD_CHANNELS:
        ax_t.plot(time[shown], data[c][shown], color=ROD_COLORS[c], linewidth=1, label=f"Rod {c[3]}")
    for w_end in window_ends:
        ax_t.axvline(w_end - args.window, color="0.8", linewidth=0.8)
    ax_t.axvspan(start, end, color="0.9", label="final interval (used)")
    ax_t.axvline(first_steady, color="0.4", linestyle="--", label="criterion first met")
    ax_t.set_ylabel("Raw temperature (°C)")
    ax_t.set_title(f"Phase 4 after steady state: {args.window / 60:g}-min windows and the m each one gives")
    ax_t.grid(True, alpha=0.3)
    ax_t.legend(fontsize=8.5, loc="upper left", bbox_to_anchor=(1.01, 1))
    centers = np.append(window_ends - args.window / 2, (start + end) / 2)
    ax_m.errorbar(centers, np.append(window_m, finite["m"]),
                  yerr=[f[3]["m_err"] for f in window_fits] + [finite["m_err"]], fmt="o-",
                  color="tab:red", capsize=3, label="finite (insulated tip)")
    ax_m.errorbar(centers, np.append(window_semi_m, semi["m"]),
                  yerr=[f[4]["m_err"] for f in window_fits] + [semi["m_err"]], fmt="s--",
                  color="tab:blue", capsize=3, label="semi-infinite")
    ax_m.axvspan(start, end, color="0.9")
    ax_m.set_xlabel("Arduino time, time_s (s)")
    ax_m.set_ylabel("Fitted m (m⁻¹)")
    ax_m.grid(True, alpha=0.3)
    ax_m.legend(fontsize=9)
    fig.savefig(OUTPUT_DIR / f"{stem}_fin_windows.png", dpi=150)
    print(f"\nSaved {OUTPUT_DIR / f'{stem}_fin_fits.png'}\nSaved {OUTPUT_DIR / f'{stem}_fin_windows.png'}"
          f"\nSaved {OUTPUT_DIR / f'{stem}_fin_results.csv'}")


if __name__ == "__main__":
    main()
