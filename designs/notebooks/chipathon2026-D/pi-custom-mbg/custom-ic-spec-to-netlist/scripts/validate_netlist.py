#!/usr/bin/env python3
"""
Validate a SPICE netlist before simulation/layout.
Usage: python3 scripts/validate_netlist.py netlist.spice
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from common.utils import setup_env, print_banner, print_result
setup_env()

from core.spice_parser import parse_netlist_with_pdk

def validate(path):
    print_banner(f"Validating SPICE Netlist: {path}")
    with open(path) as f:
        content = f.read()
    
    # Basic checks
    checks = {}
    checks["has_content"] = bool(content.strip())
    print_result("File not empty", checks["has_content"], f"{len(content)} chars")
    
    checks["has_subckt"] = ".subckt" in content
    print_result("Has .subckt", checks["has_subckt"])
    
    checks["has_ends"] = ".ends" in content
    print_result("Has .ends", checks["has_ends"])
    
    # Parse
    try:
        parsed = parse_netlist_with_pdk(content)
        devices = [c for c in parsed.get("components", []) if c["type"] == "device"]
        checks["has_devices"] = len(devices) > 0
        print_result(f"Devices found", checks["has_devices"], f"{len(devices)} devices")
        for d in devices:
            params = d["parameters"]
            w = params.get("w", "?")
            l = params.get("l", "?")
            print(f"      {d['name']}: {d['model']} W={w} L={l}")
        checks["pdk"] = parsed["metadata"]["pdk"]
        print(f"  PDK detected: {checks['pdk']}")
    except Exception as e:
        print_result("Parsing", False, str(e))
        checks["parsed_ok"] = False
    
    all_ok = all(checks.values()) if all(isinstance(v, bool) for v in checks.values()) else False
    print()
    print_result("VALIDATION", all_ok)
    return all_ok

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 validate_netlist.py <netlist.spice>")
        sys.exit(1)
    sys.exit(0 if validate(sys.argv[1]) else 1)
