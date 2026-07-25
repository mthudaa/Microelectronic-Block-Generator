#!/usr/bin/env python3
"""
Package all tapeout deliverables into a single directory.
Usage: python3 scripts/package_tapeout.py layout.gds --netlist netlist.spice [--cell name] [--output /tmp/tapeout]
"""
import sys, os, argparse, shutil, datetime, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from common.utils import setup_env
setup_env()

def main():
    parser = argparse.ArgumentParser(description="Package tapeout deliverables")
    parser.add_argument("gds", help="Final GDS layout")
    parser.add_argument("--netlist", "-n", required=True, help="SPICE schematic")
    parser.add_argument("--cell", "-c", default=None)
    parser.add_argument("--output", "-o", default="/tmp/tapeout")
    args = parser.parse_args()
    
    cell = args.cell or os.path.splitext(os.path.basename(args.gds))[0]
    
    # Create directory structure
    dirs = [
        f"{args.output}/gds",
        f"{args.output}/netlist",
        f"{args.output}/reports",
        f"{args.output}/simulation/pre_layout",
        f"{args.output}/simulation/post_layout",
    ]
    for d in dirs:
        os.makedirs(d, exist_ok=True)
    
    # Copy GDS
    shutil.copy2(args.gds, f"{args.output}/gds/{cell}.gds")
    gds_size = os.path.getsize(args.gds)
    
    # Copy netlist
    shutil.copy2(args.netlist, f"{args.output}/netlist/{cell}.spice")
    
    # Copy reports (if they exist)
    for src, dst in [
        (f"/tmp/drc/{cell}.magic.drc.rpt", f"reports/drc.rpt"),
        (f"/tmp/lvs/{cell}.lvs.out", f"reports/lvs.out"),
        (f"/tmp/pex/{cell}.pex.spice", f"reports/pex.spice"),
    ]:
        if os.path.isfile(src):
            shutil.copy2(src, f"{args.output}/{dst}")
    
    # Copy simulation data (if exists)
    for src, dst in [
        ("/tmp/pre.raw", "simulation/pre_layout/pre.raw"),
        ("/tmp/post.raw", "simulation/post_layout/post.raw"),
    ]:
        if os.path.isfile(src):
            shutil.copy2(src, f"{args.output}/{dst}")
    
    # Generate summary
    summary = f"""# Tapeout Summary
- **Design:** {cell}
- **Date:** {datetime.date.today()}
- **PDK:** GF180MCU
- **GDS:** gds/{cell}.gds ({gds_size/1024:.0f} kB)
- **Netlist:** netlist/{cell}.spice
- **Reports:** reports/
  - drc.rpt
  - lvs.out  
  - pex.spice
"""
    with open(f"{args.output}/summary.md", "w") as f:
        f.write(summary)
    
    # Print tree
    print(f"\nTapeout package: {args.output}")
    for root, dirs, files in os.walk(args.output):
        level = root.replace(args.output, "").count(os.sep)
        indent = "  " * level
        print(f"{indent}{os.path.basename(root)}/")
        for f in files:
            print(f"{indent}  {f}")

if __name__ == "__main__":
    main()
