"""Run the full MBG SPICE→GDS pipeline with DRC+LVS+PEX."""
import sys, os, json
sys.path.insert(0, "/home/huda/.opencode/tools")

os.environ.setdefault("PDK_ROOT", "/home/huda/.volare")
os.environ.setdefault("PDK", "gf180mcuD")
os.environ.setdefault("PDKPATH", "/home/huda/.volare/gf180mcuD")

from core.pipeline import spice_to_gds_with_checks

NETLIST = """
.lib "/home/huda/.volare/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" typical
.subckt ota_5t vdd vss inp inm out vb
XM1  net1 inp net2 vss nfet_03v3 L=1u W=4u nf=4
XM2  out  inm net2 vss nfet_03v3 L=1u W=4u nf=4
XM3  net1 net1 vdd vdd pfet_03v3 L=1u W=4u nf=4
XM4  out  net1 vdd vdd pfet_03v3 L=1u W=4u nf=4
XM5  net2 vb  vss vss nfet_03v3 L=1u W=4u nf=4
.ends
"""

os.chdir("/tmp/opencode/mbg_ota_5t")
r = spice_to_gds_with_checks(NETLIST)

print("\n" + "="*80)
print("  SPICE→GDS RESULT SUMMARY")
print("="*80)
print(json.dumps({
    "outdir":     r.get("outdir"),
    "gds_path":   r.get("gds_path"),
    "svg_path":   r.get("svg_path"),
    "cell_name":  r.get("cell_name"),
    "all_pass":   r.get("all_pass"),
}, indent=2, default=str))

# Persist details for the report
import pickle
with open("/tmp/opencode/mbg_ota_5t/_pipe_result.pkl", "wb") as f:
    pickle.dump(r, f)

print("\n-- DRC --")
print(r["drc"].get("summary"))
print(json.dumps({k:v for k,v in r["drc"].items() if k != "log"}, indent=2, default=str))

print("\n-- LVS --")
print(r["lvs"].get("summary"))
print(json.dumps({k:v for k,v in r["lvs"].items() if k != "log"}, indent=2, default=str))

print("\n-- PEX --")
print(r["pex"].get("summary"))
print(json.dumps({k:v for k,v in r["pex"].items() if k != "log"}, indent=2, default=str))

print("\nALL_PASS:", r.get("all_pass"))
