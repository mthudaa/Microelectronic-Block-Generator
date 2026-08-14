#!/usr/bin/env python3
"""Fast layout+LVS-only iteration (skips slow DRC+PEX). Usage: python3 iter_lvs.py <netlist>"""
import os, sys, re, json
os.environ.setdefault("PDK_ROOT", "/home/huda/.volare")
os.environ.setdefault("PDK", "gf180mcuD")
os.environ.setdefault("PDKPATH", "/home/huda/.volare/gf180mcuD")
sys.path.insert(0, "/home/huda/.opencode/tools")
from core.pipeline import spice_to_gds          # noqa
from core import run_lvs                          # noqa

cand = sys.argv[1]
nn = open(cand).read()
cell = re.search(r"\.subckt\s+(\S+)", nn).group(1)
outdir = os.path.join(os.getcwd(), "iter", cell)
os.makedirs(outdir, exist_ok=True)
gdsp = os.path.join(outdir, f"{cell}.gds")

try:
    top = spice_to_gds(nn, mode="analog", run_checks=False)
    top.write_gds(gdsp)
    print(f"[OK] GDS: {gdsp}")
except Exception as e:
    print(f"[ERR] layout failed: {e}")
    raise

lvs = run_lvs(gdsp, netlist_content=nn, cell_name=cell, workdir=outdir)
print(f"LVS match   : {lvs.get('match')}")
print(f"LVS summary : {lvs.get('summary')}")
rp = lvs.get("report_path")
if rp and os.path.exists(rp):
    txt = open(rp).read()
    tail = "\n".join(txt.splitlines()[-45:])
    print("\n---- LVS tail ----")
    print(tail)
