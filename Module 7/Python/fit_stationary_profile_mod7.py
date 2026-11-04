"""Stationary-fin analysis of the 20 -> 45 C step run (Module 7).

Averages each sensor over the final 5 min of the run, checks the steady-state
criterion, fits the finite insulated-tip and semi-infinite models to
theta(x) = T(x) - T_inf, and saves a figure plus a results CSV in Module 7/data.
Run: python "Module 7/Python/fit_stationary_profile_mod7.py"
"""

import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
RUN_STAMP = "20261104_091551"
T_END_S = 3777.5  # last time on the previous step-response plot
STEP_TO_C = 45.0
AVG_WINDOW_MIN = 5.0
CRITERION_C_PER_MIN = 0.02
CRITERION_MIN = 10.0

RODS = ["rod1_C", "rod2_C", "rod3_C", "rod4_C", "rod5_C"]
X_M = np.array([0.0, 0.025, 0.050, 0.100, 0.150])  # from rod 1's hole, measured by hand
SIGMA_X_M = np.array([0.0, 0.003, 0.003, 0.003, 0.003])
L_M = 0.283  # rod-1 hole to tip (Module 7 README)
D_M = 0.011
H_PLAN = 10.0  # W/(m^2 K), course planning value
K_PLAN = 167.0  # W/(m K), 6061-T6 (Lienhard Table A.1 range 166-180)
SIGMA_OFFSET_C = 0.25  # sensor-to-sensor offset, from the spread of the readings at t = 0
SIGMA_TINF_C = 1.0  # room temperature was not logged; estimated from the start of the run


def read_columns(path):
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    return rows


def slope_per_min(t, y, t_end, minutes):
    m = (t > t_end - 60 * minutes) & (t <= t_end)
    return np.polyfit(t[m], y[m], 1)[0] * 60.0


def theta_finite(x, m, L):
    return np.cosh(m * (L - x)) / np.cosh(m * L)


def theta_semi(x, m, L):
    return np.exp(-m * x)


def fit_model(model, x, th, sig, L):
    """Weighted LS for theta0 and m. Returns m, sigma_m, theta0, chi2, dof, fit values."""
    ms = np.arange(0.5, 15.0, 0.0005)
    w = 1.0 / sig**2
    chi2 = np.empty_like(ms)
    t0s = np.empty_like(ms)
    for i, m in enumerate(ms):
        f = model(x, m, L)
        t0s[i] = np.sum(w * f * th) / np.sum(w * f * f)
        chi2[i] = np.sum(w * (th - t0s[i] * f) ** 2)
    k = int(np.argmin(chi2))
    dof = len(x) - 2
    scale = max(1.0, chi2[k] / dof)  # inflate errors if chi2 per dof > 1
    inside = ms[chi2 <= chi2[k] + scale]
    sigma_m = 0.5 * (inside.max() - inside.min())
    fit = t0s[k] * model(x, ms[k], L)
    return ms[k], sigma_m, t0s[k], chi2[k], dof, fit


def effective_sigma(x, th, sigma_stat, sigma_drift, m_guess):
    """Per-sensor sigma: statistics, drift, offset, and position error mapped through |dtheta/dx| = m*theta."""
    sig_pos = m_guess * th * SIGMA_X_M
    return np.sqrt(sigma_stat**2 + sigma_drift**2 + SIGMA_OFFSET_C**2 + sig_pos**2)


def main():
    raw = read_columns(DATA_DIR / f"raw_mod7_{RUN_STAMP}.csv")
    pi = read_columns(DATA_DIR / f"pi_log_mod7_{RUN_STAMP}.csv")
    t_all = np.array([float(r["time_s"]) for r in raw])
    keep = t_all <= T_END_S
    t = t_all[keep]
    temps = {c: np.array([float(r[c]) for r in raw])[keep] for c in RODS + ["tec_C"]}
    sp = np.array([float(r["setpoint_C"]) for r in pi])[keep]
    t_step = t[np.where(sp == STEP_TO_C)[0][0]]
    t_end = t[-1]

    # Room temperature: all six sensors before any heating, first 30 s.
    start = t < 30
    t_inf = np.mean([temps[c][start].mean() for c in RODS + ["tec_C"]])
    print(f"Step at {t_step:.1f} s; data to {t_end:.1f} s. T_inf estimate = {t_inf:.2f} C (first 30 s, all sensors)")

    # 1. Prediction record (course planning values; computed from the model, anchored on rod 1).
    m_pred = np.sqrt(4 * H_PLAN / (K_PLAN * D_M))
    print(f"\nPrediction: h = {H_PLAN} W/m2K, k = {K_PLAN} W/mK, d = {D_M} m, L = {L_M} m -> "
          f"m = {m_pred:.2f} 1/m, mL = {m_pred * L_M:.2f}, 1/m = {1 / m_pred:.3f} m")

    # 2. Steady-state criterion on the final 10 min, plus the latest earlier window that satisfied it.
    print(f"\nCriterion: |dT/dt| < {CRITERION_C_PER_MIN} C/min on every rod sensor over {CRITERION_MIN:g} min")
    slopes10 = {c: slope_per_min(t, temps[c], t_end, CRITERION_MIN) for c in RODS}
    for c in RODS:
        print(f"  {c}: last 10 min {slopes10[c]:+.3f} C/min  last 5 min {slope_per_min(t, temps[c], t_end, 5):+.3f}")
    met = all(abs(s) < CRITERION_C_PER_MIN for s in slopes10.values())
    print(f"  Final window: {'MET' if met else 'NOT MET'}")
    earlier = None
    for te in np.arange(t_end, t_step + 900, -10.0):
        if all(abs(slope_per_min(t, temps[c], te, CRITERION_MIN)) < CRITERION_C_PER_MIN for c in RODS):
            earlier = te
            break
    print(f"  Latest 10-min window meeting it: " + (f"ending at {earlier:.0f} s" if earlier else "none"))

    # 3. Average over the final 5 min.
    win = (t > t_end - 60 * AVG_WINDOW_MIN) & (t <= t_end)
    mean = np.array([temps[c][win].mean() for c in RODS])
    sigma_stat = np.array([
        (temps[c][win] - np.polyval(np.polyfit(t[win], temps[c][win], 1), t[win])).std(ddof=2) / np.sqrt(win.sum())
        for c in RODS
    ])
    sigma_drift = np.array([abs(slopes10[c]) * AVG_WINDOW_MIN for c in RODS])  # change over one more window
    theta = mean - t_inf
    print(f"\nAveraged {t[win][0]:.0f}-{t_end:.0f} s ({win.sum()} samples/sensor)")

    sigma = effective_sigma(X_M, theta, sigma_stat, sigma_drift, m_pred)
    # Refine position-error term with the fitted m (one iteration).
    mf0, *_ = fit_model(theta_finite, X_M, theta, sigma, L_M)
    sigma = effective_sigma(X_M, theta, sigma_stat, sigma_drift, mf0)

    # 5/6/7/8. Fits.
    mf, smf, t0f, chif, dof, fit_f = fit_model(theta_finite, X_M, theta, sigma, L_M)
    ms, sms, t0s, chis, _, fit_s = fit_model(theta_semi, X_M, theta, sigma, L_M)
    print("\nPer-sensor values")
    print(f"{'rod':<7}{'x (m)':>8}{'T (C)':>8}{'theta':>8}{'sigma':>7}{'stat':>7}{'drift':>7}{'finite fit':>11}{'semi fit':>10}")
    for i, c in enumerate(RODS):
        print(f"{c[:4]+c[4]:<7}{X_M[i]:8.3f}{mean[i]:8.2f}{theta[i]:8.2f}{sigma[i]:7.2f}{sigma_stat[i]:7.3f}"
              f"{sigma_drift[i]:7.2f}{fit_f[i]:11.2f}{fit_s[i]:10.2f}")
    print(f"\nFinite insulated tip : m = {mf:.3f} +/- {smf:.3f} 1/m, theta0 = {t0f:.2f} C, chi2/dof = {chif:.2f}/{dof}")
    print(f"Semi-infinite        : m = {ms:.3f} +/- {sms:.3f} 1/m, theta0 = {t0s:.2f} C, chi2/dof = {chis:.2f}/{dof}")
    print(f"Decay length 1/m: finite {1 / mf:.4f} m (+/- {smf / mf**2:.4f}), semi {1 / ms:.4f} m (+/- {sms / ms**2:.4f})")
    shift = ms - mf
    print(f"Ignoring the tip changes m by {shift:+.3f} 1/m ({100 * shift / mf:+.1f}%), "
          f"= {abs(shift) / smf:.2f} x sigma_m(finite)")
    print(f"mL = {mf * L_M:.2f} (finite fit); measured theta0 from rod 1 = {theta[0]:.2f} C")

    # Sensitivity to T_inf and to dropping the base point.
    print("\nSensitivity of m to T_inf (finite / semi):")
    for dT in (-SIGMA_TINF_C, SIGMA_TINF_C):
        th2 = mean - (t_inf + dT)
        s2 = effective_sigma(X_M, th2, sigma_stat, sigma_drift, mf)
        a = fit_model(theta_finite, X_M, th2, s2, L_M)[0]
        b = fit_model(theta_semi, X_M, th2, s2, L_M)[0]
        print(f"  T_inf {dT:+.1f} C: m_finite = {a:.3f}, m_semi = {b:.3f}")
    # Free-T_inf check: fit T directly with T_inf as an extra parameter on a grid.
    best = None
    for ti in np.arange(18.0, 31.0, 0.05):
        th2 = mean - ti
        if np.any(th2 <= 0):
            continue
        r = fit_model(theta_finite, X_M, th2, sigma, L_M)
        if best is None or r[3] < best[1][3]:
            best = (ti, r)
    print(f"  Free-T_inf finite fit: T_inf = {best[0]:.2f} C, m = {best[1][0]:.3f}, chi2 = {best[1][3]:.2f}")

    # 10. Compare with the prediction (anchored on measured rod 1).
    pred = theta[0] * theta_finite(X_M, m_pred, L_M)
    print("\nPredicted vs measured theta (prediction anchored on rod 1):")
    for i, c in enumerate(RODS):
        print(f"  {c}: predicted {pred[i]:.2f}, measured {theta[i]:.2f} +/- {sigma[i]:.2f}, diff {theta[i] - pred[i]:+.2f}")
    print(f"  m measured/predicted = {mf / m_pred:.3f} (finite), implied h = {mf**2 * K_PLAN * D_M / 4:.2f} W/m2K at k = {K_PLAN}")
    bi = H_PLAN * D_M / (4 * K_PLAN)
    bi_meas = (mf * D_M / 4) ** 2
    print(f"  Bi_perp: planning {bi:.2e}, from fitted m {bi_meas:.2e}")

    # Figure: theta(x) with fits and prediction, and the two residual sets.
    xs = np.linspace(0, 0.19, 300)
    fig, (ax, axr) = plt.subplots(
        2, 1, figsize=(11, 10), sharex=True, gridspec_kw={"height_ratios": [3, 2]}
    )
    ax.errorbar(X_M, theta, yerr=sigma, xerr=SIGMA_X_M, fmt="ko", ms=7, capsize=4, lw=1.5, label="Measured (final 5 min mean)")
    ax.plot(xs, t0f * theta_finite(xs, mf, L_M), color="#d62728", lw=2.5,
            label=f"Finite, insulated tip: m = {mf:.2f} ± {smf:.2f} 1/m")
    ax.plot(xs, t0s * theta_semi(xs, ms, L_M), color="#1f77b4", lw=2.5, ls="--",
            label=f"Semi-infinite: m = {ms:.2f} ± {sms:.2f} 1/m")
    ax.plot(xs, theta[0] * theta_finite(xs, m_pred, L_M), color="gray", lw=2, ls=":",
            label=f"Prediction (h = {H_PLAN:g}, k = {K_PLAN:g}): m = {m_pred:.2f} 1/m")
    ax.set_ylabel("θ = T − T∞ (°C)", fontsize=13)
    ax.set_title(f"Stationary profile, final {AVG_WINDOW_MIN:g} min (T∞ = {t_inf:.1f} °C)", fontsize=15)
    ax.legend(fontsize=11)
    axr.axhline(0, color="black", lw=1)
    off = 0.0025
    axr.errorbar(X_M - off, theta - fit_f, yerr=sigma, fmt="o", color="#d62728", capsize=4, ms=7, label="Finite model")
    axr.errorbar(X_M + off, theta - fit_s, yerr=sigma, fmt="s", color="#1f77b4", capsize=4, ms=7, label="Semi-infinite model")
    axr.set_ylabel("Residual θ − fit (°C)", fontsize=13)
    axr.set_xlabel("Position x from rod 1 (m)", fontsize=13)
    axr.set_title("Residuals", fontsize=15)
    axr.legend(fontsize=11)
    for a in (ax, axr):
        a.grid(True, alpha=0.3)
        a.tick_params(labelsize=12)
    fig.tight_layout()
    fig.savefig(DATA_DIR / "stationary_profile_mod7.png", dpi=150)

    with open(DATA_DIR / "stationary_profile_mod7.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["rod", "x_m", "mean_T_C", "theta_C", "sigma_C", "fit_finite_C", "fit_semi_C", "pred_C"])
        for i, c in enumerate(RODS):
            w.writerow([c, X_M[i], f"{mean[i]:.3f}", f"{theta[i]:.3f}", f"{sigma[i]:.3f}",
                        f"{fit_f[i]:.3f}", f"{fit_s[i]:.3f}", f"{pred[i]:.3f}"])
    print("\nSaved stationary_profile_mod7.png and stationary_profile_mod7.csv")


if __name__ == "__main__":
    main()
