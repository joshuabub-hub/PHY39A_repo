"""Plot the 20 C -> 45 C TEC setpoint step from one Module 7 run and save the
boundary-condition record (commanded TEC, measured TEC, rod T(0,t)).

Reads the raw_mod7 / pi_log_mod7 pair for the run (joined on time_s), finds
the step in the PI log's setpoint_C, and writes into Module 7/data:
  step_response_mod7.png          all six temperatures + commanded setpoint
  step_boundary_condition_mod7.csv  time_s, commanded, TEC, rod 1 (= T(0,t))
Run: python "Module 7/Python/plot_step_response_mod7.py"
"""

import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
RUN_STAMP = "20261104_091551"
STEP_FROM_C, STEP_TO_C = 20.0, 45.0
DRIFT_LIMIT_C_PER_MIN = 0.02  # course steady-state criterion

CHANNELS = [  # (column, label, color, width)
    ("tec_C", "TEC thermistor", "black", 3.0),
    ("rod1_C", "Rod 1  (x = 0, boundary)", "#1f77b4", 2.2),
    ("rod2_C", "Rod 2", "#ff7f0e", 2.0),
    ("rod3_C", "Rod 3", "#9467bd", 2.0),
    ("rod4_C", "Rod 4", "#8c564b", 2.0),
    ("rod5_C", "Rod 5", "#17becf", 2.0),
]


def read(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def column(rows, name):
    return np.array([float(r[name]) for r in rows])


def find_step(pi_rows):
    """Time of the first record whose setpoint is STEP_TO_C right after STEP_FROM_C."""
    sp = column(pi_rows, "setpoint_C")
    t = column(pi_rows, "time_s")
    reached = np.where(sp == STEP_TO_C)[0]
    if not len(reached):
        raise SystemExit("No 45 C setpoint found in the PI log.")
    return t[reached[0]]


def window_slope(t, y, t_end, minutes):
    """Least-squares slope (C/min) of y over the last `minutes` before t_end."""
    m = (t > t_end - 60 * minutes) & (t <= t_end)
    return np.polyfit(t[m], y[m], 1)[0] * 60.0


def fit_exponential(t, y, t_step):
    """Fit y = y_inf - A*exp(-(t-t_step)/tau); returns (y_inf, tau). Scans tau, solves y_inf and A linearly."""
    m = t >= t_step + 100
    tt, yy = t[m] - t_step, y[m]
    best = None
    for tau in np.linspace(20, 2000, 800):
        basis = np.column_stack([np.ones_like(tt), -np.exp(-tt / tau)])
        coef, *_ = np.linalg.lstsq(basis, yy, rcond=None)
        sse = np.sum((basis @ coef - yy) ** 2)
        if best is None or sse < best[0]:
            best = (sse, coef[0], tau)
    return best[1], best[2]


def main():
    raw = read(DATA_DIR / f"raw_mod7_{RUN_STAMP}.csv")
    pi = read(DATA_DIR / f"pi_log_mod7_{RUN_STAMP}.csv")
    assert [r["time_s"] for r in raw] == [p["time_s"] for p in pi], "files do not join on time_s"

    t = column(raw, "time_s")
    commanded = column(pi, "setpoint_C")
    # Typing 45 in the spinbox briefly passed through 2 C; the real command stayed at 20 C until 45 C.
    t_step = find_step(pi)
    glitch = (commanded < STEP_FROM_C) & (t > 700) & (t < t_step)
    commanded[glitch] = STEP_FROM_C
    temps = {name: column(raw, name) for name, *_ in CHANNELS}
    # The setpoint box passes through intermediate values while typing, so the
    # commanded value is only trusted from the first record at 45 C.
    after = t >= t_step
    print(f"Step to {STEP_TO_C:g} C at t = {t_step:.2f} s")

    print(f"{'sensor':<26}{'T(step)':>9}{'T(end)':>9}{'excursion':>10}{'t10% (s)':>10}{'t50% (s)':>10}")
    for name, label, _c, _w in CHANNELS:
        y = temps[name]
        y0 = y[np.searchsorted(t, t_step)]
        y1 = y[-20:].mean()
        exc = y1 - y0
        out = []
        for frac in (0.1, 0.5):
            idx = np.where(after & (y >= y0 + frac * exc))[0]
            out.append(t[idx[0]] - t_step if len(idx) else float("nan"))
        print(f"{label:<26}{y0:9.2f}{y1:9.2f}{exc:10.2f}{out[0]:10.1f}{out[1]:10.1f}")

    fig, axes = plt.subplots(
        2, 1, figsize=(14, 10), sharex=True, gridspec_kw={"height_ratios": [3, 2]}
    )
    lo, hi = t_step - 150, t[-1]
    ax = axes[0]
    for name, label, color, width in CHANNELS:
        ax.plot(t, temps[name], color=color, lw=width, label=label)
    ax.step(t, commanded, where="post", color="green", ls="--", lw=2.5, label="Commanded setpoint")
    ax.axvline(t_step, color="gray", ls=":", lw=1.5)
    ax.annotate(f"setpoint {STEP_FROM_C:g} → {STEP_TO_C:g} °C\nt = {t_step:.0f} s",
                (t_step, 21), xytext=(t_step + 40, 22), fontsize=12,
                arrowprops=dict(arrowstyle="->", color="gray"))
    ax.set_ylabel("Temperature (°C)", fontsize=13)
    ax.set_title("All six temperatures after the 20 → 45 °C setpoint step", fontsize=15)
    ax.legend(fontsize=11, ncol=2, loc="lower right")

    ax = axes[1]
    ax.step(t, commanded, where="post", color="green", ls="--", lw=2.5, label="Commanded TEC temperature")
    ax.plot(t, temps["tec_C"], color="black", lw=3, label="Measured TEC temperature")
    ax.plot(t, temps["rod1_C"], color="#1f77b4", lw=2.5, label="Rod T(0, t)  (model boundary condition)")
    ax.axvline(t_step, color="gray", ls=":", lw=1.5)
    ax.set_ylabel("Temperature (°C)", fontsize=13)
    ax.set_xlabel("Arduino time (s)", fontsize=13)
    ax.set_title("Boundary-condition record: command, TEC, and T(0, t)", fontsize=15)
    ax.legend(fontsize=11, loc="lower right")

    for ax in axes:
        ax.set_xlim(lo, hi)
        ax.set_ylim(15, 48)
        ax.grid(True, alpha=0.3)
        ax.tick_params(labelsize=12)
    fig.tight_layout()
    png = DATA_DIR / "step_response_mod7.png"
    fig.savefig(png, dpi=150)
    print(f"Saved {png}")

    # Steady-state estimate (printed only): drift over the last 5/10 min and the fitted final value.
    t_end = t[-1]
    print(f"\nSteady-state check at t = {t_end:.0f} s ({(t_end - t_step) / 60:.1f} min after the step)")
    print(f"{'sensor':<26}{'last 5 min':>11}{'last 10 min':>12}{'T(now)':>8}{'T_inf':>8}{'tau(s)':>8}{'gap(C)':>8}{'% of rise':>10}")
    steady = True
    for name, label, _color, _width in CHANNELS:
        y = temps[name]
        s5, s10 = window_slope(t, y, t_end, 5), window_slope(t, y, t_end, 10)
        y_inf, tau = fit_exponential(t, y, t_step)
        now = y[-20:].mean()
        rise = now - y[np.searchsorted(t, t_step)]
        if name != "tec_C":
            steady &= abs(s10) < DRIFT_LIMIT_C_PER_MIN
        print(f"{label:<26}{s5:+11.3f}{s10:+12.3f}{now:8.2f}{y_inf:8.2f}{tau:8.0f}{y_inf - now:8.2f}{100 * (y_inf - now) / rise:10.1f}")
    print(f"Criterion |dT/dt| < {DRIFT_LIMIT_C_PER_MIN} C/min on every rod sensor for 10 min: {'MET' if steady else 'NOT MET'}")

    csv_path = DATA_DIR / "step_boundary_condition_mod7.csv"
    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["time_s", "commanded_TEC_C", "measured_TEC_C", "rod1_T0_C"])
        for i in range(len(t)):
            w.writerow([f"{t[i]:.2f}", f"{commanded[i]:g}", f"{temps['tec_C'][i]:.2f}", f"{temps['rod1_C'][i]:.2f}"])
    print(f"Saved {csv_path}")


if __name__ == "__main__":
    main()
