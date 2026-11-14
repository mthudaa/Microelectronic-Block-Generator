#!/usr/bin/env python3
"""Regenerate the MBG-D08 top-level simulation plots.

Reads the ngspice `wrdata` outputs produced by mbg-d08_pre_tb.spice and
mbg-d08_post_tb.spice and writes:

    mbg-d08_simulation_plot.png    all ten outputs + differential input
    temp_sensor_simulation_plot.png  temperature-sensor detail + frequency

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


def load(path):
    """ngspice wrdata writes (time, value) column pairs per vector."""
    d = np.loadtxt(path)
    t = d[:, 0]
    return t, {n: d[:, 2 * i + 1] for i, n in enumerate(SIGNALS)}


def osc_stats(t, v, thresh=1.65):
    """Rising-edge count and median period of an oscillating node."""
    hi = v > thresh
    rises = np.flatnonzero((~hi[:-1]) & hi[1:])
    if len(rises) < 2:
        return 0, np.nan, np.nan
    periods = np.diff(t[rises])
    med = float(np.median(periods))
    return len(rises), med, (1.0 / med if med > 0 else np.nan)


def plot_all(tp, cp, tq, cq, out):
    fig, axes = plt.subplots(4, 3, figsize=(20, 16.25))
    fig.suptitle("MBG-D08 pre-layout vs post-layout transient "
                 "(100 µs, CLK = 10 µs, 27 °C)", fontsize=17)
    for k, name in enumerate(SIGNALS):
        ax = axes[k // 3][k % 3]
        ax.plot(tp * 1e6, cp[name] * (1e3 if name == "vdiff" else 1),
                color=C_PRE, lw=0.8, label="pre")
        ax.plot(tq * 1e6, cq[name] * (1e3 if name == "vdiff" else 1),
                color=C_POST, lw=0.8, label="post PEX")
        ax.set_title("INP-INN" if name == "vdiff" else name, fontsize=14)
        ax.set_ylabel("mV" if name == "vdiff" else "V")
        ax.grid(alpha=0.3)
        if k == 0:
            ax.legend(loc="upper left", fontsize=10)
        if k // 3 == 3:
            ax.set_xlabel("Time (µs)")
    axes[3][2].axis("off")
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    fig.savefig(out, dpi=120)
    plt.close(fig)
    print("wrote", out)


def plot_temp(tp, cp, tq, cq, out, zoom_us=10.0):
    fig = plt.figure(figsize=(16, 9))
    gs = fig.add_gridspec(2, 1, height_ratios=[3, 1], hspace=0.25)
    ax = fig.add_subplot(gs[0])
    for t, c, col, lab in ((tp, cp, C_PRE, "Pre-layout"),
                           (tq, cq, C_POST, "Post-layout PEX")):
        m = (t * 1e6) <= zoom_us
        ax.plot(t[m] * 1e6, c["temp_out"][m], color=col, lw=1.4, label=lab)
    ax.set_title("Claude Opus 5 relaxation-oscillator temperature sensor, "
                 "27 °C", fontsize=16)
    ax.set_ylabel("TEMP_OUT (V)")
    ax.set_xlim(0, zoom_us)
    ax.grid(alpha=0.3)
    ax.legend(loc="upper right")

    axb = fig.add_subplot(gs[1])
    stats = [osc_stats(tp, cp["temp_out"]), osc_stats(tq, cq["temp_out"])]
    labels = ["Pre-layout", "Post-layout PEX"]
    for i, ((n, per, f), col) in enumerate(zip(stats, (C_PRE, C_POST))):
        axb.bar(i, f / 1e6, width=0.5, color=col)
        axb.text(i, f / 1e6 * 1.02,
                 f"{f/1e6:.3f} MHz\n{n} rises, {per*1e9:.1f} ns",
                 ha="center", va="bottom", fontsize=11)
    axb.set_xticks([0, 1])
    axb.set_xticklabels(labels)
    axb.set_ylabel("Frequency (MHz)")
    axb.set_ylim(0, max(s[2] for s in stats) / 1e6 * 1.35)
    axb.grid(alpha=0.3, axis="y")
    fig.savefig(out, dpi=120, bbox_inches="tight")
    plt.close(fig)
    print("wrote", out)
    return stats


if __name__ == "__main__":
    tp, cp = load(PRE)
    tq, cq = load(POST)
    print(f"pre : {len(tp)} pts  post: {len(tq)} pts")
    plot_all(tp, cp, tq, cq, os.path.join(HERE, "mbg-d08_simulation_plot.png"))
    st = plot_temp(tp, cp, tq, cq,
                   os.path.join(HERE, "temp_sensor_simulation_plot.png"))
    for lab, (n, per, f) in zip(("pre", "post"), st):
        print(f"  temp_out {lab:4s}: {n} rises, median {per*1e9:.1f} ns, {f/1e6:.4f} MHz")
