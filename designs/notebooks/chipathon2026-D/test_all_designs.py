#!/usr/bin/env python3
import os
import sys
import time

os.environ['PDK_ROOT'] = os.environ.get('PDK_ROOT', '/home/huda/.volare')
os.environ['PDK'] = os.environ.get('PDK', 'gf180mcuD')
pdkpath = f"{os.environ['PDK_ROOT']}/{os.environ['PDK']}"
os.environ['PDKPATH'] = os.environ.get('PDKPATH', pdkpath)
os.environ['STD_CELL_LIBRARY'] = os.environ.get('STD_CELL_LIBRARY', 'gf180mcu_fd_sc_mcu7t5v0')

from core.pipeline import spice_to_gds_with_checks

DESIGNS = {
    "Inverter": """
.lib "/home/huda/.volare/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" typical
.subckt inverter vdd vss in out
XM1p out in vdd vdd pfet_03v3 L=1u W=4u nf=1
XM1n out in vss vss nfet_03v3 L=1u W=2u nf=1
.ends
""",
    "3-stage Ring Oscillator": """
.lib "/home/huda/.volare/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" typical
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
.lib "/home/huda/.volare/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" typical
.subckt ota_5t vdd vss inn inp out
XM1 tail inn out1 vss nfet_03v3 L=1u W=2u nf=1
XM2 out inp tail vss nfet_03v3 L=1u W=2u nf=1
XM3 out1 out1 vdd vdd pfet_03v3 L=1u W=4u nf=1
XM4 out out1 vdd vdd pfet_03v3 L=1u W=4u nf=1
XM5 tail bias vss vss nfet_03v3 L=1u W=2u nf=1
.ends
""",
    "StrongArm-Comparator": """
.lib "/home/huda/.volare/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" typical
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

def main():
    print("============================================================")
    print("  VERIFYING DESIGNS")
    print("============================================================")

    results = {}

    for name, netlist in DESIGNS.items():
        print(f"\n--- Testing: {name} ---")
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

if __name__ == "__main__":
    main()
