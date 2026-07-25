#!/usr/bin/env python3
"""
Run final verification checklist before tapeout.
Usage: python3 scripts/final_checklist.py layout.gds --netlist netlist.spice [--cell name]
"""
import sys, os, argparse
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from common.utils import setup_env, print_banner, print_result
setup_env()

def main():
    parser = argparse.ArgumentParser(description="Final tapeout checklist")
    parser.add_argument("gds", help="GDS layout file")
    parser.add_argument("--netlist", "-n", required=True, help="SPICE schematic")
    parser.add_argument("--cell", "-c", default=None, help="Top cell name")
    args = parser.parse_args()
    
    cell = args.cell or os.path.splitext(os.path.basename(args.gds))[0]
    wd = f"/tmp/tapeout_check_{cell}"
    os.makedirs(wd, exist_ok=True)
    
    from core.checks import validate_gds, run_drc, run_lvs, run_pex
    
    results = {}
    
    print_banner("TAPEOUT FINAL CHECKLIST")
    
    # 1. GDS Validation
    v = validate_gds(args.gds, cell_name=cell)
    results["gds"] = v["valid"]
    print_result("GDS Validation", v["valid"], v["message"])
    
    # 2. DRC
    drc = run_drc(args.gds, cell_name=cell, workdir=f"{wd}/drc")
    results["drc"] = drc["clean"]
    print_result("DRC", drc["clean"], drc["summary"])
    
    # 3. LVS
    with open(args.netlist) as f:
        nl = f.read()
    lvs = run_lvs(args.gds, netlist_content=nl, cell_name=cell, workdir=f"{wd}/lvs")
    results["lvs"] = lvs["match"]
    print_result("LVS", lvs["match"], lvs["summary"]["message"])
    if not lvs["match"] and lvs["summary"]["port_swaps"]:
        print(f"    Port swaps: {lvs['summary']['port_swaps']}")
    
    # 4. PEX
    pex = run_pex(args.gds, cell_name=cell, mode=2, workdir=f"{wd}/pex")
    results["pex"] = pex["pex_path"] is not None
    print_result("PEX", pex["pex_path"] is not None, pex["summary"])
    
    # Summary
    print_banner("OVERALL VERDICT")
    all_pass = all(results.values())
    print_result("TAPEOUT READY" if all_pass else "ISSUES FOUND", all_pass)
    for k, v in results.items():
        print(f"  {k.upper():8s}: {'✅' if v else '❌'}")
    
    return 0 if all_pass else 1

if __name__ == "__main__":
    sys.exit(main())
