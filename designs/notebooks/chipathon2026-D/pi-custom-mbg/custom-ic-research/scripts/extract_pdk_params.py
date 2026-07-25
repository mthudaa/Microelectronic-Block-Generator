#!/usr/bin/env python3
"""
Extract key PDK parameters for design research.
Usage: python3 scripts/extract_pdk_params.py [--pdk gf180mcuD]
"""
import sys, os, re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

def extract_models(pdk_path):
    """Extract MOSFET model parameters from PDK SPICE file."""
    models = {}
    for lib_file in ["sm141064.ngspice", "design.ngspice"]:
        path = f"{pdk_path}/libs.tech/ngspice/{lib_file}"
        if not os.path.isfile(path):
            continue
        with open(path) as f:
            for line in f:
                m = re.match(r'\.model\s+(\S+)\s+(nmos|pmos)', line, re.I)
                if m:
                    name = m.group(1)
                    models[name] = models.get(name, {})
                    models[name]["type"] = m.group(2).lower()
                # Extract VTO
                m2 = re.search(r'vto\s*=\s*([-\d.e+]+)', line, re.I)
                if m2 and name:
                    models[name]["vto"] = float(m2.group(1))
    return models

def main():
    pdk_root = os.environ.get("PDK_ROOT", "/home/huda/.volare")
    pdk = os.environ.get("PDK", "gf180mcuD")
    pdk_path = f"{pdk_root}/{pdk}"
    
    print(f"PDK: {pdk} at {pdk_path}")
    print("=" * 50)
    
    models = extract_models(pdk_path)
    print(f"\nFound {len(models)} models:")
    for name, params in sorted(models.items()):
        vto = params.get("vto", "?")
        print(f"  {name}: type={params['type']} VTO={vto}")

if __name__ == "__main__":
    main()
