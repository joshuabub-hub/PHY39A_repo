"""Plot the heating and cooling P and PI control runs listed in the
Module 6 README.

Each run is pulled from data/temperature_log.csv as the longest contiguous
block of PI-mode rows with the given setpoint, Kp, and Ki (heating runs are
in session 5 at 30 C, cooling runs in session 6 at 15 C). Time is measured
from the first row of each run, and within each figure every run is cut to
the same window length (the duration of that figure's shortest run) so all
four panels cover an identical time interval.

PWM is the Arduino-reported PWM, signed by the reported direction
(+ HEAT, - COOL).

Outputs (in data/): P_PI_control_heating.png and P_PI_control_cooling.png,
each a 2x2 figure with P control temperature above P control PWM on the
left, and PI control temperature above PI control PWM on the right.
"""

import csv
from pathlib import Path

import matplotlib.pyplot as plt

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
LOG_PATH = DATA_DIR / "temperature_log.csv"
# (name, setpoint_C, output file) for each README table.
CASES = [
    ("Heating", 30.0, "P_PI_control_heating.png"),
    ("Cooling", 15.0, "P_PI_control_cooling.png"),
]

# (label, kp, ki) for each README table row (same gains for both tables).
P_RUNS = [
    ("Run 1: Kp = 5", 5.0, 0.0),
    ("Run 2: Kp = 50", 50.0, 0.0),
    ("Run 3: Kp = 500", 500.0, 0.0),
]
PI_RUNS = [
    ("Run 4: Kp = 40, Ki = 0.1", 40.0, 0.1),
    ("Run 5: Kp = 40, Ki = 0.5", 40.0, 0.5),
    ("Run 6: Kp = 40, Ki = 10", 40.0, 10.0),
]


def load_rows():
    with open(LOG_PATH, newline="") as f:
        return list(csv.DictReader(f))


def extract_run(rows, setpoint, kp, ki):
    """Return (t, temperature, signed_pwm) for the longest contiguous block
    of PI-mode rows at this setpoint, Kp, and Ki."""
    def matches(r):
        return (
            r["mode"] == "PI"
            and float(r["setpoint_C"]) == setpoint
            and float(r["kp"]) == kp
            and r["ki"] != ""
            and float(r["ki"]) == ki
        )

    blocks, start = [], None
    for i, r in enumerate(rows + [None]):
        if r is not None and matches(r):
            if start is None:
                start = i
        elif start is not None:
            blocks.append(rows[start:i])
            start = None

    block = max(blocks, key=len)
    t0 = float(block[0]["time_s"])
    t = [float(r["time_s"]) - t0 for r in block]
    temp = [float(r["temperature_C"]) for r in block]
    pwm = [int(r["pwm"]) * (1 if r["heat_cool"] == "1" else -1) for r in block]
    return t, temp, pwm


def crop(run, window_s):
    t, temp, pwm = run
    n = sum(1 for x in t if x <= window_s)
    return t[:n], temp[:n], pwm[:n]


def plot_column(ax_temp, ax_pwm, runs, setpoint, title, legend_loc):
    for label, (t, temp, _) in runs:
        ax_temp.plot(t, temp, label=label)
    ax_temp.axhline(setpoint, color="k", lw=1, ls="--",
                    label=f"Setpoint ({setpoint:g} ºC)")
    ax_temp.set_ylabel("Temperature (ºC)")
    ax_temp.set_title(title)
    ax_temp.legend(loc=legend_loc)
    ax_temp.grid(alpha=0.3)

    for label, (t, _, pwm) in runs:
        ax_pwm.plot(t, pwm, label=label)
    ax_pwm.axhline(0, color="k", lw=1)
    ax_pwm.set_xlabel("Time (s)")
    ax_pwm.set_ylabel("PWM (+ heat, - cool)")
    ax_pwm.grid(alpha=0.3)


def main():
    rows = load_rows()
    for name, setpoint, output in CASES:
        p = [(label, extract_run(rows, setpoint, kp, ki))
             for label, kp, ki in P_RUNS]
        pi = [(label, extract_run(rows, setpoint, kp, ki))
              for label, kp, ki in PI_RUNS]

        window_s = min(run[0][-1] for _, run in p + pi)
        print(f"{name} common window: {window_s:.2f} s")

        p = [(label, crop(run, window_s)) for label, run in p]
        pi = [(label, crop(run, window_s)) for label, run in pi]

        legend_loc = "lower right" if setpoint > 22 else "upper right"
        fig, axes = plt.subplots(2, 2, figsize=(12, 8),
                                 sharex=True, sharey="row")
        plot_column(axes[0, 0], axes[1, 0], p, setpoint,
                    f"P Control ({name})", legend_loc)
        plot_column(axes[0, 1], axes[1, 1], pi, setpoint,
                    f"PI Control ({name})", legend_loc)
        axes[0, 0].set_xlim(0, window_s)
        fig.tight_layout()
        fig.savefig(DATA_DIR / output, dpi=200)


if __name__ == "__main__":
    main()
