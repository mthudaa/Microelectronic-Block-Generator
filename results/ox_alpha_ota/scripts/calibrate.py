"""Calibrate GF180MCU 3.3V devices at target currents via DC sweeps."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ota_design import MODELS, DESIGN
from mbg.simulation import run_spice

OUT = sys.argv[1] if len(sys.argv) > 1 else "calib"
os.makedirs(OUT, exist_ok=True)

deck = f""".include '{DESIGN}'
.lib '{MODELS}' typical
.temp 27
* diode-ish test devices, forced currents via supplies
VD d 0 0.9
VG g 0 0.8
XN d g 0 0 nfet_03v3 W=2u L=2u
XP2 s2 g3 d3 s2 pfet_03v3 W=6.6u L=4u
VS2 s2 0 3.3
VAM d3 0 1.65
VG3 g3 0 2.0
.control
dc VG 0.4 1.6 0.005
wrdata nf.dat i(VD)
dc VG3 1.7 3.2 0.005
wrdata pf.dat i(VAM)
quit
.endc
.end
"""
r = run_spice(deck, workdir=OUT, fmt="dat")


def read(path):
    rows = []
    p = os.path.join(OUT, path)
    if not os.path.isfile(p):
        return rows
    for line in open(p):
        parts = line.split()
        if len(parts) >= 2:
            try:
                rows.append((float(parts[0]), float(parts[1])))
            except ValueError:
                pass
    return rows


def vgs_for(rows, target_ua):
    """Vgs where |I| crosses target (rows are (vgs, i))."""
    prev = None
    for vgs, i in rows:
        if abs(i) * 1e6 >= target_ua:
            if prev is None:
                return vgs
            (v0, i0), (v1, i1) = prev, (vgs, i)
            t = (abs(target_ua) * 1e-6 - abs(i0)) / max(abs(abs(i1) - abs(i0)), 1e-18)
            return v0 + t * (v1 - v0)
        prev = (vgs, i)
    return None


nf = read("nf.dat")
pf = read("pf.dat")
res = {}
for tgt in (10, 20, 30, 40):
    res[f"nf_W2L2@{tgt}uA"] = round(vgs_for(nf, tgt), 4) if nf else None
for tgt in (20, 40):
    res[f"pf_W6.6L4@{tgt}uA"] = round(vgs_for(pf, tgt), 4) if pf else None
# gm estimate near 20uA for nfet: (I(21u)-I(19u))/dVgs
if nf:
    def i_at(v):
        best = min(nf, key=lambda r: abs(r[0] - v))
        return abs(best[1])
    v20 = vgs_for(nf, 20)
    dv = 0.02
    gm = (i_at(v20 + dv) - i_at(v20 - dv)) / (2 * dv)
    res["nf_gm_uS_at_20uA"] = round(gm * 1e6, 1)
    res["nf_gm_over_id"] = round(gm * 1e6 / 20, 2)
if pf:
    def pi_at(v):
        best = min(pf, key=lambda r: abs(r[0] - v))
        return abs(best[1])
    vp20 = vgs_for(pf, 20)
    dv = 0.02
    gmp = (pi_at(vp20 + dv) - pi_at(vp20 - dv)) / (2 * dv)
    res["pf_gm_uS_at_20uA"] = round(gmp * 1e6, 1)

import json
print(json.dumps(res, indent=1))
with open(os.path.join(OUT, "calib.json"), "w") as f:
    json.dump(res, f, indent=1)
