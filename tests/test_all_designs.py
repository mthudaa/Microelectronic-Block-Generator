#!/usr/bin/env python3
"""End-to-end regression over the reference analog blocks.

Drives the public pipeline entry point, spice_to_gds_with_checks(), and
reports DRC / LVS for each design.

Run:  python tests/test_all_designs.py
      python tests/test_all_designs.py --only 5T-OTA
"""

import os
import sys
import time


def _repo_src():
    """Walk up from this file until the src/mbg package is found."""
    d = os.path.dirname(os.path.abspath(__file__))
    for _ in range(8):
        cand = os.path.join(d, "src")
        if os.path.isdir(os.path.join(cand, "mbg")):
            return cand
        d = os.path.dirname(d)
    raise RuntimeError("could not locate src/mbg from " + __file__)


sys.path.insert(0, _repo_src())

os.environ['PDK_ROOT'] = os.environ.get('PDK_ROOT', os.path.expanduser('~/.volare'))
os.environ['PDK'] = os.environ.get('PDK', 'gf180mcuD')
pdkpath = f"{os.environ['PDK_ROOT']}/{os.environ['PDK']}"
os.environ['PDKPATH'] = os.environ.get('PDKPATH', pdkpath)
os.environ['STD_CELL_LIBRARY'] = os.environ.get('STD_CELL_LIBRARY', 'gf180mcu_fd_sc_mcu7t5v0')

from mbg.pipeline import spice_to_gds_with_checks

PDK_LIB = os.path.join(os.environ['PDKPATH'], 'libs.tech', 'ngspice', 'sm141064.ngspice')

DESIGNS = {
    "Inverter": """
.lib "{PDK_LIB}" typical
.subckt inverter vdd vss in out
XM1p out in vdd vdd pfet_03v3 L=1u W=4u nf=1
XM1n out in vss vss nfet_03v3 L=1u W=2u nf=1
.ends
""",
    "3-stage Ring Oscillator": """
.lib "{PDK_LIB}" typical
.subckt ring_osc_3 vdd vss out
XM1p n1 out vdd vdd pfet_03v3 L=1u W=4u nf=1
XM1n n1 out vss vss nfet_03v3 L=1u W=2u nf=1
XM2p n2 n1 vdd vdd pfet_03v3 L=1u W=4u nf=1
XM2n n2 n1 vss vss nfet_03v3 L=1u W=2u nf=1
XM3p out n2 vdd vdd pfet_03v3 L=1u W=4u nf=1
XM3n out n2 vss vss nfet_03v3 L=1u W=2u nf=1
.ends
""",
    "5T-OTA": """
.lib "{PDK_LIB}" typical
.subckt ota_5t vdd vss inn inp out
XM1 tail inn out1 vss nfet_03v3 L=1u W=2u nf=1
XM2 out inp tail vss nfet_03v3 L=1u W=2u nf=1
XM3 out1 out1 vdd vdd pfet_03v3 L=1u W=4u nf=1
XM4 out out1 vdd vdd pfet_03v3 L=1u W=4u nf=1
XM5 tail bias vss vss nfet_03v3 L=1u W=2u nf=1
.ends
""",
    # Body-biased OTA: XM1's bulk sits on vbb rather than vss, so it can only
    # be built with a deep n-well. Isolation propagates to XM2 to keep the
    # differential pair matched.
    "DNW Body-Biased OTA": """
.lib "{PDK_LIB}" typical
.subckt ota_bb vdd vss inp inm out vb vbb
XM1  net1 inp net2 vbb nfet_03v3 L=1u W=4u nf=4
XM2  out  inm net2 vss nfet_03v3 L=1u W=4u nf=4
XM3  net1 net1 vdd vdd pfet_03v3 L=1u W=4u nf=4
XM4  out  net1 vdd vdd pfet_03v3 L=1u W=4u nf=4
XM5  net2 vb  vss vss nfet_03v3 L=1u W=4u nf=4
.ends
""",
    # Beta-multiplier voltage reference: dominated by diode-connected devices
    # (gate and drain on the same net). The archived run logged exactly that
    # topology as failing to connect in the layout.
    "VREF Beta-Multiplier": """
.lib "{PDK_LIB}" typical
.subckt vref_1v2 vdd vss vref
XM3  d1   d1   vdd  vdd  pfet_03v3 L=1.25u W=4u nf=1
XM4  d2   d1   vdd  vdd  pfet_03v3 L=1.25u W=4u nf=1
XM5  vref d1   vdd  vdd  pfet_03v3 L=1.25u W=4u nf=1
XM1  d1   d1   vss  vss  nfet_03v3 L=1.25u W=4u nf=1
XM2  d2   d1   src2 vss  nfet_03v3 L=1.25u W=4u nf=1
XM_r src2 vdd  vss  vss  nfet_03v3 L=1.25u W=4u nf=1
XM6  vref vref vss  vss  nfet_03v3 L=1u    W=4u nf=1
.ends
""",
    # Native passives: a real poly resistor and a metal4/metal5 MIM, neither
    # of which gLayout can build in a form gf180 recognises. Both must
    # extract as the actual PDK primitives, not as a pfet or as nothing.
    "RC Filter (native passives)": """
.lib "{PDK_LIB}" typical
.subckt rc_filter vin vout vss
XR1 vin  vout ppolyf_u W=1u L=4u
XC1 vout vss  cap_mim_2f0_m4m5_noshield W=5u L=5u
.ends
""",



    "StrongArm-Comparator": """
.lib "{PDK_LIB}" typical
.subckt strongarm vdd vss clk inn inp outn outp
XM1 tail clk vss vss nfet_03v3 L=1u W=2u nf=1 
XM2 d1 inn tail vss nfet_03v3 L=1u W=2u nf=1 
XM3 d2 inp tail vss nfet_03v3 L=1u W=2u nf=1 
XM4 outn outp d1 vss nfet_03v3 L=1u W=2u nf=1 
XM5 outp outn d2 vss nfet_03v3 L=1u W=2u nf=1 
XM6 outn outp vdd vdd pfet_03v3 L=1u W=2u nf=1 
XM7 outp outn vdd vdd pfet_03v3 L=1u W=2u nf=1 
XM8 outn clk vdd vdd pfet_03v3 L=1u W=2u nf=1 
XM9 outp clk vdd vdd pfet_03v3 L=1u W=2u nf=1 
XM10 d1 clk vdd vdd pfet_03v3 L=1u W=2u nf=1 
XM11 d2 clk vdd vdd pfet_03v3 L=1u W=2u nf=1 
.ends
"""
}

def _workspace():
    """Run inside a results directory.

    spice_to_gds_with_checks() writes <cwd>/<cell_name>/, so running this
    suite from the repository root used to scatter design directories across
    it. Everything now lands under outputs/regression/ instead.
    """
    root = os.path.dirname(_repo_src())
    ws = os.environ.get("MBG_TEST_OUTPUT") or os.path.join(root, "outputs", "regression")
    os.makedirs(ws, exist_ok=True)
    return ws


def main():
    print("============================================================")
    print("  VERIFYING DESIGNS")
    print("============================================================")

    ws = _workspace()
    os.chdir(ws)
    print(f"  output directory: {ws}")

    results = {}

    for name, netlist in DESIGNS.items():
        print(f"\n--- Testing: {name} ---")
        # the netlists carry a {PDK_LIB} placeholder so no personal path is
        # baked into this file; resolve it against the live PDK here
        netlist = netlist.replace("{PDK_LIB}", PDK_LIB)
        t0 = time.time()
        try:
            res = spice_to_gds_with_checks(netlist)
            t_elapsed = time.time() - t0
            results[name] = res
            print(f"  Routing time: {t_elapsed:.2f}s")
            print(f"  DRC:          {res['drc'].get('summary', '?')}")
            print(f"  LVS:          {'MATCH' if res['lvs'].get('match') else 'MISMATCH'}")
        except Exception as e:
            print(f"  FAILED: {e}")
            results[name] = {'drc': {}, 'lvs': {}}

    print("\n============================================================")
    print("  FINAL SUMMARY")
    print("============================================================")
    for name, res in results.items():
        drc = res['drc'].get('summary', 'ERROR')
        lvs = 'MATCH' if res['lvs'].get('match') else 'MISMATCH'
        print(f"  {name}: DRC={drc} | LVS={lvs}")
    print("============================================================")

    ok = all(r["drc"].get("clean") and r["lvs"].get("match") for r in results.values())
    print(f"  {sum(1 for r in results.values() if r['drc'].get('clean') and r['lvs'].get('match'))}"
          f"/{len(results)} designs pass DRC + LVS")
    return 0 if ok and results else 1


if __name__ == "__main__":
    sys.exit(main())
