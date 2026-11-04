"""Calibrate the five rod thermistors against the TEC-base thermistor.

Reads one raw six-thermistor CSV written by serial_plot_mod7.py (columns
time_s, tec_C, rod1_C ... rod5_C, pwm, heat_cool, setpoint_C, safety) and,
treating tec_C as the reference temperature, fits for each rod i

    tec_C = a_i + b_i * rod_i_C        (linear least squares)

over a calibration range you choose, by Arduino time or by TEC temperature.

Outputs (all NEW files in Module 7/data/calibration/; the raw CSV is only
ever opened for reading and is never changed):
  <raw name>_cal_<run time>_stats.csv      per thermistor: n, mean, std, std error,
                                           min, max, offset from tec_C
  <raw name>_cal_<run time>_vs_time.png    all six thermistors vs time, one graph
  <raw name>_cal_<run time>_table.csv     a_i, b_i, point count, range, residual stats
  <raw name>_cal_<run time>_corrected.csv  every raw column unchanged, plus
                                           rod1_corrected_C ... rod5_corrected_C
  <raw name>_cal_<run time>_fits.png       rod_i_C vs tec_C, identity + fitted line
  <raw name>_cal_<run time>_residuals.png  corrected residual vs tec_C

Examples (run from the Module 7 folder):
  venv/bin/python Python/calibrate_thermistors_mod7.py data/raw_mod7_20261026_143005.csv --time 120 900
  venv/bin/python Python/calibrate_thermistors_mod7.py data/raw_mod7_20261026_143005.csv --temp 18 40
With neither --time nor --temp, the whole file is used.
"""

import argparse
import csv
from datetime import datetime
import math
from pathlib import Path
import sys

import matplotlib.pyplot as plt
import numpy as np

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
RAW_COLUMNS = [
    "time_s", "tec_C", "rod1_C", "rod2_C", "rod3_C", "rod4_C", "rod5_C",
    "pwm", "heat_cool", "setpoint_C", "safety",
]
REFERENCE_COLUMN = "tec_C"
ROD_CHANNELS = ["rod1_C", "rod2_C", "rod3_C", "rod4_C", "rod5_C"]

# Same colors as the live GUI, so rod 3 is purple everywhere.
ROD_COLORS = {
    "rod1_C": (31 / 255, 119 / 255, 180 / 255),
    "rod2_C": (255 / 255, 127 / 255, 14 / 255),
    "rod3_C": (148 / 255, 103 / 255, 189 / 255),
    "rod4_C": (140 / 255, 86 / 255, 75 / 255),
    "rod5_C": (23 / 255, 190 / 255, 207 / 255),
}

OUTPUT_DIR = Path(__file__).resolve().parents[1] / "data" / "calibration"
CORRECTED_DECIMALS = 4  # digits written for the corrected temperatures

TABLE_COLUMNS = [
    "channel",
    "a_C",                 # intercept a_i, in C
    "b",                   # slope b_i, dimensionless (C per C)
    "n_points",            # rows used in this channel's fit
    "selection",           # the range you asked for, e.g. "time_s 120 to 900"
    "cal_tec_min_C",       # lowest tec_C actually fitted
    "cal_tec_max_C",       # highest tec_C actually fitted
    "residual_mean_C",
    "residual_std_C",
    "max_abs_residual_C",
]

STATS_COLUMNS = [
    "channel",
    "n_points",            # rows used for this channel's statistics
    "selection",
    "mean_C",
    "std_C",               # sample standard deviation (ddof=1): reading noise
    "std_error_C",         # std / sqrt(n): uncertainty of the mean
    "min_C",
    "max_C",
    "offset_from_tec_C",   # mean of (channel - tec_C), row by row
    "offset_std_C",        # std of (channel - tec_C)
]

# Below this tec_C span the slope b is set by noise, not by the sensor, so
# the fit is flagged and the rod - TEC offset is the better correction.
MIN_SLOPE_SPAN_C = 1.0


# ---------------------------------------------------------------------------
# File input
# ---------------------------------------------------------------------------
def read_raw_csv(path):
    """Read the raw CSV and return (raw_rows, data).

    raw_rows is a list of dicts holding every field EXACTLY as text, the way
    it appears in the file; these are copied unchanged into the corrected
    CSV, so the raw values there can never drift from the original.

    data is a dict of numpy arrays, one per numeric column, for the math:
    data["rod2_C"][k] is rod 2's temperature in row k. Text that isn't a
    number (e.g. "nan" from a faulted thermistor) becomes NaN.

    The file is opened with "r" (read only), so this cannot change it.
    """
    with open(path, "r", newline="") as raw_file:
        reader = csv.DictReader(raw_file)
        if reader.fieldnames != RAW_COLUMNS:
            sys.exit(
                f"{path.name} does not have the expected raw columns.\n"
                f"  expected: {','.join(RAW_COLUMNS)}\n"
                f"  found:    {','.join(reader.fieldnames or [])}"
            )
        raw_rows = list(reader)

    if not raw_rows:
        sys.exit(f"{path.name} has a header but no data rows.")

    def to_number(text):
        try:
            return float(text)
        except ValueError:
            return math.nan

    data = {}
    for column in ["time_s", REFERENCE_COLUMN, *ROD_CHANNELS]:
        data[column] = np.array([to_number(row[column]) for row in raw_rows])
    data["safety"] = np.array([row["safety"] for row in raw_rows])
    return raw_rows, data


# ---------------------------------------------------------------------------
# Range selection
# ---------------------------------------------------------------------------
def select_calibration_rows(data, time_range, temp_range):
    """Return (in_range, description).

    in_range is a True/False array with one entry per row: True means the
    row is inside the range you chose AND is safe to use, i.e.
      - safety is OK (CUTOFF or SENSOR_FAULT rows are never fitted), and
      - tec_C is a real number.
    Each rod's fit additionally skips rows where that rod reads NaN, so the
    five channels can end up with slightly different point counts.

    time_range / temp_range are (low, high) pairs, inclusive at both ends,
    or None. temp_range is applied to the reference temperature tec_C.
    """
    usable = (data["safety"] == "OK") & np.isfinite(data[REFERENCE_COLUMN])

    if time_range is not None:
        low, high = sorted(time_range)
        in_window = (data["time_s"] >= low) & (data["time_s"] <= high)
        description = f"time_s {low:g} to {high:g} s"
    elif temp_range is not None:
        low, high = sorted(temp_range)
        tec = data[REFERENCE_COLUMN]
        in_window = (tec >= low) & (tec <= high)
        description = f"tec_C {low:g} to {high:g} C"
    else:
        in_window = np.ones(len(usable), dtype=bool)
        description = "all rows"

    return usable & in_window, description


# ---------------------------------------------------------------------------
# Fitting
# ---------------------------------------------------------------------------
def fit_channel(rod, tec):
    """Linear least-squares fit of tec = a + b * rod. Returns (a, b).

    Least squares picks the a and b that make the sum of squared
    differences  sum_k (a + b * rod_k - tec_k)^2  as small as possible.
    np.linalg.lstsq solves that for us once the problem is written as a
    matrix equation  A @ [a, b] = tec, where each row of A is [1, rod_k]
    (the 1 multiplies a, the rod value multiplies b).
    """
    A = np.column_stack([np.ones_like(rod), rod])
    (a, b), *_ = np.linalg.lstsq(A, tec, rcond=None)
    return a, b


# ---------------------------------------------------------------------------
# Residual calculation
# ---------------------------------------------------------------------------
def residual_stats(residuals):
    """Summarize the corrected residuals of the fitted points.

    residual = (a + b * rod) - tec  is how far the corrected rod reading is
    from the reference: positive means the corrected rod reads too warm.
    For a least-squares line with an intercept the mean is ~0 by
    construction (any leftover is round-off), so the standard deviation and
    the maximum absolute residual are the numbers that describe calibration
    quality. The standard deviation uses ddof=1 (the n - 1 "sample"
    formula).
    """
    return {
        "residual_mean_C": float(np.mean(residuals)),
        "residual_std_C": float(np.std(residuals, ddof=1)),
        "max_abs_residual_C": float(np.max(np.abs(residuals))),
    }


def calibrate(data, in_range, description):
    """Fit every rod channel and return a list of table rows (dicts)."""
    tec = data[REFERENCE_COLUMN]
    table = []
    for channel in ROD_CHANNELS:
        rod = data[channel]
        # Rows used for THIS channel: in range, and this rod reads a number.
        fit_rows = in_range & np.isfinite(rod)
        n_points = int(np.count_nonzero(fit_rows))

        # Two points always fit a line exactly (zero residuals, meaningless
        # statistics), so at least three are required; the rod values must
        # also not all be identical (otherwise the slope is undefined).
        if n_points < 3 or np.ptp(rod[fit_rows]) == 0:
            print(f"  {channel}: only {n_points} usable point(s) or no temperature "
                  f"spread in the range - not fitted, no correction written.")
            table.append({"channel": channel, "n_points": n_points,
                          "selection": description})
            continue

        a, b = fit_channel(rod[fit_rows], tec[fit_rows])
        residuals = (a + b * rod[fit_rows]) - tec[fit_rows]

        row = {
            "channel": channel,
            "a_C": float(a),
            "b": float(b),
            "n_points": n_points,
            "selection": description,
            "cal_tec_min_C": float(tec[fit_rows].min()),
            "cal_tec_max_C": float(tec[fit_rows].max()),
        }
        row.update(residual_stats(residuals))
        table.append(row)
    return table


def is_fitted(table_row):
    return "a_C" in table_row


# ---------------------------------------------------------------------------
# Per-thermistor statistics
# ---------------------------------------------------------------------------
def channel_stats(data, in_range, description):
    """Mean, standard deviation, etc. of each thermistor over the range.

    std_C is the scatter of the readings (ddof=1). If the true temperature
    was steady over the range, this is the thermistor's noise. std_error_C
    = std / sqrt(n) is the uncertainty of the mean. offset_from_tec_C is the
    average of (rod - tec) taken row by row, i.e. how far that rod reads
    above (+) or below (-) the reference; subtracting it is the simplest
    correction when the range covers only one temperature.
    """
    tec = data[REFERENCE_COLUMN]
    stats = []
    for channel in [REFERENCE_COLUMN, *ROD_CHANNELS]:
        values = data[channel]
        rows = in_range & np.isfinite(values)
        n_points = int(np.count_nonzero(rows))
        row = {"channel": channel, "n_points": n_points, "selection": description}
        if n_points >= 2:
            std = float(np.std(values[rows], ddof=1))
            row.update({
                "mean_C": float(np.mean(values[rows])),
                "std_C": std,
                "std_error_C": std / math.sqrt(n_points),
                "min_C": float(np.min(values[rows])),
                "max_C": float(np.max(values[rows])),
            })
            if channel != REFERENCE_COLUMN:
                difference = values[rows] - tec[rows]
                row["offset_from_tec_C"] = float(np.mean(difference))
                row["offset_std_C"] = float(np.std(difference, ddof=1))
        stats.append(row)
    return stats


def channel_label(channel):
    """'tec_C' -> 'TEC', 'rod3_C' -> 'Rod 3' (matches the live GUI)."""
    if channel == REFERENCE_COLUMN:
        return "TEC"
    return channel.replace("_C", "").replace("rod", "Rod ")


# ---------------------------------------------------------------------------
# Output: file names
# ---------------------------------------------------------------------------
def new_output_path(stem, suffix):
    """A path in OUTPUT_DIR that does not exist yet. Files are created with
    mode "x" (fails if the file exists), so nothing is ever overwritten."""
    path = OUTPUT_DIR / f"{stem}{suffix}"
    n = 2
    while path.exists():
        path = OUTPUT_DIR / f"{stem}_{n}{suffix}"
        n += 1
    return path


# ---------------------------------------------------------------------------
# Output: calibration table (printed and saved)
# ---------------------------------------------------------------------------
def print_stats(stats, description):
    print(f"Thermistor statistics ({description}), all in °C")
    header = (f"{'':<6} {'n':>5} {'mean':>8} {'std dev':>8} {'std err':>8}"
              f" {'min':>7} {'max':>7}   {'rod - TEC (mean ± std)':<22}")
    print(header)
    print("-" * len(header))
    for row in stats:
        label = channel_label(row["channel"])
        if "mean_C" not in row:
            print(f"{label:<6} {row['n_points']:>5}  too few readings")
            continue
        offset = (f"{row['offset_from_tec_C']:+.3f} ± {row['offset_std_C']:.3f}"
                  if "offset_from_tec_C" in row else "(reference)")
        print(f"{label:<6} {row['n_points']:>5} {row['mean_C']:>8.3f} {row['std_C']:>8.4f}"
              f" {row['std_error_C']:>8.4f} {row['min_C']:>7.2f} {row['max_C']:>7.2f}"
              f"   {offset:<22}")


def save_stats(stats, path):
    with open(path, "x", newline="") as stats_file:
        writer = csv.DictWriter(stats_file, fieldnames=STATS_COLUMNS)
        writer.writeheader()
        writer.writerows(stats)  # TEC has blank offset cells


def print_table(table):
    fitted_rows = [row for row in table if is_fitted(row)]
    if fitted_rows:
        tec_min = min(row["cal_tec_min_C"] for row in fitted_rows)
        tec_max = max(row["cal_tec_max_C"] for row in fitted_rows)
        print(f"Linear fit  tec = a + b * rod   (TEC {tec_min:.2f} to {tec_max:.2f} °C)")
    header = (f"{'':<6} {'n':>5} {'a (°C)':>9} {'b':>8} {'resid std (°C)':>15}"
              f" {'max |resid| (°C)':>17}")
    print(header)
    print("-" * len(header))
    for row in table:
        label = channel_label(row["channel"])
        if not is_fitted(row):
            print(f"{label:<6} {row['n_points']:>5}  not fitted")
            continue
        print(f"{label:<6} {row['n_points']:>5} {row['a_C']:>9.3f} {row['b']:>8.4f}"
              f" {row['residual_std_C']:>15.4f} {row['max_abs_residual_C']:>17.4f}")

    if fitted_rows and tec_max - tec_min < MIN_SLOPE_SPAN_C:
        print(f"\nWARNING: TEC only spans {tec_max - tec_min:.2f} °C in this range, so a and b"
              f" are set by noise\nand are not a usable calibration. Use the rod - TEC offsets"
              f" above, or calibrate on\na run where the temperature changes by"
              f" at least {MIN_SLOPE_SPAN_C:g} °C.")


def save_table(table, path):
    with open(path, "x", newline="") as table_file:
        writer = csv.DictWriter(table_file, fieldnames=TABLE_COLUMNS)
        writer.writeheader()
        writer.writerows(table)  # channels that weren't fitted get blank cells


# ---------------------------------------------------------------------------
# Output: corrected-data CSV
# ---------------------------------------------------------------------------
def save_corrected_csv(raw_rows, data, table, path):
    """Write every raw row with all 11 raw columns copied unchanged (as the
    original text), followed by rod1_corrected_C ... rod5_corrected_C.

    The correction a_i + b_i * rod_i_C is applied to EVERY row - including
    rows outside the calibration range, so check cal_tec_min_C/max_C in the
    table before trusting values far outside it. A rod that reads nan, or a
    channel that couldn't be fitted, gets "nan" in its corrected column.
    """
    fits = {row["channel"]: row for row in table if is_fitted(row)}
    corrected_columns = [channel.replace("_C", "_corrected_C") for channel in ROD_CHANNELS]

    with open(path, "x", newline="") as corrected_file:
        writer = csv.DictWriter(corrected_file, fieldnames=RAW_COLUMNS + corrected_columns)
        writer.writeheader()
        for k, raw_row in enumerate(raw_rows):
            out_row = dict(raw_row)  # a copy: the raw text, untouched
            for channel, corrected_column in zip(ROD_CHANNELS, corrected_columns):
                rod_value = data[channel][k]
                if channel in fits and math.isfinite(rod_value):
                    corrected = fits[channel]["a_C"] + fits[channel]["b"] * rod_value
                    out_row[corrected_column] = f"{corrected:.{CORRECTED_DECIMALS}f}"
                else:
                    out_row[corrected_column] = "nan"
            writer.writerow(out_row)


# ---------------------------------------------------------------------------
# Output: plots
# ---------------------------------------------------------------------------
def make_axes_grid(title):
    """Five panels (one per rod) on a 2 x 3 grid; the sixth is hidden."""
    fig, axes = plt.subplots(2, 3, figsize=(15, 9), constrained_layout=True)
    axes = axes.ravel()
    axes[-1].set_visible(False)
    fig.suptitle(title)
    return fig, axes[:len(ROD_CHANNELS)]


def plot_temperatures_vs_time(data, in_range, stats, description, path):
    """All six thermistors against Arduino time on one set of axes.

    The calibration range is shaded so you can see which readings went into
    the statistics and fit. Each legend entry gives that channel's mean ±
    standard deviation over the range. TEC is drawn thicker and in black,
    as in the live GUI.
    """
    time = data["time_s"]
    fig, ax = plt.subplots(figsize=(12, 6), constrained_layout=True)

    # Shade each continuous stretch of in-range rows.
    order = np.argsort(time)
    shaded = in_range[order]
    start = None
    for k, inside in enumerate(np.append(shaded, False)):
        if inside and start is None:
            start = k
        elif not inside and start is not None:
            ax.axvspan(time[order][start], time[order][k - 1], color="0.9",
                       label="calibration range" if start == np.argmax(shaded) else None)
            start = None

    stats_by_channel = {row["channel"]: row for row in stats}
    for channel in [REFERENCE_COLUMN, *ROD_CHANNELS]:
        row = stats_by_channel[channel]
        label = channel_label(channel)
        if "mean_C" in row:
            label += f": {row['mean_C']:.3f} ± {row['std_C']:.3f} °C"
        is_tec = channel == REFERENCE_COLUMN
        ax.plot(time, data[channel], "-",
                color="black" if is_tec else ROD_COLORS[channel],
                linewidth=2.5 if is_tec else 1.3, label=label)

    ax.set_title(f"Thermistor temperatures vs time (mean ± std over {description})")
    ax.set_xlabel("Arduino time, time_s (s)")
    ax.set_ylabel("Raw temperature (°C)")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=9, loc="best")
    fig.savefig(path, dpi=150)
    return fig


def plot_fits(data, in_range, table, description, path):
    """Each rod temperature (y) against the reference tec_C (x).

    Colored points were fitted; gray points are valid readings outside the
    calibration range, shown for context only. The fit is tec = a + b*rod,
    so on these axes (rod on y) the fitted line is rod = (tec - a) / b.
    A perfect, already-calibrated rod would sit on the dashed identity line.
    """
    tec = data[REFERENCE_COLUMN]
    fig, axes = make_axes_grid(f"Rod thermistors vs TEC reference ({description})")
    for ax, row in zip(axes, table):
        channel = row["channel"]
        rod = data[channel]
        valid = np.isfinite(rod) & np.isfinite(tec) & (data["safety"] == "OK")
        fitted = valid & in_range

        ax.plot(tec[valid & ~in_range], rod[valid & ~in_range], ".", color="0.75",
                markersize=3, label="outside range")
        ax.plot(tec[fitted], rod[fitted], ".", color=ROD_COLORS[channel],
                markersize=4, label="fitted points")

        if np.any(valid):
            line_tec = np.linspace(tec[valid].min(), tec[valid].max(), 2)
            ax.plot(line_tec, line_tec, "k--", linewidth=1, label="identity (rod = tec)")
            if is_fitted(row):
                ax.plot(line_tec, (line_tec - row["a_C"]) / row["b"], "-", color="red",
                        linewidth=1.5,
                        label=f"fit: tec = {row['a_C']:.3f} + {row['b']:.4f} rod")

        ax.set_title(channel.replace("_C", "").replace("rod", "Rod "))
        ax.set_xlabel("TEC reference temperature, tec_C (°C)")
        ax.set_ylabel(f"Raw rod temperature, {channel} (°C)")
        ax.grid(True, alpha=0.3)
        ax.legend(fontsize=8)
    fig.savefig(path, dpi=150)
    return fig


def plot_residuals(data, in_range, table, description, path):
    """Corrected residual (a + b*rod) - tec against tec_C for each rod.

    Fitted points are colored; points outside the calibration range (gray)
    show how well the correction extrapolates. The red band is +/- one
    residual standard deviation of the fitted points.
    """
    tec = data[REFERENCE_COLUMN]
    fig, axes = make_axes_grid(f"Corrected residuals ({description})")
    for ax, row in zip(axes, table):
        channel = row["channel"]
        ax.set_title(channel.replace("_C", "").replace("rod", "Rod "))
        ax.set_xlabel("TEC reference temperature, tec_C (°C)")
        ax.set_ylabel("Residual, (a + b·rod) − tec_C (°C)")
        ax.grid(True, alpha=0.3)
        if not is_fitted(row):
            ax.text(0.5, 0.5, "not fitted", transform=ax.transAxes, ha="center")
            continue

        rod = data[channel]
        valid = np.isfinite(rod) & np.isfinite(tec) & (data["safety"] == "OK")
        fitted = valid & in_range
        residual = (row["a_C"] + row["b"] * rod) - tec

        ax.plot(tec[valid & ~in_range], residual[valid & ~in_range], ".", color="0.75",
                markersize=3, label="outside range")
        ax.plot(tec[fitted], residual[fitted], ".", color=ROD_COLORS[channel],
                markersize=4, label="fitted points")
        ax.axhline(0, color="k", linewidth=1)
        std = row["residual_std_C"]
        ax.axhspan(-std, std, color="red", alpha=0.1, label=f"±1 std = {std:.3f} °C")
        ax.legend(fontsize=8)
    fig.savefig(path, dpi=150)
    return fig


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Fit tec_C = a + b * rod_i_C for each rod thermistor.")
    parser.add_argument("raw_csv", type=Path, help="raw six-thermistor CSV from serial_plot_mod7.py")
    range_choice = parser.add_mutually_exclusive_group()
    range_choice.add_argument("--time", nargs=2, type=float, metavar=("START_S", "END_S"),
                              help="calibrate on rows with START_S <= time_s <= END_S")
    range_choice.add_argument("--temp", nargs=2, type=float, metavar=("LOW_C", "HIGH_C"),
                              help="calibrate on rows with LOW_C <= tec_C <= HIGH_C")
    parser.add_argument("--no-show", action="store_true",
                        help="save the plots without opening plot windows")
    args = parser.parse_args()

    # ----- File input -----
    raw_path = args.raw_csv.resolve()
    if not raw_path.is_file():
        sys.exit(f"File not found: {raw_path}")
    raw_rows, data = read_raw_csv(raw_path)
    tec = data[REFERENCE_COLUMN]
    print(f"Read {len(raw_rows)} rows from {raw_path.name}")
    print(f"  time_s spans {np.nanmin(data['time_s']):.2f} to {np.nanmax(data['time_s']):.2f} s;"
          f" tec_C spans {np.nanmin(tec):.2f} to {np.nanmax(tec):.2f} C")

    # ----- Range selection -----
    in_range, description = select_calibration_rows(data, args.time, args.temp)
    print(f"Calibration range: {description} -> {np.count_nonzero(in_range)} usable rows"
          f" (safety OK, tec_C valid)")
    if not np.any(in_range):
        sys.exit("No usable rows in that range. Check the spans printed above.")

    # ----- Statistics, fitting + residual calculation -----
    stats = channel_stats(data, in_range, description)
    table = calibrate(data, in_range, description)
    print()
    print_stats(stats, description)
    print()
    print_table(table)
    print()

    # ----- Output -----
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stem = f"{raw_path.stem}_cal_{datetime.now():%Y%m%d_%H%M%S}"
    stats_path = new_output_path(stem, "_stats.csv")
    table_path = new_output_path(stem, "_table.csv")
    corrected_path = new_output_path(stem, "_corrected.csv")
    time_plot_path = new_output_path(stem, "_vs_time.png")
    fits_path = new_output_path(stem, "_fits.png")
    residuals_path = new_output_path(stem, "_residuals.png")

    save_stats(stats, stats_path)
    save_table(table, table_path)
    save_corrected_csv(raw_rows, data, table, corrected_path)
    plot_temperatures_vs_time(data, in_range, stats, description, time_plot_path)
    plot_fits(data, in_range, table, description, fits_path)
    plot_residuals(data, in_range, table, description, residuals_path)

    for path in (stats_path, table_path, corrected_path, time_plot_path, fits_path,
                 residuals_path):
        print(f"Saved {path}")

    if not args.no_show:
        plt.show()


if __name__ == "__main__":
    main()
