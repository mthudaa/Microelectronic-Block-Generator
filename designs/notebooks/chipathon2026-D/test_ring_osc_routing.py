#!/usr/bin/env python3
"""
Ring Oscillator auto-routing robustness test.

Tests the optimized auto_router on a 3-stage CMOS Ring Oscillator,
which is a challenging topology for routing due to:
  - Feedback loop (output feeds back to input)
  - Dense internal nets (n1→n2→n3→n1)
  - Many VDD/VSS connections (6 devices)
  - Mixed PMOS/NMOS multi-row placement

Usage:
    python test_ring_osc_routing.py
    # Or from notebook: %run test_ring_osc_routing.py
"""
import os
import sys
import time

# Environment setup
os.environ['PDK_ROOT'] = os.environ.get('PDK_ROOT', '/home/huda/.volare')
os.environ['PDK'] = os.environ.get('PDK', 'gf180mcuD')
pdkpath = f"{os.environ['PDK_ROOT']}/{os.environ['PDK']}"
os.environ['PDKPATH'] = os.environ.get('PDKPATH', pdkpath)
os.environ['STD_CELL_LIBRARY'] = os.environ.get('STD_CELL_LIBRARY', 'gf180mcu_fd_sc_mcu7t5v0')

# Add project root to path
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from core.pipeline import spice_to_gds_with_checks


def test_ring_oscillator_3stage():
    """Test 3-stage CMOS Ring Oscillator routing."""
    print("=" * 60)
    print("  RING OSCILLATOR (3-stage) — Auto-Routing Robustness Test")
    print("=" * 60)

    netlist = """
.lib "/home/huda/.volare/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" typical
.subckt ring_osc_3 vdd vss out
XM1p n1 out vdd vdd pfet_03v3 L=1u W=4u nf=1 m=1
XM1n n1 out vss vss nfet_03v3 L=1u W=2u nf=1 m=1
XM2p n2 n1 vdd vdd pfet_03v3 L=1u W=4u nf=1 m=1
XM2n n2 n1 vss vss nfet_03v3 L=1u W=2u nf=1 m=1
XM3p out n2 vdd vdd pfet_03v3 L=1u W=4u nf=1 m=1
XM3n out n2 vss vss nfet_03v3 L=1u W=2u nf=1 m=1
.ends
"""

    t0 = time.time()
    result = spice_to_gds_with_checks(netlist)
    t_elapsed = time.time() - t0

    print("\n" + "=" * 60)
    print("  RING OSCILLATOR — RESULTS SUMMARY")
    print("=" * 60)
    print(f"  Routing time: {t_elapsed:.2f}s")
    print(f"  Output:       {result['outdir']}/")
    print(f"  GDS:          {result['gds_path']}")
    print(f"  DRC:          {result['drc'].get('summary', '?')}")
    print(f"  LVS:          {'MATCH' if result['lvs'].get('match') else 'MISMATCH'}")
    print(f"  PEX:          {result['pex'].get('summary', '?')}")
    print(f"  ALL PASS:     {'YES' if result['all_pass'] else 'NO'}")
    print("=" * 60)

    return result


def test_ring_oscillator_5stage():
    """Test 5-stage CMOS Ring Oscillator (more complex routing)."""
    print("\n" + "=" * 60)
    print("  RING OSCILLATOR (5-stage) — Stress Test")
    print("=" * 60)

    netlist = """
.lib "/home/huda/.volare/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" typical
.subckt ring_osc_5 vdd vss out
XM1p n1 out vdd vdd pfet_03v3 L=1u W=4u nf=1 m=1
XM1n n1 out vss vss nfet_03v3 L=1u W=2u nf=1 m=1
XM2p n2 n1 vdd vdd pfet_03v3 L=1u W=4u nf=1 m=1
XM2n n2 n1 vss vss nfet_03v3 L=1u W=2u nf=1 m=1
XM3p n3 n2 vdd vdd pfet_03v3 L=1u W=4u nf=1 m=1
XM3n n3 n2 vss vss nfet_03v3 L=1u W=2u nf=1 m=1
XM4p n4 n3 vdd vdd pfet_03v3 L=1u W=4u nf=1 m=1
XM4n n4 n3 vss vss nfet_03v3 L=1u W=2u nf=1 m=1
XM5p out n4 vdd vdd pfet_03v3 L=1u W=4u nf=1 m=1
XM5n out n4 vss vss nfet_03v3 L=1u W=2u nf=1 m=1
.ends
"""

    t0 = time.time()
    result = spice_to_gds_with_checks(netlist)
    t_elapsed = time.time() - t0

    print("\n" + "=" * 60)
    print("  RING OSCILLATOR (5-stage) — RESULTS SUMMARY")
    print("=" * 60)
    print(f"  Routing time: {t_elapsed:.2f}s")
    print(f"  Output:       {result['outdir']}/")
    print(f"  GDS:          {result['gds_path']}")
    print(f"  DRC:          {result['drc'].get('summary', '?')}")
    print(f"  LVS:          {'MATCH' if result['lvs'].get('match') else 'MISMATCH'}")
    print(f"  PEX:          {result['pex'].get('summary', '?')}")
    print(f"  ALL PASS:     {'YES' if result['all_pass'] else 'NO'}")
    print("=" * 60)

    return result


if __name__ == "__main__":
    r3 = test_ring_oscillator_3stage()
    r5 = test_ring_oscillator_5stage()

    print("\n\n" + "=" * 60)
    print("  FINAL SUMMARY")
    print("=" * 60)
    for label, r in [("3-stage", r3), ("5-stage", r5)]:
        lvs = "MATCH" if r["lvs"].get("match") else "MISMATCH"
        drc = r["drc"].get("summary", "?")
        print(f"  {label}: DRC={drc} | LVS={lvs} | PEX={r['pex'].get('summary', '?')}")
    print("=" * 60)
