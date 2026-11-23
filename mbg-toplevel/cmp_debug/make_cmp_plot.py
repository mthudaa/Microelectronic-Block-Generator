#!/usr/bin/env python3
"""Regenerate cmp_io_simulation_plot.png from the *_cmp_io_tr.dat files written by *_cmp_io_tb.spice.

Run the three benches with ngspice first (edit the PDK .include/.lib paths at the top of each bench):
    ngspice -b gpt62sol_cmp_io_tb.spice   (and opus55_..., gemini4argon_...)
"""
import os

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
MODELS = [("gemini4argon", "Gemini 4 Argon (neon fallback)"), ("gpt62sol", "GPT-6.2 Sol"), ("opus55", "Opus 5.5")]

fig, axes = plt.subplots(3, 2, figsize=(20, 14.3), sharex=True, sharey=True)
fig.suptitle("Standalone comparator + io_secondary_3p3 diagnostic\n"
             "100 µs transient, CLK period 10 µs (5 µs high), complementary ±200 mV input ramp", fontsize=16, y=0.97)
for r, (mid, label) in enumerate(MODELS):
    d = np.loadtxt(os.path.join(HERE, f"{mid}_cmp_io_tr.dat"))
    t = d[:, 0] * 1e6
    outp_pad, outn_pad, outp_core, outn_core, vdiff, clk = [d[:, 2 * i + 1] for i in range(6)]
    cross = t[np.argmin(np.abs(vdiff))]
    for c, (core, pad, name) in enumerate(((outp_core, outp_pad, "OUTP"), (outn_core, outn_pad, "OUTN"))):
        ax = axes[r][c]
        ax.plot(t, core, color="#1f77b4", lw=1.2, label="core")
        ax.plot(t, pad, color="red", lw=1.0, ls="--", label="pad via io_secondary_3p3")
        ax.axvline(cross, color="#2ca02c", ls=":", lw=1)
        ax.set_title(f"{label}: {name}", fontsize=13)
        ax.grid(alpha=0.3)
        if c == 0:
            ax.set_ylabel("Voltage (V)")
        if r == 2:
            ax.set_xlabel("Time (µs)")
        if r == 0 and c == 0:
            ax.legend(loc="lower right", fontsize=9)
        if c == 1:
            ax.text(0.98, 0.03, "green: Vdiff = 0", transform=ax.transAxes, ha="right", color="#2ca02c", fontsize=9)
fig.text(0.5, 0.03, "Input ramp: INP −200 mV → +200 mV, INN +200 mV → −200 mV", ha="center", fontsize=11)
out = os.path.join(HERE, "cmp_io_simulation_plot.png")
fig.savefig(out, dpi=112, bbox_inches="tight")
print("wrote", out)
