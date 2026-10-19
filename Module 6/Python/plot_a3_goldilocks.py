"""Rebuild the Module 6 PI Goldilocks comparisons from log + model.

Experimental temperatures come from data/temperature_log.csv (heating session
5, cooling session 6). Simulation curves are generated in memory by the shared
Lab_6_7_modeling_tec_v3 two-lump Euler model; they are not measured or read
from a separate simulation-data file. The figures are saved as SVGs under
 data/A3_comparison/.
"""

from __future__ import annotations

import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

MODULE_DIR = Path(__file__).resolve().parents[1]
LOG_PATH = MODULE_DIR / "data" / "temperature_log.csv"
OUTPUT_DIR = MODULE_DIR / "data" / "A3_comparison"

# (legend label, Kp, Ki, color). The middle gain is the recommended compromise.
KI_CASES = [
    (r"Low $K_i=0.1$", 40.0, 0.1, "#277da1"),
    (r"Goldilocks $K_i=0.5$", 40.0, 0.5, "#43a047"),
    (r"High $K_i=10$", 40.0, 10.0, "#e76f51"),
]
DIRECTIONS = [
    ("Heating", 5, 30.0, "heating_pi_ki_comparison.svg"),
    ("Cooling", 6, 15.0, "cooling_pi_ki_comparison.svg"),
]
P_CASES = [
    ("P control, Kp=5", 5.0, "p_kp5.svg"),
    ("P control, Kp=50", 50.0, "p_kp50.svg"),
    ("P control, Kp=500", 500.0, "p_kp500.svg"),
]


def load_rows() -> list[dict[str, str]]:
    with LOG_PATH.open(newline="") as log_file:
        return list(csv.DictReader(log_file))


def extract_longest_run(
    rows: list[dict[str, str]], session: int, setpoint_c: float, kp: float, ki: float
) -> tuple[list[float], list[float]]:
    """Return relative time and temperature for the longest matching log block."""
    matching_blocks: list[list[dict[str, str]]] = []
    block: list[dict[str, str]] = []
    for row in [*rows, None]:
        matches = (
            row is not None
            and int(row["session"]) == session
            and row["mode"] == "PI"
            and float(row["setpoint_C"]) == setpoint_c
            and float(row["kp"]) == kp
            and row["ki"] != ""
            and float(row["ki"]) == ki
        )
        if matches:
            block.append(row)
        elif block:
            matching_blocks.append(block)
            block = []

    if not matching_blocks:
        raise ValueError(
            f"No log run found for session={session}, setpoint={setpoint_c}, "
            f"Kp={kp}, Ki={ki}."
        )

    run = max(matching_blocks, key=len)
    start_s = float(run[0]["time_s"])
    times_s = [float(row["time_s"]) - start_s for row in run]
    temperatures_c = [float(row["temperature_C"]) for row in run]
    return times_s, temperatures_c


def make_model_trace(
    initial_c: float, setpoint_c: float, kp: float, ki: float, duration_s: float
) -> tuple[list[float], list[float]]:
    """Run the documented two-lump PI model with forward-Euler updates.

    The update and conditional-integration anti-windup logic match
    Lab_6_7_modeling_tec_v3.py. They are kept local here so plot regeneration
    does not require importing that desktop GUI module (and Tk).
    """
    ambient_c = 22.0
    total_capacitance = 137.6
    tec_capacitance = 0.35 * total_capacitance
    measured_capacitance = 0.65 * total_capacitance
    coupling = 2.0
    heat_loss = 0.688
    cooling_power_per_pwm = 0.0929
    heating_to_cooling_ratio = 3.815
    pwm_limit = 255.0
    dt_s = 0.1

    tec_c = initial_c
    measured_c = initial_c
    integral_error_c_s = 0.0
    times_s = [0.0]
    temperatures_c = [initial_c]
    step_count = round(duration_s / dt_s)

    for step in range(step_count):
        error_c = setpoint_c - measured_c
        p_term = kp * error_c
        proposed_integral = integral_error_c_s + error_c * dt_s
        proposed_command = p_term + ki * proposed_integral
        drives_farther_into_saturation = (
            proposed_command > pwm_limit and error_c > 0.0
        ) or (proposed_command < -pwm_limit and error_c < 0.0)
        if not drives_farther_into_saturation:
            integral_error_c_s = proposed_integral

        raw_command = p_term + ki * integral_error_c_s
        command = max(-pwm_limit, min(pwm_limit, raw_command))
        coefficient = (
            heating_to_cooling_ratio * cooling_power_per_pwm
            if command >= 0.0
            else cooling_power_per_pwm
        )
        tec_power = coefficient * command
        coupling_power = coupling * (tec_c - measured_c)
        heat_loss_power = heat_loss * (measured_c - ambient_c)
        tec_rate = (tec_power - coupling_power) / tec_capacitance
        measured_rate = (coupling_power - heat_loss_power) / measured_capacitance

        tec_c += dt_s * tec_rate
        measured_c += dt_s * measured_rate
        times_s.append((step + 1) * dt_s)
        temperatures_c.append(measured_c)

    return times_s, temperatures_c


def plot_direction(
    rows: list[dict[str, str]], direction: str, session: int, setpoint_c: float, output_name: str
) -> None:
    runs = [
        (label, kp, ki, color, *extract_longest_run(rows, session, setpoint_c, kp, ki))
        for label, kp, ki, color in KI_CASES
    ]
    # Crop to the shortest run so all three Ki settings share the same time axis.
    window_s = min(times[-1] for _, _, _, _, times, _ in runs)

    fig, ax = plt.subplots(figsize=(10.5, 5.8))
    fig.subplots_adjust(top=0.81, left=0.1, right=0.98, bottom=0.12)
    for label, kp, ki, color, times_s, temperatures_c in runs:
        sample_count = sum(time_s <= window_s for time_s in times_s)
        times_s = times_s[:sample_count]
        temperatures_c = temperatures_c[:sample_count]
        initial_c = temperatures_c[0]
        model_t, model_temp = make_model_trace(
            initial_c, setpoint_c, kp, ki, window_s
        )
        is_goldilocks = ki == 0.5
        line_width = 2.5 if is_goldilocks else 1.8
        ax.plot(
            times_s,
            temperatures_c,
            color=color,
            linewidth=line_width,
            label=f"{label} — experiment",
        )
        ax.plot(
            model_t,
            model_temp,
            color=color,
            linewidth=line_width,
            linestyle="--",
            alpha=0.88,
            label=f"{label} — simulation",
        )

    ax.axhline(setpoint_c, color="#333333", linewidth=1.2, linestyle=":")
    ax.text(
        0.99,
        setpoint_c,
        f"  setpoint {setpoint_c:g} °C",
        transform=ax.get_yaxis_transform(),
        ha="right",
        va="bottom",
        fontsize=9,
        color="#333333",
    )
    fig.suptitle(
        f"{direction}: PI integral-gain comparison (Kp = 40 PWM/°C)",
        x=0.1,
        y=0.97,
        ha="left",
        fontsize=16,
        fontweight="bold",
    )
    fig.text(
        0.1,
        0.91,
        f"Experiment vs two-lump model · {window_s:.1f} s common window · "
        "Goldilocks setting: green",
        fontsize=9,
        color="#555555",
    )
    ax.set_xlabel("Time from start of logged run (s)")
    ax.set_ylabel("Measured temperature (°C)")
    ax.set_xlim(0.0, window_s)
    ax.grid(True, alpha=0.25)
    ax.spines[["top", "right"]].set_visible(False)

    legend_handles = [
        Line2D([0], [0], color="#555555", linewidth=2, label="Experiment (solid)"),
        Line2D([0], [0], color="#555555", linewidth=2, linestyle="--", label="Simulation (dashed)"),
        *[
            Line2D([0], [0], color=color, linewidth=3, label=label)
            for label, _, _, color in KI_CASES
        ],
    ]
    ax.legend(handles=legend_handles, loc="best", ncols=2, frameon=True)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUTPUT_DIR / output_name, format="svg")
    plt.close(fig)
    print(f"Saved {direction.lower()} comparison ({window_s:.2f} s): {OUTPUT_DIR / output_name}")


def plot_p_case(
    rows: list[dict[str, str]], title: str, kp: float, output_name: str
) -> None:
    """Plot logged and simulated P-control heating and cooling runs."""
    cases = [("Heating", 5, 30.0), ("Cooling", 6, 15.0)]
    extracted = [
        (direction, session, setpoint_c, *extract_longest_run(rows, session, setpoint_c, kp, 0.0))
        for direction, session, setpoint_c in cases
    ]
    window_s = min(times_s[-1] for _, _, _, times_s, _ in extracted)

    fig, axes = plt.subplots(1, 2, figsize=(11, 5.8))
    fig.subplots_adjust(top=0.81, left=0.08, right=0.98, bottom=0.12, wspace=0.22)
    fig.suptitle(title, x=0.08, y=0.97, ha="left", fontsize=16, fontweight="bold")
    fig.text(
        0.08,
        0.91,
        f"Experiment vs two-lump model · {window_s:.1f} s common window · solid = experiment, dashed = simulation",
        fontsize=9,
        color="#555555",
    )

    for ax, (direction, _, setpoint_c, times_s, temperatures_c) in zip(axes, extracted):
        sample_count = sum(time_s <= window_s for time_s in times_s)
        times_s = times_s[:sample_count]
        temperatures_c = temperatures_c[:sample_count]
        model_t, model_temp = make_model_trace(
            temperatures_c[0], setpoint_c, kp, 0.0, window_s
        )
        ax.plot(times_s, temperatures_c, color="#277da1", linewidth=2, label="Experiment")
        ax.plot(model_t, model_temp, color="#e76f00", linewidth=2, linestyle="--", label="Simulation")
        ax.axhline(setpoint_c, color="#333333", linewidth=1.2, linestyle=":", label=f"Setpoint {setpoint_c:g} °C")
        ax.set_title(direction)
        ax.set_xlabel("Time from start of logged run (s)")
        ax.set_ylabel("Measured temperature (°C)")
        ax.set_xlim(0.0, window_s)
        ax.grid(True, alpha=0.25)
        ax.spines[["top", "right"]].set_visible(False)
        ax.legend(loc="best", frameon=True)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUTPUT_DIR / output_name, format="svg")
    plt.close(fig)
    print(f"Saved P-control comparison ({window_s:.2f} s): {OUTPUT_DIR / output_name}")


def main() -> None:
    rows = load_rows()
    for title, kp, output_name in P_CASES:
        plot_p_case(rows, title, kp, output_name)
    for direction, session, setpoint_c, output_name in DIRECTIONS:
        plot_direction(rows, direction, session, setpoint_c, output_name)


if __name__ == "__main__":
    main()
