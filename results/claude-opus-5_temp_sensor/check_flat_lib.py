"""Verify pdk_flat/sm141064.ngspice against the stock GF180 MOSFET library.

``ts_sim.py`` simulates the MOSFETs from a flattened copy of the PDK model
file, because the stock library re-evaluates roughly a thousand quoted
parameter expressions inside its .model cards on every Newton iteration and a
250 us transient becomes unusable.  A speed-up that changes the answer is
worthless, so this script re-derives the claim rather than asserting it: it
runs the *actual* design on both libraries and compares.

  1. DC operating point of every internal node, at -40 / 27 / 125 C.  This is
     the cheap half and it is the strongest single check: it compares every
     bias node the design depends on.  Always run.
  2. A 5 us transient at each of those temperatures, comparing frequency,
     duty cycle, swing, start-up time and average supply current.  Run with
     ``--tran``; it is slow precisely because the stock library is slow, which
     is the reason the flattened copy exists.

Passives are read from the stock PDK in both cases (only the MOSFET section
is flattened), so this isolates exactly the thing that was changed.

    python3 results/claude-opus-5_temp_sensor/check_flat_lib.py [--tran]
"""
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.environ.get("MBG_ROOT") or os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "src"))
sys.path.insert(0, HERE)

import ts_sim                                                   # noqa: E402
from ts_design import temp_sensor_netlist, CELL                 # noqa: E402

NODES = ["nb1", "nbp", "nrs", "nsu", "ncap", "nst", "npa", "nnb", "nsk"]
TEMPS = (-40, 27, 125)
OP_TOL_V = 1e-4          # absolute volts
TRAN_TOL = 5e-3          # relative


def _op(lib, temp, workdir):
    ts_sim.FLAT_LIB = lib
    deck = ts_sim.build_deck(temp_sensor_netlist(), CELL, temp=temp,
                             stop="1n", step="1p", power_up=False)
    probes = " ".join(f"v(Xdut.{n})" for n in NODES)
    deck = re.sub(r"\.control.*?\.endc",
                  f".control\nop\nprint {probes} i(Vsup)\n.endc",
                  deck, flags=re.S)
    path = os.path.join(workdir, "op.sp")
    with open(path, "w") as f:
        f.write(deck)
    out = subprocess.run(["ngspice", "-b", path], capture_output=True,
                         text=True, cwd=workdir, timeout=900).stdout
    vals = {}
    for m in re.finditer(r"^(\S+)\s*=\s*([-\d.eE+]+)\s*$", out, re.M):
        vals[m.group(1).lower()] = float(m.group(2))
    return vals


def main():
    do_tran = "--tran" in sys.argv
    stock = ts_sim._pdk_file("sm141064.ngspice")
    flat = os.path.join(HERE, "pdk_flat", "sm141064.ngspice")
    if not os.path.isfile(flat):
        raise SystemExit(f"flattened library missing: {flat}")
    worst_op = 0.0
    worst_tran = 0.0
    failures = []

    with tempfile.TemporaryDirectory() as wd:
        for temp in TEMPS:
            a, b = _op(flat, temp, wd), _op(stock, temp, wd)
            keys = sorted(set(a) & set(b))
            if not keys:
                failures.append(f"op {temp}C: no comparable node voltages")
                continue
            for k in keys:
                d = abs(a[k] - b[k])
                worst_op = max(worst_op, d)
                if d > OP_TOL_V:
                    failures.append(f"op {temp}C {k}: {a[k]:.6g} vs {b[k]:.6g}")
            print(f"  op  {temp:>4}C: {len(keys)} quantities, "
                  f"max |delta| = {max(abs(a[k]-b[k]) for k in keys):.3g}")

        net = temp_sensor_netlist()
        for temp in (TEMPS if do_tran else ()):
            row = {}
            for tag, lib in (("flat", flat), ("stock", stock)):
                ts_sim.FLAT_LIB = lib
                row[tag] = ts_sim.simulate_ts_netlist(
                    net, CELL, temp=temp, stop=5e-6,
                    workdir=os.path.join(wd, tag))
            keys = [k for k in row["flat"] if k in row["stock"]]
            worst_k, worst_v = "", 0.0
            for k in keys:
                x, y = row["flat"][k], row["stock"][k]
                scale = max(abs(x), abs(y), 1e-12)
                rel = abs(x - y) / scale
                if rel > worst_v:
                    worst_k, worst_v = k, rel
                if rel > TRAN_TOL:
                    failures.append(f"tran {temp}C {k}: {x:.6g} vs {y:.6g} "
                                    f"({rel*100:.2f}%)")
            worst_tran = max(worst_tran, worst_v)
            print(f"  tran{temp:>4}C: f = {row['flat']['freq_hz']/1e3:.3f} kHz "
                  f"(flat) vs {row['stock']['freq_hz']/1e3:.3f} kHz (stock); "
                  f"worst metric '{worst_k}' {worst_v*100:.3f}%")

    ts_sim.FLAT_LIB = flat
    print(f"\nworst operating-point delta : {worst_op:.3g} V  "
          f"(tolerance {OP_TOL_V} V)")
    if do_tran:
        print(f"worst transient-metric delta: {worst_tran*100:.4f} %  "
              f"(tolerance {TRAN_TOL*100} %)")
    else:
        print("transient comparison: NOT RUN (pass --tran)")
    if failures:
        print("\nFAIL — the flattened library is NOT equivalent:")
        for f in failures[:20]:
            print("  " + f)
        return 1
    print("PASS — flattened and stock MOSFET libraries agree within tolerance.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
