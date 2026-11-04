"""Invert the measured steady-state susceptibility curves into the open-loop
feedforward command uff(Tset) and save a table and plot.

Steady temperature vs signed PWM (Module 4, data/pwm_steady_state.csv) is fit
separately for heating and cooling; uff(Tset) = (Tset - Troom)/m_heat for
Tset >= Troom and (Tset - Troom)/m_cool below it (+ = HEAT, - = COOL).
Run: python "Module 8/Python/feedforward_curve_mod8.py" [room_C]
"""

import csv
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
PWM_MAX = 255


def main():
    series = {"HEAT": ([], []), "COOL": ([], [])}
    with open(DATA_DIR / "pwm_steady_state.csv", newline="") as f:
        for row in csv.DictReader(f):
            series[row["direction"]][0].append(int(row["pwm"]))
            series[row["direction"]][1].append(float(row["steady_state_temp_C"]))
    m_h, b_h = np.polyfit(*series["HEAT"], 1)
    m_c, b_c = np.polyfit(*series["COOL"], 1)
    room = float(sys.argv[1]) if len(sys.argv) > 1 else (b_h + b_c) / 2
    print(f"Heating slope {m_h:.4f} C/PWM, cooling slope {m_c:.4f} C/PWM, ratio r = {m_h / m_c:.2f}")
    print(f"Troom = {room:.2f} C ({'entered' if len(sys.argv) > 1 else 'fitted unpowered baseline'})")

    t_set = np.arange(10.0, 60.01, 1.0)
    u = np.where(t_set >= room, (t_set - room) / m_h, (t_set - room) / m_c)
    ta, tb = 40.0, 16.0  # Tset = Ta + Tb sin(2 pi t / tau)
    u_peak = (ta + tb - room) / m_h
    u_trough = (ta - tb - room) / m_c
    print(f"Tset ranges {ta - tb:g} to {ta + tb:g} C: uff(peak) = {u_peak:+.1f} PWM, "
          f"uff(trough) = {u_trough:+.1f} PWM (limit +/-{PWM_MAX}); the mean command over a "
          f"cycle is not zero because r = {m_h / m_c:.2f}")

    with open(DATA_DIR / "feedforward_uff_mod8.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Tset_C", "uff_signed_PWM", "direction"])
        for ts, uu in zip(t_set, u):
            w.writerow([f"{ts:.1f}", f"{uu:.1f}", "HEAT" if uu >= 0 else "COOL"])

    fig, ax = plt.subplots(figsize=(9, 6))
    ax.plot(t_set, u, "k-", lw=2.5, label="uff(Tset)")
    ax.plot(series["HEAT"][1], series["HEAT"][0], "ro", ms=8, label="Measured heating")
    ax.plot(series["COOL"][1], series["COOL"][0], "bo", ms=8, label="Measured cooling")
    ax.axhline(0, color="gray", lw=1)
    ax.axvline(room, color="gray", ls=":", label=f"Troom = {room:.1f} C")
    ax.set_xlabel("Steady-state temperature Tset (°C)", fontsize=13)
    ax.set_ylabel("Signed PWM (+ heat / − cool)", fontsize=13)
    ax.set_title("Feedforward command from the inverted susceptibility curve", fontsize=14)
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=11)
    fig.tight_layout()
    fig.savefig(DATA_DIR / "feedforward_uff_mod8.png", dpi=130)
    print("Saved feedforward_uff_mod8.csv and .png")


if __name__ == "__main__":
    main()
