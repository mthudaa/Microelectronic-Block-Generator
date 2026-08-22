"""Run the MBG FULL AUTOMATE flow on a 5T OTA with external Vbias.

Specification (user-provided):
  - 5T OTA, external bias port 'vb'
  - no passive components (no R / no C)
  - DC gain >= 25 dB (only required spec)
  - VDD = 3.3 V, VSS = 0 V, GF180MCU (nfet_03v3 / pfet_03v3)

The same netlist string feeds pre-layout simulation (Testbench strips the
.lib line) and layout generation (the parser needs "GF180" on a .lib line to
detect the PDK). No resistor or capacitor appears anywhere in the circuit.
"""
import os
import sys

os.environ.setdefault("PDK_ROOT", os.path.expanduser("~/.volare"))
os.environ.setdefault("PDK", "gf180mcuD")
os.environ.setdefault("PDKPATH", os.path.expanduser("~/.volare/gf180mcuD"))

from mbg import Spec, make_hooks
from mbg.full_auto import run_full_auto, FullAutoConfig

CELL = "ota_5t"
OUTDIR = os.path.join(os.path.expanduser("~"), "ota_5t_vbias_g25")

lib_path = os.path.join(os.environ["PDKPATH"], "libs.tech", "ngspice",
                        "sm141064.ngspice")

NETLIST = f"""
.lib "{lib_path}" typical
.subckt {CELL} vdd vss inp inm out vb
XM1  net1 inp net2 vss nfet_03v3 L=1u W=4u nf=4
XM2  out  inm net2 vss nfet_03v3 L=1u W=4u nf=4
XM3  net1 net1 vdd vdd pfet_03v3 L=1u W=4u nf=4
XM4  out  net1 vdd vdd pfet_03v3 L=1u W=4u nf=4
XM5  net2 vb  vss vss nfet_03v3 L=1u W=4u nf=4
.ends
""".strip()

SPECS = [Spec("gain_db", ">=", 25.0, " dB")]

REQUEST = (
    "Design a 5T OTA (NMOS differential pair, PMOS current-mirror load, "
    "NMOS tail current source) with an external bias port 'vb'. "
    "No passive components: no resistors, no capacitors. "
    "VDD=3.3 V, VSS=0 V, GF180MCU. DC gain >= 25 dB. "
    "No other performance target is required."
)

# Input common-mode must sit mid-rail for the NMOS diff pair to conduct;
# 'vb' biases the tail current source. 'inp' carries the AC stimulus.
BIAS = {"vb": "DC 0.9", "inm": "DC 1.65", "inp": "DC 1.65"}

hooks = make_hooks(
    cell=CELL, in_node="inp", out_node="out",
    supplies={"vdd": 3.3, "vss": 0.0},
    bias=BIAS,
    spec_names=[s.name for s in SPECS],
    specs=SPECS,
    outdir=OUTDIR,
    verbosity=1,
)

config = FullAutoConfig.for_effort("normal", outdir=OUTDIR)

res = run_full_auto(REQUEST, hooks, cell=CELL, specs=SPECS,
                    netlist=NETLIST, config=config)

print("\n" + "=" * 80)
if hasattr(res, "summary"):
    print(res.summary())
print("STATUS:", res.status)
print("TAPEOUT_READY:", res.tapeout_ready)
print("Report:", res.report_path)
sys.exit(0 if res.tapeout_ready else 1)
