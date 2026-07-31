#!/usr/bin/env python3
"""Run full spice_to_gds_with_checks pipeline for vref_1v2."""
import sys, os, json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".opencode", "tools"))
sys.path.insert(0, "/home/huda/.opencode/tools")

from core.pipeline import spice_to_gds_with_checks

netlist = """
.lib "/home/huda/.volare/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" typical
.subckt vref_1v2 vdd vss vref
* PMOS current mirror (1:1:1)
XM3 d1 d1 vdd vdd pfet_03v3 L=2u W=4u nf=2
XM4 d2 d1 vdd vdd pfet_03v3 L=2u W=4u nf=2
XM5 vref d1 vdd vdd pfet_03v3 L=2u W=4u nf=2

* Beta-multiplier NMOS pair (K:1 = 2:1 via nf=2 vs nf=1)
XM1 d1 d1 vss vss nfet_03v3 L=2u W=4u nf=2
XM2 d2 d1 src2 vss nfet_03v3 L=2u W=4u nf=1

* Triode NMOS resistor (gate=VDD, deep triode)
XM_r src2 vdd vss vss nfet_03v3 L=2u W=4u nf=1

* Output diode-connected NMOS load
XM6 vref vref vss vss nfet_03v3 L=2u W=4u nf=1

.ends
"""

result = spice_to_gds_with_checks(netlist)

print("\n=== PIPELINE RESULT ===")
print(f"outdir:    {result['outdir']}")
print(f"gds_path:  {result['gds_path']}")
print(f"svg_path:  {result['svg_path']}")
print(f"DRC:       {result['drc'].get('summary', '?')}")
print(f"LVS:       {result['lvs'].get('summary', {}).get('message', '?')}")
print(f"PEX:       {result['pex'].get('summary', '?')}")
print(f"all_pass:  {result['all_pass']}")
print("=== DONE ===")

# Save summary
with open(os.path.join(result['outdir'], "pipeline_summary.json"), "w") as f:
    summary = {
        "outdir": result["outdir"],
        "gds_path": result["gds_path"],
        "svg_path": result["svg_path"],
        "drc_summary": result["drc"].get("summary", ""),
        "lvs_summary": str(result["lvs"].get("summary", {})),
        "pex_summary": result["pex"].get("summary", ""),
        "all_pass": result["all_pass"],
    }
    json.dump(summary, f, indent=2, default=str)
