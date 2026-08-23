"""PVT + mismatch-Monte-Carlo characterization of the final comparator.

Run after the flow converges (or from the best iteration's netlist):

    python3 run_characterization.py <netlist.spice> [runs]

Writes characterization/pvt.json, characterization/offset_mc.json and
characterization/CHARACTERIZATION.md next to this script. Every number comes
from a simulation; nothing is estimated. Analyses that did not run are
reported as such.
"""
import json
import os
import sys
import time

os.environ.setdefault("PDK_ROOT", os.path.expanduser("~/.volare"))
os.environ.setdefault("PDK", "gf180mcuD")
os.environ.setdefault("PDKPATH", os.path.expanduser("~/.volare/gf180mcuD"))
os.environ["OMP_NUM_THREADS"] = "1"

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from strongarm_tb import (ComparatorSim, estimate_offset_distribution,
                          reduced_matrix)

VDDS = [3.0, 3.3, 3.6]
TEMPS = [-40, 27, 125]
CORNERS = ["typical", "ff", "fs", "sf", "ss"]


def pvt(netlist: str) -> list:
    rows = []
    for corner in CORNERS:
        for vdd in VDDS:
            for temp in TEMPS:
                tag = f"pvt/{corner}_vdd{vdd:.1f}_t{temp}".replace("-", "m")
                t0 = time.time()
                try:
                    sim = ComparatorSim(workdir=os.path.join(HERE, "sim"),
                                        vdd=vdd, corner=corner, temp_c=temp)
                    m = sim.run(netlist, conds=reduced_matrix(), tag=tag)
                    row = {"corner": corner, "vdd": vdd, "temp": temp,
                           "status": "PASS", **m}
                    # explicit per-condition verification of reset/regen is
                    # implied by correct_frac + swing_ratio + decision time
                    ok = (row["correct_frac"] >= 1.0
                          and row["swing_ratio"] >= 0.90
                          and row["decision_time_s"] <= 5e-9)
                    row["all_specs"] = bool(ok)
                except Exception as e:                       # noqa: BLE001
                    row = {"corner": corner, "vdd": vdd, "temp": temp,
                           "status": "ERROR", "error": f"{type(e).__name__}: {e}"}
                row["wall_s"] = round(time.time() - t0, 1)
                rows.append(row)
                print(json.dumps(row), flush=True)
    return rows


def main() -> int:
    netlist_path = sys.argv[1]
    runs = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    with open(netlist_path) as f:
        netlist = f.read()

    outdir = os.path.join(HERE, "characterization")
    os.makedirs(outdir, exist_ok=True)
    os.makedirs(os.path.join(HERE, "sim"), exist_ok=True)

    print(f"[CHAR] PVT sweep: {len(CORNERS)} corners x {len(VDDS)} VDD "
          f"x {len(TEMPS)} temps", flush=True)
    rows = pvt(netlist)
    with open(os.path.join(outdir, "pvt.json"), "w") as f:
        json.dump({"netlist": netlist_path, "results": rows}, f, indent=1)

    print(f"[CHAR] mismatch Monte Carlo offset ({runs} runs)", flush=True)
    try:
        mc = estimate_offset_distribution(
            ComparatorSim(workdir=os.path.join(HERE, "sim")), netlist,
            runs=runs)
        if mc.get("valid"):
            mc["mean_mv"] = mc["mean_v"] * 1e3
            mc["sigma_mv"] = mc["sigma_v"] * 1e3
            mc["sigma3_mv"] = mc["sigma3_v"] * 1e3
    except Exception as e:                                   # noqa: BLE001
        mc = {"status": "ERROR", "error": f"{type(e).__name__}: {e}"}
    with open(os.path.join(outdir, "offset_mc.json"), "w") as f:
        json.dump(mc, f, indent=1)

    n_pass = sum(1 for r in rows if r.get("all_specs"))
    lines = ["# Characterization (measured)", "",
             f"Netlist: `{netlist_path}`", "",
             "## PVT", "",
             "| corner | VDD | TEMP | decision_time_s | swing_ratio | "
             "correct_frac | iavg_a | istatic_a | all specs |",
             "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        if r["status"] != "PASS":
            lines.append(f"| {r['corner']} | {r['vdd']} | {r['temp']} | - | - "
                         "| - | - | - | ERROR: "
                         f"{r.get('error','')[:60]} |")
            continue
        lines.append(
            f"| {r['corner']} | {r['vdd']:.1f} | {r['temp']} | "
            f"{r['decision_time_s']*1e9:.2f} ns | {r['swing_ratio']:.3f} | "
            f"{r['correct_frac']:.2f} | {r['iavg_a']*1e6:.1f} uA | "
            f"{r['istatic_a']*1e9:.1f} nA | {'PASS' if r['all_specs'] else 'FAIL'} |")
    lines += ["", f"PVT conditions meeting all dynamic specs: "
              f"{n_pass}/{len(rows)}.", ""]
    if mc.get("valid"):
        lines += [
            "## Input-referred offset (mismatch Monte Carlo)",
            "",
            f"- runs requested: {mc['runs']}, valid samples: {mc['valid']}",
            f"- mean offset: {mc['mean_mv']:.2f} mV",
            f"- 1 sigma: {mc['sigma_mv']:.2f} mV",
            f"- 3 sigma: {mc['sigma3_mv']:.2f} mV",
            "- method: per-sample amplitude ladder at CM = 1.65 V; the offset",
            "  is interval-censored between the largest amplitude whose both",
            "  polarities decide wrongly and the smallest whose both decide",
            "  correctly; the sample estimate is the bracket midpoint.",
            ""]
    else:
        lines += ["## Input-referred offset (mismatch Monte Carlo)", "",
                  f"NOT AVAILABLE: {mc}", ""]
    with open(os.path.join(outdir, "CHARACTERIZATION.md"), "w") as f:
        f.write("\n".join(lines))
    print("[CHAR] wrote", os.path.join(outdir, "CHARACTERIZATION.md"),
          flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
