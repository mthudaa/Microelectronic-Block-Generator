#!/usr/bin/env python3
"""
Debug helper for the mbg-full-automate and mbg-cowork-design skills.
Diagnoses and fixes common issues in the IC design flow.
Usage: python3 scripts/debug_flow.py --stage drc|lvs|sim|layout --gds file.gds [--netlist file.spice]
"""
import sys, os, argparse
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from common.utils import setup_env, print_banner, print_result
setup_env()

def diagnose_drc(gds_path, cell):
    from core.checks import run_drc
    drc = run_drc(gds_path, cell_name=cell, workdir="/tmp/mbg_debug/drc")
    if drc["clean"]:
        print_result("DRC", True, "no violations")
        return True
    
    report_text = ""
    if drc["report_path"] and os.path.isfile(drc["report_path"]):
        with open(drc["report_path"]) as f:
            report_text = f.read()
    
    print_result("DRC", False, f"{drc['error_count']} violations")
    
    # Categorize violations
    if "Metal2 spacing" in report_text:
        print("  → Fix: Remove met2_pin rectangles, keep labels only")
    if "Metal3 spacing" in report_text:
        print("  → Fix: Increase vertical gap between met3 segments")
    if "Via4 spacing" in report_text:
        print("  → Fix: Remove redundant via_met4_met5 in routes")
    if "Metal2 width" in report_text or "Metal3 width" in report_text:
        print("  → Fix: Remove extra metal polygons at port locations")
    
    return False

def diagnose_lvs(gds_path, netlist_content, cell):
    from core.checks import run_lvs
    lvs = run_lvs(gds_path, netlist_content=netlist_content, cell_name=cell,
                  workdir="/tmp/mbg_debug/lvs", auto_fix_ports=True)
    if lvs["match"]:
        print_result("LVS", True, "Circuits match uniquely")
        return True
    
    s = lvs["summary"]
    print_result("LVS", False, s["message"])
    if s["port_swaps"]:
        print(f"  Port swaps: {s['port_swaps']} (auto-fix should handle these)")
    if s["missing_devices"]:
        print(f"  Missing devices: {s['missing_devices']}")
    if s["device_mismatch"] != "?":
        print(f"  Device count: {s['device_mismatch']}")
    if s["net_mismatch"] != "?":
        print(f"  Net count: {s['net_mismatch']}")
        if "VSUBS" in str(s):
            print("  → Fix: Map VSUBS→vss in flattened netlist")
    
    return False

def diagnose_sim(netlist):
    from core.simulation import run_spice
    result = run_spice(netlist, timeout=120)
    if result["raw_path"]:
        print_result("Simulation", True, f"raw: {result['raw_path']}")
        return True
    err = result["stderr"][:500]
    print_result("Simulation", False)
    if "fnoicor" in err:
        print("  → Fix: Add '.include design.ngspice' before '.lib'")
    if "modelname" in err.lower():
        print("  → Fix: Use 'XM' prefix for MOSFETs (glayout convention)")
    if "incomplete" in err.lower():
        print("  → Fix: Add .tran/.ac/.control block to netlist")
    return False

def main():
    parser = argparse.ArgumentParser(description="Debug IC design flow")
    parser.add_argument("--stage", "-s", choices=["drc", "lvs", "sim", "layout", "all"], default="all")
    parser.add_argument("--gds", "-g", help="GDS layout file")
    parser.add_argument("--netlist", "-n", help="SPICE netlist file")
    parser.add_argument("--cell", "-c", default=None, help="Cell name")
    args = parser.parse_args()
    
    cell = args.cell or (os.path.splitext(os.path.basename(args.gds))[0] if args.gds else "unknown")
    
    print_banner("MBG Debug Flow")
    
    if args.stage in ("drc", "all") and args.gds:
        diagnose_drc(args.gds, cell)
    
    if args.stage in ("lvs", "all") and args.gds and args.netlist:
        with open(args.netlist) as f:
            nl = f.read()
        diagnose_lvs(args.gds, nl, cell)
    
    if args.stage in ("sim", "all") and args.netlist:
        with open(args.netlist) as f:
            nl = f.read()
        diagnose_sim(nl)
    
    if args.stage == "layout" and args.gds:
        from core.checks import validate_gds
        v = validate_gds(args.gds, cell_name=cell)
        print_result("GDS valid", v["valid"], v["message"])
        print(f"  Cells: {v['cells']}")
        print(f"  Size: {v['size']/1024:.0f} kB")

if __name__ == "__main__":
    main()
