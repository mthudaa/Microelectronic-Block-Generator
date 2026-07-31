#!/usr/bin/env python3
"""Run DRC/LVS/PEX checks manually with correct env."""
import sys, os

sys.path.insert(0, "/home/huda/.opencode/tools")
from core.checks import run_drc, run_lvs, run_pex

os.environ["PDK_ROOT"] = "/home/huda/.volare"
os.environ["PDK"] = "gf180mcuD"
os.environ["PDKPATH"] = "/home/huda/.volare/gf180mcuD"

gds_path = "/home/huda/mbg_vref_1v2/vref_1v2/vref_1v2.gds"
outdir = "/home/huda/mbg_vref_1v2/vref_1v2"
cell_name = "vref_1v2"

netlist = """.lib "/home/huda/.volare/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" typical
.subckt vref_1v2 vdd vss vref
XM3 d1 d1 vdd vdd pfet_03v3 L=2u W=4u nf=2
XM4 d2 d1 vdd vdd pfet_03v3 L=2u W=4u nf=2
XM5 vref d1 vdd vdd pfet_03v3 L=2u W=4u nf=2
XM1 d1 d1 vss vss nfet_03v3 L=2u W=4u nf=2
XM2 d2 d1 src2 vss nfet_03v3 L=2u W=4u nf=1
XM_r src2 vdd vss vss nfet_03v3 L=2u W=4u nf=1
XM6 vref vref vss vss nfet_03v3 L=2u W=4u nf=1
.ends
"""

print("=== DRC ===")
drc = run_drc(gds_path, cell_name=cell_name, workdir=outdir)
print(f"DRC: {drc['summary']}")
print(f"Errors: {drc.get('error_count', '?')}")
n = (drc.get('log', '') or '')[-2000:]
print(n if n else "(no log)")

print()
print("=== LVS ===")
lvs = run_lvs(gds_path, netlist_content=netlist, cell_name=cell_name, workdir=outdir)
summary = lvs.get("summary", {})
print(f"LVS: {summary.get('message', '?')}")
if not lvs.get("match"):
    print(f"Device mismatch: {summary.get('device_mismatch', '?')}")
    print(f"Net mismatch: {summary.get('net_mismatch', '?')}")
    print(f"Port swaps: {summary.get('port_swaps', '?')}")
    print(f"Missing devs: {summary.get('missing_devices', '?')}")
n = (lvs.get('log', '') or '')[-2000:]
print(n if n else "(no log)")

print()
print("=== PEX ===")
pex = run_pex(gds_path, cell_name=cell_name, mode=2, workdir=outdir)
print(f"PEX: {pex['summary']}")
if pex.get("pex_path"):
    print(f"PEX file: {pex['pex_path']}")

all_pass = drc.get("clean") and lvs.get("match") and pex.get("pex_path") is not None
print(f"\nAll pass: {all_pass}")

# Save final results
import json
with open(os.path.join(outdir, "checks_result.json"), "w") as f:
    json.dump({
        "drc_summary": drc.get("summary", ""),
        "drc_clean": drc.get("clean", False),
        "drc_errors": drc.get("error_count", -1),
        "lvs_match": lvs.get("match", False),
        "lvs_summary": str(lvs.get("summary", {})),
        "pex_path": pex.get("pex_path", ""),
        "pex_summary": pex.get("summary", ""),
        "all_pass": all_pass,
    }, f, indent=2, default=str)
