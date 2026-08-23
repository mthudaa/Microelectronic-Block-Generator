import sys
import os
import json

sys.path.insert(0, "/home/huda/opensource-project/Microelectronic-Block-Generator/src")
sys.path.insert(0, "/home/huda/opensource-project/Microelectronic-Block-Generator/results/deepseek_strongarm_comparator")

import sa_measure as M
import run_strongarm as R

OUT = R.OUTDIR
netlist = R.NETLIST
wd = os.path.join(OUT, "sim", "char_dt")
m = M.measure_comparator(netlist, workdir=wd, timeout=900, icmr_step=0.1)
cases = m.pop("_cases", [])
table = [{"vd_mv": c["vd"] * 1e3,
          "t_dec_ns": (c["t_dec"] * 1e9) if c["t_dec"] is not None else None,
          "diff_settled_v": c["diff_settled"],
          "correct": c["correct"], "precharge_lo_v": c["precharge_lo"]}
         for c in cases]
nominal = {k: v for k, v in m.items() if not k.startswith("_")}

path = os.path.join(OUT, "characterization.json")
d = json.load(open(path))
d["decision_time_table"] = table
d["nominal"] = nominal
json.dump(d, open(path, "w"), indent=2, default=str)

# worst-case decision time per |VIN_DIFF| over both polarities
by = {}
for c in table:
    by.setdefault(abs(c["vd_mv"]), []).append(c["t_dec_ns"])
lines = ["", "### Decision time vs |VIN_DIFF| (nominal, worst of both polarities)",
         ""]
lines.append("| |VIN_DIFF| (mV) | t_dec worst (ns) | decisions |")
lines.append("|---|---|---|")
for vd in sorted(by):
    vals = [x for x in by[vd] if x is not None]
    ok = all(c["correct"] for c in table if abs(c["vd_mv"]) == vd)
    lines.append(f"| {int(vd)} | {max(vals):.3f} | "
                 f"{'10/10 correct' if ok else 'MISMATCH'} |")
lines.append("")
report = os.path.join(OUT, "final_design_report.md")
with open(report, "a") as f:
    f.write("\n".join(lines))
print("decision-time table entries:", len(table))
for vd in sorted(by):
    print(f"  |VD|={int(vd):3d} mV: worst t_dec = {max(by[vd]):.3f} ns")
print("nominal t_dec_ns:", nominal["t_dec_ns"])
