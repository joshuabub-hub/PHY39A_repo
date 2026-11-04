"""Analyze a sinusoidal-drive run (Module 8): boundary quality, mode comparison,
per-cycle settling, and amplitude/phase of every rod sensor.

Fits T(t) = c + d*t + A*sin(w t) + B*cos(w t) to each sensor, so
T = c + d*t + Amp*sin(w t + phi). Phase lag of a signal behind another is
(phi_ref - phi)/w. The commanded setpoint is read from the PI log.

Examples (from the repo root):
  python "Module 8/Python/analyze_angstrom_mod8.py" 20261110_101500 --t0 300 --t1 900 --period 100 --label PI
  python "Module 8/Python/analyze_angstrom_mod8.py" --compare

Each run appends one row to data/angstrom_summary_mod8.csv; --compare prints it.
"""

import argparse
import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
SUMMARY_CSV = DATA_DIR / "angstrom_summary_mod8.csv"
SENSORS = ["rod1_C", "rod2_C", "rod3_C", "rod4_C", "rod5_C"]
PWM_MAX = 255

# Settling criterion between successive complete cycles (per sensor).
AMP_TOL = 0.02  # fractional amplitude change
PHASE_TOL_DEG = 2.0
MEAN_TOL_C = 0.15
MIN_SETTLED_CYCLES = 5

SUMMARY_FIELDS = [
    "label", "stamp", "period_s", "t0_s", "t1_s", "mean_C", "amp_C", "target_amp_C",
    "phase_lag_deg", "symmetry", "distortion_rms_over_amp", "harmonic_ratio",
    "rms_error_C", "pwm_mean", "pwm_max_heat", "pwm_max_cool", "frac_saturated",
]


def read_csv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def column(rows, name, dtype=float):
    return np.array([dtype(r[name]) if r[name] != "" else np.nan for r in rows])


def sine_fit(t, y, omega):
    """Return mean c, drift d (per s), amplitude, phase phi (rad) and residuals."""
    basis = np.column_stack([np.ones_like(t), t - t[0], np.sin(omega * t), np.cos(omega * t)])
    coef, *_ = np.linalg.lstsq(basis, y, rcond=None)
    amp = np.hypot(coef[2], coef[3])
    phi = np.arctan2(coef[3], coef[2])
    return coef[0], coef[1], amp, phi, y - basis @ coef


def wrap(angle):
    return (angle + np.pi) % (2 * np.pi) - np.pi


def load_run(stamp):
    raw = read_csv(DATA_DIR / f"raw_mod8_{stamp}.csv")
    log = read_csv(DATA_DIR / f"pi_log_mod8_{stamp}.csv")
    if [r["time_s"] for r in raw] != [r["time_s"] for r in log]:
        raise SystemExit("raw and PI log do not join on time_s")
    t = column(raw, "time_s")
    data = {c: column(raw, c) for c in ["tec_C"] + SENSORS}
    pwm = column(raw, "pwm")
    sign = np.where(column(raw, "heat_cool", int) == 1, 1.0, -1.0)
    return t, data, pwm * sign, column(log, "setpoint_C"), [r["mode"] for r in log]


def settling_table(t, data, omega, period, t0, t1):
    """Per-cycle amplitude/phase/mean for every sensor and the first cycle from which the criterion holds."""
    edges = np.arange(t0, t1 - period + 1e-9, period)
    cycles = []
    for start in edges:
        m = (t >= start) & (t < start + period)
        if m.sum() < 20:
            continue
        cycles.append({s: sine_fit(t[m], data[s][m], omega)[:4] for s in SENSORS})
    ok = []
    for k in range(1, len(cycles)):
        good = True
        for s in SENSORS:
            c0, _, a0, p0 = cycles[k - 1][s]
            c1, _, a1, p1 = cycles[k][s]
            good &= abs(a1 - a0) / max(a0, 1e-9) < AMP_TOL
            good &= abs(np.degrees(wrap(p1 - p0))) < PHASE_TOL_DEG
            good &= abs(c1 - c0) < MEAN_TOL_C
        ok.append(good)
    first = None
    for k in range(len(ok)):
        if all(ok[k:]) and len(ok) - k >= MIN_SETTLED_CYCLES - 1:
            first = k + 1  # cycle index (0-based) whose change from its predecessor starts the settled run
            break
    return cycles, ok, first


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("stamp", nargs="?", help="run stamp, e.g. 20261110_101500")
    p.add_argument("--t0", type=float, help="analysis start time (s)")
    p.add_argument("--t1", type=float, help="analysis end time (s)")
    p.add_argument("--period", type=float, default=100.0)
    p.add_argument("--label", default="run", help="e.g. OPEN, P, PI")
    p.add_argument("--positions", type=float, nargs=5, default=[0.0, 0.025, 0.05, 0.10, 0.15],
                   help="x of rods 1-5 in m from rod 1 (default from Module 7)")
    p.add_argument("--compare", action="store_true", help="print the saved summary table and exit")
    args = p.parse_args()

    if args.compare:
        for row in read_csv(SUMMARY_CSV):
            print("  ".join(f"{k}={v}" for k, v in row.items()))
        return
    if not (args.stamp and args.t0 is not None and args.t1 is not None):
        p.error("stamp, --t0 and --t1 are required")

    t, data, signed_pwm, setpoint, modes = load_run(args.stamp)
    omega = 2 * np.pi / args.period
    win = (t >= args.t0) & (t <= args.t1)
    n_cycles = (args.t1 - args.t0) / args.period
    print(f"Run {args.stamp}, window {args.t0:g}-{args.t1:g} s = {n_cycles:.1f} cycles of {args.period:g} s; "
          f"modes in window: {sorted(set(np.array(modes)[win]))}")

    # Boundary (T1) vs commanded waveform.
    tw = t[win]
    c1, d1, a1, ph1, res1 = sine_fit(tw, data["rod1_C"][win], omega)
    cs, _, as_, phs, _ = sine_fit(tw, setpoint[win], omega)
    lag_deg = np.degrees(wrap(phs - ph1))
    y1 = data["rod1_C"][win]
    symmetry = (y1.max() - c1) / (c1 - y1.min())  # 1 = heating and cooling excursions equal
    distortion = res1.std() / a1
    # Second and third harmonics of T1 relative to the fundamental.
    harm = 0.0
    for h in (2, 3):
        basis = np.column_stack([np.sin(h * omega * tw), np.cos(h * omega * tw), np.ones_like(tw)])
        coef, *_ = np.linalg.lstsq(basis, y1 - np.polyval(np.polyfit(tw, y1, 1), tw), rcond=None)
        harm += np.hypot(coef[0], coef[1]) ** 2
    harm = np.sqrt(harm) / a1
    rms_error = np.sqrt(np.mean((y1 - setpoint[win]) ** 2))
    u = signed_pwm[win]
    sat = np.mean(np.abs(u) >= PWM_MAX)
    print(f"\nT1 boundary: mean {c1:.2f} C (commanded {cs:.2f}), amplitude {a1:.2f} C (commanded {as_:.2f}), "
          f"lag behind command {lag_deg:+.1f} deg ({lag_deg / 360 * args.period:+.1f} s)")
    print(f"  heating/cooling symmetry (max-mean)/(mean-min) = {symmetry:.2f}; drift {d1 * 60:+.3f} C/min")
    print(f"  distortion: residual RMS / amplitude = {distortion:.3f}, harmonics (2nd+3rd)/fundamental = {harm:.3f}")
    print(f"  RMS(T1 - Tset) = {rms_error:.2f} C")
    print(f"  applied PWM: mean {u.mean():+.1f}, max heat {u.max():.0f}, max cool {u.min():.0f}, saturated {100 * sat:.1f}% of records")

    # Per-sensor amplitude and phase; ordering check.
    print("\nSensor amplitude / phase (lag behind T1):")
    fits = {s: sine_fit(tw, data[s][win], omega) for s in SENSORS}
    x = np.array(args.positions)
    amps, lags, means = [], [], []
    for i, s in enumerate(SENSORS):
        c, d, a, ph, res = fits[s]
        lag = np.degrees(wrap(fits["rod1_C"][3] - ph))
        amps.append(a)
        lags.append(lag)
        means.append(c)
        print(f"  {s[:4]+s[4]} x={x[i]:.3f} m: mean {c:6.2f} C, amp {a:5.2f} C ({a / a1:5.2f} of T1), "
              f"lag {lag:6.1f} deg ({lag / 360 * args.period:5.1f} s), resid RMS {res.std():.2f} C")
    in_order = all(np.diff(amps) < 0) and all(np.diff(lags) > 0)
    print(f"  Ordering check (T1 nearest TEC: amplitude falls and lag rises with index): {'OK' if in_order else 'NOT OK - recheck channel map'}")
    good = [i for i in range(5) if amps[i] > 0.1]
    print(f"  Sensors with measurable amplitude (> 0.1 C): {len(good)}")
    if len(good) >= 3:
        k_amp = -np.polyfit(x[good], np.log(np.array(amps)[good]), 1)[0]
        k_phase = np.polyfit(x[good], np.radians(np.array(lags)[good]), 1)[0]
        for name, k in (("amplitude", k_amp), ("phase", k_phase)):
            print(f"  {name} slope k = {k:.2f} 1/m -> alpha = omega/(2k^2) = {omega / (2 * k**2) * 1e6:.1f} mm^2/s (ignores side loss)")

    # Settling.
    cycles, ok, first = settling_table(t, data, omega, args.period, args.t0, args.t1)
    print(f"\nSettling (change between successive cycles: amp < {AMP_TOL:.0%}, phase < {PHASE_TOL_DEG:g} deg, "
          f"mean < {MEAN_TOL_C:g} C, every sensor):")
    print("  cycle-to-cycle flags:", "".join("Y" if g else "n" for g in ok))
    if first is None:
        print(f"  Not settled for {MIN_SETTLED_CYCLES} consecutive cycles in this window.")
    else:
        print(f"  Settled from cycle {first} on ({len(ok) + 1 - first} cycles).")

    DATA_DIR.mkdir(exist_ok=True)
    new = not SUMMARY_CSV.exists()
    with open(SUMMARY_CSV, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=SUMMARY_FIELDS)
        if new:
            w.writeheader()
        w.writerow({
            "label": args.label, "stamp": args.stamp, "period_s": args.period, "t0_s": args.t0, "t1_s": args.t1,
            "mean_C": f"{c1:.2f}", "amp_C": f"{a1:.2f}", "target_amp_C": f"{as_:.2f}",
            "phase_lag_deg": f"{lag_deg:.1f}", "symmetry": f"{symmetry:.2f}",
            "distortion_rms_over_amp": f"{distortion:.3f}", "harmonic_ratio": f"{harm:.3f}",
            "rms_error_C": f"{rms_error:.2f}", "pwm_mean": f"{u.mean():.1f}",
            "pwm_max_heat": f"{u.max():.0f}", "pwm_max_cool": f"{u.min():.0f}", "frac_saturated": f"{sat:.3f}",
        })

    # Figure: boundary vs command, residuals, applied PWM, all sensors.
    fig, axes = plt.subplots(4, 1, figsize=(13, 14), sharex=True, gridspec_kw={"height_ratios": [3, 2, 2, 3]})
    axes[0].plot(tw, setpoint[win], "g--", lw=2.5, label="Commanded Tset")
    axes[0].plot(tw, y1, color="#1f77b4", lw=2.5, label="T1 (boundary)")
    axes[0].plot(tw, data["tec_C"][win], "k", lw=1.5, alpha=0.6, label="TEC")
    axes[0].set_ylabel("Temperature (°C)")
    axes[0].set_title(f"{args.label}: T1 boundary vs commanded sinusoid")
    axes[1].plot(tw, y1 - setpoint[win], color="#d62728", lw=2)
    axes[1].axhline(0, color="k", lw=1)
    axes[1].set_ylabel("T1 − Tset (°C)")
    axes[2].plot(tw, u, color="purple", lw=2)
    axes[2].axhline(0, color="k", lw=1)
    axes[2].set_ylabel("Applied PWM (+heat / −cool)")
    for s in SENSORS:
        axes[3].plot(tw, data[s][win], lw=2, label=s[:4] + s[4])
    axes[3].set_ylabel("Rod temperatures (°C)")
    axes[3].set_xlabel("Arduino time (s)")
    for ax in axes:
        ax.grid(True, alpha=0.3)
        ax.legend(loc="upper right", ncol=3) if ax.get_legend_handles_labels()[0] else None
    fig.tight_layout()
    out = DATA_DIR / f"angstrom_{args.label}_{args.stamp}.png"
    fig.savefig(out, dpi=130)
    print(f"\nSaved {out} and a row in {SUMMARY_CSV.name}")


if __name__ == "__main__":
    main()
