"""Render pvt_summary.json -> pvt_summary.md tables."""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
rows = json.load(open(os.path.join(HERE, "pvt_summary.json")))

CORNERS = ["typical", "ss", "ff", "sf", "fs"]
VDDS = [3.0, 3.3, 3.6]
TEMPS = [-40, 27, 125]


def cell(rows, corner, vdd, temp, key):
    for r in rows:
        if (r["corner"] == corner and r["vdd"] == vdd and r["temp"] == temp
                and r["netlist"] == key):
            m = r["metrics"]
            if not m:
                return r["fail_flags"] or ["NO DATA"]
            f = [x for x in r["fail_flags"]]
            return (f"{m.get('freq_hz', 0)/1e6:.1f}MHz "
                    f"d{m.get('duty_cycle_pct', 0):.1f}%"
                    + (" *" + ",".join(f) if f else ""))
    return "MISSING"


lines = [
    "# PVT Characterization — self-starting ring oscillator (ox-alpha)",
    "",
    "Final design, nominal pre-layout `f=53.8 MHz`; extracted (PEX) "
    "`f=45.3 MHz`. Each cell: frequency, duty cycle; `*FLAG` marks a "
    "specification miss (window: 10-100 MHz, duty 40-60%, VOH>2.97 V, "
    "VOL<0.33 V, Iavg<1 mA, >=100 cycles, startup<5 us).",
    "",
]
for key, title in (("sch", "Pre-layout (schematic) netlist"),
                   ("pex", "Extracted (PEX) netlist")):
    lines += [f"## {title}", "",
              "| corner | " + " | ".join(
                  f"{v} V, {t} °C" for v in VDDS for t in TEMPS) + " |",
              "|" + "---|" * (1 + len(VDDS) * len(TEMPS))]
    for c in CORNERS:
        cells = [cell(rows, c, v, t, key) for v in VDDS for t in TEMPS]
        lines.append(f"| {c} | " + " | ".join(cells) + " |")
    lines.append("")

npex = sum(1 for r in rows if r["netlist"] == "pex" and not r["fail_flags"])
nsch = sum(1 for r in rows if r["netlist"] == "sch" and not r["fail_flags"])
tot = len(VDDS) * len(TEMPS) * len(CORNERS)
freqs = sorted(r["metrics"]["freq_hz"] / 1e6 for r in rows
               if r["netlist"] == "pex" and r["metrics"].get("freq_hz"))
lines += [
    f"**Result:** schematic {nsch}/{tot} points pass all specs; extracted "
    f"{npex}/{tot} points pass.",
    f"PEX frequency range across the full grid: {freqs[0]:.1f} - "
    f"{freqs[-1]:.1f} MHz." if freqs else "",
    "",
    "Simulation model: flattened GF180MCU ngspice parameter library "
    "(value-identical, see pdk_flat/); ideal DC power-up, no stimulus, "
    "no forced initial conditions anywhere.",
]

out = os.path.join(HERE, "pvt_summary.md")
open(out, "w").write("\n".join(lines) + "\n")
print("wrote", out)
