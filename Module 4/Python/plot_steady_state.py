"""Plot steady-state temperature vs. signed PWM from the Module 4 PWM
step-test data (see README.md's "PWM step-test data" tables).

Reads data/pwm_steady_state.csv and plots heating and cooling on common axes
with separate least-squares fits over each full tested range. The shared
PWM 0 point is the common unpowered baseline. PWM is signed: positive for
heating, negative for cooling.
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


def fit_temperature_vs_pwm(pwm, temp):
    """Return slope and intercept for steady-state temperature vs. signed PWM."""
    return np.polyfit(pwm, temp, 1)


def main():
    heat, cool = load_steady_state_data(DATA_CSV)

    heat_pwm = np.asarray(heat["pwm"])
    heat_temp = np.asarray(heat["temp"])
    cool_pwm = np.asarray(cool["pwm"])
    cool_temp = np.asarray(cool["temp"])

    heat_slope, heat_intercept = fit_temperature_vs_pwm(heat_pwm, heat_temp)
    cool_slope, cool_intercept = fit_temperature_vs_pwm(cool_pwm, cool_temp)
    slope_ratio = abs(heat_slope) / abs(cool_slope)
    print(f"Heating fit ({heat_pwm.min():.0f} to {heat_pwm.max():.0f} PWM): "
          f"{heat_slope:+.4f} C/PWM")
    print(f"Cooling fit ({cool_pwm.min():.0f} to {cool_pwm.max():.0f} signed PWM): "
          f"{cool_slope:+.4f} C/PWM")
    print(f"Heating-to-cooling slope-magnitude ratio: {slope_ratio:.4f}")

    heat_active = heat_pwm != 0
    cool_active = cool_pwm != 0
    plt.plot(heat_pwm[heat_active], heat_temp[heat_active], "o", color="red",
             label="Heating data")
    plt.plot(cool_pwm[cool_active], cool_temp[cool_active], "o", color="blue",
             label="Cooling data")
    plt.scatter([0], [heat["temp"][heat["pwm"].index(0)]], marker="s",
                color="gray", label="PWM 0 (TEC off)", zorder=4)

    heat_fit_pwm = np.linspace(heat_pwm.min(), heat_pwm.max(), 100)
    cool_fit_pwm = np.linspace(cool_pwm.min(), cool_pwm.max(), 100)
    plt.plot(
        heat_fit_pwm,
        heat_slope * heat_fit_pwm + heat_intercept,
        color="darkred",
        label=f"Heating fit: {heat_slope:+.3f} °C/PWM, {heat_pwm.min():.0f}–{heat_pwm.max():.0f}",
    )
    plt.plot(
        cool_fit_pwm,
        cool_slope * cool_fit_pwm + cool_intercept,
        color="navy",
        label=f"Cooling fit: {cool_slope:+.3f} °C/PWM, {cool_pwm.min():.0f}–{cool_pwm.max():.0f}",
    )
    plt.axvline(0, color="gray", linewidth=0.8, linestyle="--")

    plt.xlabel("Signed PWM command (counts; positive = heating, negative = cooling)")
    plt.ylabel("Steady-state object temperature (°C)")
    plt.title("Module 4: Steady-State Temperature vs. Signed PWM")
    plt.legend(loc="best", fontsize=8)
    plt.grid(True)

    plt.tight_layout()

    plt.savefig(OUTPUT_PNG)
    print(f"Saved plot to {OUTPUT_PNG}")
    plt.show()


if __name__ == "__main__":
    main()
