"""Plot predicted vs. measured steady-state droop across the P-control
gain-tuning sweep (see README.md's "Predicted vs. measured steady-state
droop" table).

Reads data/gain_tuning_droop.csv and overlays the predicted droop curve
(from Tset - T = (Tset - Tamb) / (1 + chi_T,h * Kp), using Module 4's
measured heating susceptibility) against the measured droop from each
gain-tuning run, both vs. Kp on the same axes.
"""

import csv
from pathlib import Path

import matplotlib.pyplot as plt

DATA_CSV = Path(__file__).resolve().parent.parent / "data" / "gain_tuning_droop.csv"
OUTPUT_PNG = DATA_CSV.with_name("gain_tuning_droop_plot.png")


def load_droop_data(csv_path):
    kp, predicted, measured = [], [], []
    with open(csv_path, newline="") as csv_file:
        for row in csv.DictReader(csv_file):
            kp.append(float(row["kp"]))
            predicted.append(float(row["predicted_droop_C"]))
            measured.append(float(row["measured_droop_C"]))
    return kp, predicted, measured


def main():
    kp, predicted, measured = load_droop_data(DATA_CSV)

    plt.plot(kp, predicted, "o-", color="black", label="Predicted droop")
    plt.plot(kp, measured, "o-", color="orange", label="Measured droop")

    plt.xlabel("Kp (PWM / \N{DEGREE SIGN}C)")
    plt.ylabel("Steady-state droop, Tset \N{MINUS SIGN} T (\N{DEGREE SIGN}C)")
    plt.title("Predicted vs. Measured Steady-State Droop")
    plt.legend(loc="best")
    plt.grid(True)

    plt.tight_layout()

    plt.savefig(OUTPUT_PNG)
    print(f"Saved plot to {OUTPUT_PNG}")
    plt.show()


if __name__ == "__main__":
    main()
