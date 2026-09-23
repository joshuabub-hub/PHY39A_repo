"""Plot steady-state temperature vs. signed PWM from the Module 4 PWM
step-test data (see README.md's "PWM step-test data" tables).

Reads data/pwm_steady_state.csv and plots heating and cooling as separate
red/blue line+marker series on the same axes. PWM is signed: positive for
heating, negative for cooling, so the x-axis also encodes direction.
"""

import csv
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

DATA_CSV = Path(__file__).resolve().parent.parent / "data" / "pwm_steady_state.csv"
OUTPUT_PNG = DATA_CSV.with_name("pwm_steady_state_plot.png")


def load_steady_state_data(csv_path):
    heat = {"pwm": [], "temp": []}
    cool = {"pwm": [], "temp": []}
    with open(csv_path, newline="") as csv_file:
        for row in csv.DictReader(csv_file):
            series = heat if row["direction"] == "HEAT" else cool
            series["pwm"].append(int(row["pwm"]))
            series["temp"].append(float(row["steady_state_temp_C"]))
    return heat, cool


def temperature_susceptibility(pwm, temp):
    """Least-squares slope (deg C per PWM count) of steady-state temp vs PWM."""
    slope, _intercept = np.polyfit(pwm, temp, 1)
    return slope


def main():
    heat, cool = load_steady_state_data(DATA_CSV)

    heat_slope = temperature_susceptibility(heat["pwm"], heat["temp"])
    cool_slope = temperature_susceptibility(cool["pwm"], cool["temp"])
    print(f"Heating susceptibility: {heat_slope:+.3f} C/PWM")
    print(f"Cooling susceptibility: {cool_slope:+.3f} C/PWM")

    plt.plot(heat["pwm"], heat["temp"], "o-", color="red", label="Heating")
    plt.plot(cool["pwm"], cool["temp"], "o-", color="blue", label="Cooling")
    plt.axvline(0, color="gray", linewidth=0.8, linestyle="--")

    plt.xlabel("Signed PWM (+ heating, \N{MINUS SIGN} cooling)")
    plt.ylabel("Steady-state temperature (\N{DEGREE SIGN}C)")
    plt.title("Steady-State Temperature vs. Signed PWM")
    plt.legend(loc="best")
    plt.grid(True)

    susceptibility_text = (
        f"Temperature susceptibility\n"
        f"Heating: {heat_slope:+.3f} \N{DEGREE SIGN}C/PWM\n"
        f"Cooling: {cool_slope:+.3f} \N{DEGREE SIGN}C/PWM"
    )
    plt.gca().text(
        0.02,
        0.98,
        susceptibility_text,
        transform=plt.gca().transAxes,
        ha="left",
        va="top",
        fontsize=9,
        bbox={"boxstyle": "round", "facecolor": "white", "edgecolor": "gray", "alpha": 0.9},
    )

    plt.tight_layout()

    plt.savefig(OUTPUT_PNG)
    print(f"Saved plot to {OUTPUT_PNG}")
    plt.show()


if __name__ == "__main__":
    main()
