"""Turn pvt_summary.json into the report tables.

Emits pvt_summary.md:
  * the F(T) curve — frequency at every characterised temperature point, for
    every corner and every supply, for both the schematic and the extracted
    netlist;
  * per (netlist, corner, VDD): monotonicity over -40..125 C and two
    temperature sensitivities;
  * the worst-case table for every other acceptance limit.

Two sensitivity numbers are reported because they answer different questions:

  TC_mean  = ln(f(125) / f(-40)) / 165 C
             the average fractional slope across the whole characterised span
  TC_27    = (f(50) - f(10)) / (f(27) * 40 C)
             the local slope at the nominal point, i.e. what a single-point
             uncalibrated reading actually resolves

Neither is a fit residual; this design is deliberately uncalibrated, so no
polynomial is subtracted before quoting them.
"""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "pvt_summary.json")
DST = os.path.join(HERE, "pvt_summary.md")

TEMPS = [-40, -15, 10, 27, 50, 75, 100, 125]
CORNERS = ["typical", "ss", "ff", "sf", "fs"]
VDDS = [3.0, 3.3, 3.6]


def load():
    rows = json.load(open(SRC))
    idx = {}
    for r in rows:
        idx[(r["netlist"], r["corner"], r["vdd"], r["temp"])] = r
    return rows, idx


def f_of(idx, net, corner, vdd, t):
    r = idx.get((net, corner, vdd, t))
    if not r:
        return None
    return (r["metrics"] or {}).get("freq_hz") or None


def tc_numbers(fs):
    """fs: dict temp -> freq.  Returns (mono, tc_mean, tc_27) or Nones."""
    have = [fs.get(t) for t in TEMPS]
    if any(v is None or v <= 0 for v in have):
        return None, None, None
    rising = all(b > a for a, b in zip(have, have[1:]))
    falling = all(b < a for a, b in zip(have, have[1:]))
    mono = "rising" if rising else ("falling" if falling else "NO")
    tc_mean = (math.log(fs[125]) - math.log(fs[-40])) / (125 - (-40)) * 1e6
    tc_27 = (fs[50] - fs[10]) / (fs[27] * 40.0) * 1e6
    return mono, tc_mean, tc_27


def main():
    if not os.path.exists(SRC):
        raise SystemExit(f"no PVT data yet: {SRC}")
    rows, idx = load()
    nets = [n for n in ("pex", "sch") if any(r["netlist"] == n for r in rows)]
    out = []
    w = out.append

    w("# PVT characterisation — temp_sensor\n")
    total = len(rows)
    done = {n: sum(1 for r in rows if r["netlist"] == n) for n in nets}
    w(f"{total} simulated operating points "
      + ", ".join(f"{n}: {c}" for n, c in done.items()) + ".\n")
    w("Every point is an independent transient from a 0 V power-up ramp with "
      "`uic`; no point reuses another point's state, and none uses a forced "
      "initial condition.\n")

    # ── F(T) curves ───────────────────────────────────────────────────
    for net in nets:
        label = "extracted (PEX)" if net == "pex" else "schematic (pre-layout)"
        w(f"\n## F(T) curve — {label}\n")
        w("Frequency in kHz at every characterised temperature point.\n")
        for vdd in VDDS:
            w(f"\n**VDD = {vdd:.1f} V**\n")
            w("| corner | " + " | ".join(f"{t} C" for t in TEMPS)
              + " | monotonic | TC_mean ppm/C | TC_27 ppm/C |")
            w("|---|" + "---:|" * len(TEMPS) + "---|---:|---:|")
            for c in CORNERS:
                fs = {t: f_of(idx, net, c, vdd, t) for t in TEMPS}
                cells = [("—" if fs[t] is None else f"{fs[t]/1e3:.1f}")
                         for t in TEMPS]
                mono, tcm, tc27 = tc_numbers(fs)
                w(f"| {c} | " + " | ".join(cells) + " | "
                  + (mono or "—") + " | "
                  + (f"{tcm:+.0f}" if tcm is not None else "—") + " | "
                  + (f"{tc27:+.0f}" if tc27 is not None else "—") + " |")

    # ── sensitivity summary per VDD ───────────────────────────────────
    w("\n## Monotonicity and sensitivity, per supply\n")
    w("| netlist | VDD | corners monotonic | TC_mean min | TC_mean max "
      "| TC_27 min | TC_27 max |")
    w("|---|---:|---|---:|---:|---:|---:|")
    for net in nets:
        for vdd in VDDS:
            monos, tcms, tc27s = [], [], []
            for c in CORNERS:
                fs = {t: f_of(idx, net, c, vdd, t) for t in TEMPS}
                mono, tcm, tc27 = tc_numbers(fs)
                if mono is None:
                    continue
                monos.append(mono)
                tcms.append(tcm)
                tc27s.append(tc27)
            if not tcms:
                continue
            nmono = sum(1 for m in monos if m in ("rising", "falling"))
            w(f"| {net} | {vdd:.1f} | {nmono}/{len(monos)} | "
              f"{min(tcms):+.0f} | {max(tcms):+.0f} | "
              f"{min(tc27s):+.0f} | {max(tc27s):+.0f} |")

    # ── worst case of every other limit ───────────────────────────────
    w("\n## Worst case across the whole grid\n")
    w("| netlist | metric | worst value | limit | verdict |")
    w("|---|---|---:|---:|---|")
    checks = [
        ("volt_high_v", "TEMP_OUT high (min)", min, 2.97, ">=", "V", 1.0),
        ("volt_low_v", "TEMP_OUT low (max)", max, 0.33, "<=", "V", 1.0),
        ("duty_cycle_pct", "duty cycle (min)", min, 40.0, ">=", "%", 1.0),
        ("duty_cycle_pct", "duty cycle (max)", max, 60.0, "<=", "%", 1.0),
        ("i_avg_a", "avg supply current (max)", max, 200.0, "<=", "uA", 1e6),
        ("cycles_sustained", "sustained cycles (min)", min, 100.0, ">=", "", 1.0),
        ("startup_time_s", "start-up time (max)", max, 10.0, "<=", "us", 1e6),
    ]
    for net in nets:
        for key, label, how, limit, op, unit, mul in checks:
            vals = [(r["metrics"] or {}).get(key) for r in rows
                    if r["netlist"] == net]
            vals = [v * mul for v in vals if v is not None]
            if not vals:
                continue
            v = how(vals)
            ok = (v >= limit) if op == ">=" else (v <= limit)
            w(f"| {net} | {label} | {v:.4g} {unit} | {op} {limit:g} {unit} "
              f"| {'PASS' if ok else 'FAIL'} |")

    # ── failures ──────────────────────────────────────────────────────
    bad = [r for r in rows if r["fail_flags"]]
    w("\n## Points failing any per-corner limit\n")
    if not bad:
        w(f"None — all {len(rows)} simulated points meet every limit.\n")
    else:
        w("| netlist | corner | VDD | temp | flags | f (kHz) |")
        w("|---|---|---:|---:|---|---:|")
        for r in bad:
            f = (r["metrics"] or {}).get("freq_hz")
            w(f"| {r['netlist']} | {r['corner']} | {r['vdd']:.1f} | "
              f"{r['temp']} | {','.join(r['fail_flags'])} | "
              + (f"{f/1e3:.1f}" if f else "—") + " |")

    text = "\n".join(out) + "\n"
    with open(DST, "w") as fh:
        fh.write(text)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
