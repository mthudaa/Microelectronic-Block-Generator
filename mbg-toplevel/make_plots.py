#!/usr/bin/env python3
"""Regenerate the MBG-D08 top-level simulation plot (D08 + NEURO1B).

Reads the ngspice `wrdata` outputs produced by mbg-d08_pre_tb.spice and
mbg-d08_post_tb.spice and writes:

    mbg-d08_simulation_plot.png    all ten outputs + differential input

The old relaxation-oscillator temperature-sensor plot was removed: the temp_out
pin now belongs to NEURO1B, a spiking sensor that stays at 0 V unless its input
is driven (this bench does not drive it).

Usage:  python3 make_plots.py
"""
import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
PRE = os.path.join(HERE, "mbg-d08_pre_tr.dat")
POST = os.path.join(HERE, "mbg-d08_post_tr.dat")

SIGNALS = ["deepseek_ota", "gpt_ota", "oxa_ota",
           "deepseek_cmp", "gpt_cmp", "oxa_cmp",
           "deepseek_vref", "gpt_vref", "oxa_vref",
           "temp_out", "vdiff"]

C_PRE, C_POST = "#1f77b4", "#d62728"

# Panel titles: model + block + (committee-fixed pin name). Data columns stay keyed by pin name.
MODEL = {"gpt": "GPT-6.2 Sol", "oxa": "Opus 5.5", "deepseek": "Gemini 4 Argon (neon fallback)"}
KIND = {"ota": "OTA", "cmp": "comparator", "vref": "1.2 V reference"}


T_SETTLE = 8e-6  # same rule as the NEURO1B standalone bench: count spikes after the settling window


def neuro_spikes(t, v):
    """Rising threshold crossings with hysteresis (30 % / 70 % of the swing), after T_SETTLE."""
    keep = t >= T_SETTLE
    t, v = t[keep], v[keep]
    if len(v) < 3 or v.max() - v.min() < 0.2:
        return np.array([])
    hi, lo = v.min() + 0.7 * np.ptp(v), v.min() + 0.3 * np.ptp(v)
    edges, armed = [], v[0] < lo
    for k in range(1, len(v)):
        if armed and v[k] >= hi:
            f = (hi - v[k - 1]) / (v[k] - v[k - 1]) if v[k] != v[k - 1] else 0
            edges.append(t[k - 1] + f * (t[k] - t[k - 1]))
            armed = False
        elif not armed and v[k] <= lo:
            armed = True
    return np.array(edges)


def neuro_rate(t, v):
    """Spike rate in Hz (0 if fewer than three spikes)."""
    e = neuro_spikes(t, v)
    return (len(e) - 1) / (e[-1] - e[0]) if len(e) >= 3 else 0.0


def display(name):
    if name == "vdiff":
        return "INP-INN"
    if name == "temp_out":
        return "NEURO1B (Opus 5.5), pin temp_out, 2 µA input from 1 µs"
    model, kind = name.split("_")
    return f"{MODEL[model]} {KIND[kind]} (pin {name})"


def load(path):
    """ngspice wrdata writes (time, value) column pairs per vector."""
    d = np.loadtxt(path)
    t = d[:, 0]
    return t, {n: d[:, 2 * i + 1] for i, n in enumerate(SIGNALS)}


def plot_all(tp, cp, tq, cq, out):
    fig, axes = plt.subplots(4, 3, figsize=(20, 16.25))
    fig.suptitle("MBG-D08 + NEURO1B: pre-layout vs post-layout transient "
                 "(100 µs, CLK = 10 µs, 27 °C)", fontsize=17)
    for k, name in enumerate(SIGNALS):
        ax = axes[k // 3][k % 3]
        ax.plot(tp * 1e6, cp[name] * (1e3 if name == "vdiff" else 1),
                color=C_PRE, lw=0.8, label="pre")
        ax.plot(tq * 1e6, cq[name] * (1e3 if name == "vdiff" else 1),
                color=C_POST, lw=0.8, label="post PEX")
        ax.set_title(display(name), fontsize=12)
        ax.set_ylabel("mV" if name == "vdiff" else "V")
        ax.grid(alpha=0.3)
        if k == 0:
            ax.legend(loc="upper left", fontsize=10)
        if k // 3 == 3:
            ax.set_xlabel("Time (µs)")
    # NEURO1B zoom: the spikes on temp_out between 8 and 14 us, with the measured rates
    ax = axes[3][2]
    for t_, c_, col, lab in ((tp, cp, C_PRE, "pre"), (tq, cq, C_POST, "post PEX")):
        m = (t_ * 1e6 >= 8) & (t_ * 1e6 <= 14)
        ax.plot(t_[m] * 1e6, c_["temp_out"][m], color=col, lw=1.0,
                label=f"{lab}: {neuro_rate(t_, c_['temp_out']) / 1e3:.0f} kHz")
    ax.set_title("NEURO1B (Opus 5.5) spikes on temp_out, zoom 8-14 µs", fontsize=12)
    ax.set_xlabel("Time (µs)")
    ax.set_ylabel("V")
    ax.grid(alpha=0.3)
    ax.legend(loc="upper right", fontsize=10)
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    fig.savefig(out, dpi=120)
    plt.close(fig)
    print("wrote", out)


if __name__ == "__main__":
    tp, cp = load(PRE)
    tq, cq = load(POST)
    print(f"pre : {len(tp)} pts  post: {len(tq)} pts")
    plot_all(tp, cp, tq, cq, os.path.join(HERE, "mbg-d08_simulation_plot.png"))
