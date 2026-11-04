"""Plot all six thermistors vs time across one setpoint step.

Reads a raw CSV and its matching pi_log CSV (both written by serial_plot_mod7.py),
finds the step in the PI setpoint, and plots tec_C and rod1_C ... rod5_C on one
graph from the start of the old setpoint hold until every thermistor reaches
steady state (|dT/dt| < STEADY_RATE_C_PER_MIN). The slope is a least-squares
line over a trailing SLOPE_WINDOW_S window. If steady state is never reached,
the plot runs to the end of the file and the title says so.

Example (run from the Module 7 folder):
  venv/bin/python Python/plot_step_mod7.py data/raw_mod7_20261102_093130.csv --from 20 --to 45
"""

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

CHANNELS = ["tec_C", "rod1_C", "rod2_C", "rod3_C", "rod4_C", "rod5_C"]

# Same colors as the live GUI and calibration plots.
ROD_COLORS = {
    "rod1_C": (31 / 255, 119 / 255, 180 / 255),
    "rod2_C": (255 / 255, 127 / 255, 14 / 255),
    "rod3_C": (148 / 255, 103 / 255, 189 / 255),
    "rod4_C": (140 / 255, 86 / 255, 75 / 255),
    "rod5_C": (23 / 255, 190 / 255, 207 / 255),
}

STEADY_RATE_C_PER_MIN = 0.02
SLOPE_WINDOW_S = 120.0
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "data" / "step_plots"


def load_csv(path):
    """Numeric columns as float arrays; non-numeric entries become nan."""
    names = np.genfromtxt(path, delimiter=",", max_rows=1, dtype=str)
    values = np.genfromtxt(path, delimiter=",", skip_header=1, dtype=float)
    return {name: values[:, k] for k, name in enumerate(names)}


def find_step(pi_log, old, new):
    """Times the setpoint became `old` (hold start) and then changed to `new`."""
    time, setpoint = pi_log["time_s"], pi_log["setpoint_C"]
    changed = np.flatnonzero(np.diff(setpoint) != 0) + 1
    for k in changed:
        if setpoint[k] == new and setpoint[k - 1] == old:
            earlier = changed[changed < k]
            hold_start = time[earlier[-1]] if len(earlier) else time[0]
            return hold_start, time[k]
    raise SystemExit(f"No {old} -> {new} °C setpoint step found in the PI log.")


def trailing_slope(time, temp, end):
    """dT/dt in °C/min from a line fit over [end - SLOPE_WINDOW_S, end]."""
    window = (time > end - SLOPE_WINDOW_S) & (time <= end) & np.isfinite(temp)
    if window.sum() < 10:
        return np.nan
    return np.polyfit(time[window], temp[window], 1)[0] * 60.0


def find_steady_time(data, step_time):
    """First time after the step where every channel's |dT/dt| is below the limit."""
    time = data["time_s"]
    for end in time[time >= step_time + SLOPE_WINDOW_S]:
        rates = [trailing_slope(time, data[c], end) for c in CHANNELS]
        if all(abs(r) < STEADY_RATE_C_PER_MIN for r in rates):
            return end
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("raw_csv", type=Path)
    parser.add_argument("--from", dest="old", type=float, required=True,
                        help="setpoint before the step (°C)")
    parser.add_argument("--to", dest="new", type=float, required=True,
                        help="setpoint after the step (°C)")
    args = parser.parse_args()

    data = load_csv(args.raw_csv)
    pi_log = load_csv(args.raw_csv.with_name(args.raw_csv.name.replace("raw_", "pi_log_", 1)))
    hold_start, step_time = find_step(pi_log, args.old, args.new)
    steady_time = find_steady_time(data, step_time)

    time = data["time_s"]
    end = steady_time if steady_time is not None else time[-1]
    shown = (time >= hold_start) & (time <= end)

    fig, ax = plt.subplots(figsize=(11, 6), constrained_layout=True)
    for channel in CHANNELS:
        is_tec = channel == "tec_C"
        ax.plot(time[shown], data[channel][shown], "-",
                color="black" if is_tec else ROD_COLORS[channel],
                linewidth=2.5 if is_tec else 1.3,
                label="TEC base" if is_tec else f"Rod {channel[3]}")
    ax.axvline(step_time, color="0.4", linestyle="--",
               label=f"setpoint {args.old:g} → {args.new:g} °C (t = {step_time:.0f} s)")

    rates = {c: trailing_slope(time, data[c], end) for c in CHANNELS}
    if steady_time is not None:
        ax.axvspan(steady_time - SLOPE_WINDOW_S, steady_time, color="0.9",
                   label=f"steady state (|dT/dt| < {STEADY_RATE_C_PER_MIN} °C/min)")
        status = f"steady state at t = {steady_time:.0f} s"
    else:
        status = (f"steady state NOT reached by end of data (t = {end:.0f} s); "
                  f"max |dT/dt| = {max(abs(r) for r in rates.values()):.2f} °C/min")

    final_rates = ", ".join(("TEC" if c == "tec_C" else f"Rod {c[3]}") + f" {r:+.3f}"
                            for c, r in rates.items())
    ax.set_title(f"{args.old:g} → {args.new:g} °C step: thermistor temperatures vs time\n"
                 f"final dT/dt at t = {end:.0f} s (°C/min): {final_rates}")
    ax.set_xlabel("Arduino time, time_s (s)")
    ax.set_ylabel("Raw temperature (°C)")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=9, loc="upper left", bbox_to_anchor=(0.1, 0.9))

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUT_DIR / f"{args.raw_csv.stem}_step_{args.old:g}_to_{args.new:g}.png"
    fig.savefig(out, dpi=150)
    print(f"Step at t = {step_time:.2f} s, plot from t = {hold_start:.2f} s to {end:.2f} s")
    print(status)
    for channel, rate in rates.items():
        print(f"  {channel:7s} dT/dt at end = {rate:+.3f} °C/min")
    print(f"Saved {out}")


if __name__ == "__main__":
    main()
