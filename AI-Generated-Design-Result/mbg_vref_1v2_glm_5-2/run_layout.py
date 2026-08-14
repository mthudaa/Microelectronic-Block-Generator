#!/usr/bin/env python3
"""Run full spice_to_gds_with_checks for vref_1v2 with PDK env set."""
import sys, os, json

os.environ["PDK_ROOT"] = "/home/huda/.volare"
os.environ["PDK"] = "gf180mcuD"
os.environ["PDKPATH"] = "/home/huda/.volare/gf180mcuD"

sys.path.insert(0, "/home/huda/.opencode/tools")
from core.pipeline import spice_to_gds_with_checks

with open("vref_1v2.spice") as f:
    subckt = f.read()

# Pipeline parses PDK from a .lib/.inc line; prepend the GF180MCU model lib
# so auto-detection picks 'gf180' and LVS has the models.
netlist = '.lib "/home/huda/.volare/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" typical\n' + subckt

result = spice_to_gds_with_checks(netlist)

print("\n=== PIPELINE RESULT ===")
print(f"outdir:    {result['outdir']}")
print(f"gds_path:  {result['gds_path']}")
print(f"svg_path:  {result.get('svg_path')}")
drc = result.get("drc", {})
lvs = result.get("lvs", {})
pex = result.get("pex", {})
drc_s = drc.get("summary", "?")
lvs_s = (lvs.get("summary", {}) or {}).get("message", "?")
pex_s = pex.get("summary", "?")
print(f"DRC:       {drc_s}  (clean={drc.get('clean')}, errs={drc.get('error_count','?')})")
print(f"LVS:       {lvs_s}  (match={lvs.get('match')})")
print(f"PEX:       {pex_s}  (pex_path={pex.get('pex_path')})")
print(f"all_pass:  {result.get('all_pass')}")

with open("pipeline_summary.json", "w") as f:
    json.dump({
        "outdir": result["outdir"],
        "gds_path": result["gds_path"],
        "svg_path": result.get("svg_path"),
        "cell_name": result.get("cell_name"),
        "drc_summary": str(drc_s),
        "drc_clean": drc.get("clean"),
        "drc_error_count": drc.get("error_count"),
        "lvs_match": lvs.get("match"),
        "lvs_summary": str(lvs.get("summary", {})),
        "pex_summary": str(pex_s),
        "pex_path": pex.get("pex_path"),
        "all_pass": result.get("all_pass"),
    }, f, indent=2, default=str)
print("Saved pipeline_summary.json")
