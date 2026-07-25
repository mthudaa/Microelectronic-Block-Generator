#!/usr/bin/env python3
"""
Run all verification checks: DRC → LVS → PEX.
Usage: python3 scripts/run_all_checks.py layout.gds --netlist netlist.spice --cell cellname
"""
import sys, os, argparse
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from common.utils import setup_env, print_banner, print_result, run_cmd
setup_env()

def main():
    parser = argparse.ArgumentParser(description="Run DRC + LVS + PEX")
    parser.add_argument("gds", help="GDS layout file")
    parser.add_argument("--netlist", "-n", help="SPICE schematic netlist", required=True)
    parser.add_argument("--cell", "-c", default=None, help="Top cell name")
    parser.add_argument("--workdir", "-w", default="/tmp/mbg_verify", help="Working directory")
    args = parser.parse_args()
    
    cell = args.cell or os.path.splitext(os.path.basename(args.gds))[0]
    os.makedirs(args.workdir, exist_ok=True)
    
    from core.checks import run_drc, run_lvs, run_pex
    
    # 1. DRC
    print_banner("1. DRC")
    drc = run_drc(args.gds, cell_name=cell, engine="magic", workdir=f"{args.workdir}/drc")
    drc_ok = drc["clean"]
    print_result("DRC", drc_ok, drc["summary"])
    
    # 2. LVS
    print_banner("2. LVS")
    with open(args.netlist) as f:
        netlist_content = f.read()
    lvs = run_lvs(args.gds, netlist_content=netlist_content, cell_name=cell,
                  workdir=f"{args.workdir}/lvs", auto_fix_ports=True, timeout=600)
    lvs_ok = lvs["match"]
    print_result("LVS", lvs_ok, lvs["summary"]["message"])
    if not lvs_ok and lvs["summary"]["port_swaps"]:
        print(f"    Port swaps: {lvs['summary']['port_swaps']}")
    
    # 3. PEX
    print_banner("3. PEX")
    pex = run_pex(args.gds, cell_name=cell, mode=2, workdir=f"{args.workdir}/pex", timeout=600)
    pex_ok = pex["pex_path"] is not None
    print_result("PEX", pex_ok, pex["summary"])
    
    # Summary
    print_banner("VERIFICATION SUMMARY")
    all_ok = drc_ok and lvs_ok and pex_ok
    print_result("OVERALL", all_ok)
    print(f"  GDS:  {args.gds}")
    print(f"  Cell: {cell}")
    print(f"  DRC:  {'✅' if drc_ok else '❌'} {drc['summary']}")
    print(f"  LVS:  {'✅' if lvs_ok else '❌'} {lvs['summary']['message']}")
    print(f"  PEX:  {'✅' if pex_ok else '❌'} {pex['summary']}")
    
    return 0 if all_ok else 1

if __name__ == "__main__":
    sys.exit(main())
