#!/usr/bin/env python3
"""
Run SPICE simulation on a subcircuit netlist (transient by default).
Usage: python3 scripts/run_simulation.py netlist.spice [--type tran|ac|dc] [--output /tmp/sim]
"""
import sys, os, argparse
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from common.utils import setup_env, print_banner, print_result
setup_env()

from core.simulation import run_spice

def build_testbench(netlist_path, sim_type="tran", load_cap="10fF", vdd=1.8):
    """Build a testbench around the subcircuit."""
    with open(netlist_path) as f:
        content = f.read()
    
    # Extract subcircuit name and ports
    for line in content.splitlines():
        if line.strip().startswith(".subckt"):
            parts = line.strip().split()
            cell_name = parts[1]
            ports = parts[2:]
            break
    else:
        raise ValueError("No .subckt found")
    
    # Build testbench
    tb = content.rstrip()
    if not tb.endswith("\n.end"):
        tb += "\n"
    
    # Find VDD/VSS ports for supply
    has_vdd = any("vdd" in p.lower() for p in ports)
    has_vss = any("vss" in p.lower() for p in ports)
    
    for p in ports:
        if p.lower() == "vdd":
            tb += f"VDD {p} 0 DC {vdd}\n"
        elif p.lower() == "vss":
            tb += f"VSS {p} 0 DC 0\n"
    
    # Add input stimulus and load
    # (Simplified — user should customize based on circuit type)
    tb += f"\n* Add your input stimuli here\n"
    tb += f"* CL vout 0 {load_cap}\n"
    
    tb += "\n.control\n"
    if sim_type == "tran":
        tb += "tran 0.1n 80n\n"
    elif sim_type == "ac":
        tb += "ac dec 10 1 100meg\n"
    elif sim_type == "dc":
        tb += "dc vin 0 1.8 0.01\n"
    tb += "write /tmp/sim_output.raw\n"
    tb += ".endc\n.end\n"
    
    return tb

def main():
    parser = argparse.ArgumentParser(description="Run SPICE simulation")
    parser.add_argument("netlist", help="SPICE subcircuit netlist")
    parser.add_argument("--type", "-t", choices=["tran","ac","dc"], default="tran")
    parser.add_argument("--output", "-o", default="/tmp/sim_output.raw")
    args = parser.parse_args()
    
    tb = build_testbench(args.netlist, sim_type=args.type)
    result = run_spice(tb, timeout=300)
    
    if result["raw_path"]:
        print_result("Simulation", True, f"raw data at {result['raw_path']}")
    else:
        print_result("Simulation", False, result["stderr"][:500])
        sys.exit(1)

if __name__ == "__main__":
    main()
