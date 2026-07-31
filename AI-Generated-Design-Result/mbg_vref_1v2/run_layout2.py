#!/usr/bin/env python3
"""Retry layout with modified netlist to avoid gate-drain self-loop routing."""
import sys, os, json

sys.path.insert(0, "/home/huda/.opencode/tools")
from core.pipeline import spice_to_gds_with_checks

# Modified netlist: use separate gate node for diode NMOS and short it via a routing net
# The key change: Instead of XM1(d1,d1,vss,vss), we use XM1(d1, d1, vss, vss)
# which should route d1 net to both drain and gate.
# But the router already failed at this...
# 
# Alternative: use a symmetrical topology where PMOS and NMOS both use diode mirror
# and we avoid NMOS diode-connected devices entirely.

netlist = """
.lib "/home/huda/.volare/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" typical
.subckt vref_1v2 vdd vss vref
* PMOS current mirror (1:1:1:1)
XM3 d1 d1 vdd vdd pfet_03v3 L=2u W=4u nf=1
XM4 d2 d1 vdd vdd pfet_03v3 L=2u W=4u nf=1
XM5 vref d1 vdd vdd pfet_03v3 L=2u W=4u nf=1

* Beta-multiplier NMOS pair (K:1 = 2:1 via W ratio)
XM1 d1 d1 vss vss nfet_03v3 L=2u W=4u nf=1
XM2 d2 d1 src2 vss nfet_03v3 L=2u W=4u nf=2

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
drc_summary = result['drc'].get('summary', '?')
lvs_summary = result['lvs'].get('summary', {}).get('message', '?')
pex_summary = result['pex'].get('summary', '?')
print(f"DRC:       {drc_summary}")
print(f"LVS:       {lvs_summary}")
print(f"PEX:       {pex_summary}")
print(f"all_pass:  {result['all_pass']}")

# Save summary
with open(os.path.join(result['outdir'], "pipeline_summary.json"), "w") as f:
    json.dump({
        "outdir": result["outdir"],
        "gds_path": result["gds_path"],
        "svg_path": result["svg_path"],
        "drc_summary": str(drc_summary),
        "lvs_summary": str(lvs_summary),
        "pex_summary": str(pex_summary),
        "all_pass": result["all_pass"],
    }, f, indent=2, default=str)
