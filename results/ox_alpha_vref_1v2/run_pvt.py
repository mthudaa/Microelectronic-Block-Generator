#!/usr/bin/env python
"""PVT characterization of the FINAL PEX netlist (post-layout evidence)."""
import json
import os
import sys

sys.path.insert(0, "/home/huda/opensource-project/Microelectronic-Block-Generator/src")
import run_vref as rv
from mbg.analysis import Testbench

D = os.path.dirname(os.path.abspath(__file__))
PEX = os.path.join(D, "final", "vref_1v2.pex.spice")
CORNERS = ["typical", "ff", "ss", "fs", "sf"]
VDDS = [3.0, 3.3, 3.6]
TEMPS = [-40, 27, 125]


class PvtTB(Testbench):
    def __init__(self, *a, ibias_ua=20.0, temp=None, **kw):
        super().__init__(*a, **kw)
        self.ibias_ua = float(ibias_ua)
        self.temp = temp

    def _stimulus(self):
        lines = super()._stimulus()
        if self.temp is not None:
            lines.append(f".option temp={self.temp:g}")
        lines.append(f"IBIN IBIAS VSS DC {self.ibias_ua:g}u")
        return lines


def tb(corner, temp=None, ibias=20.0, tag=""):
    return PvtTB(open(PEX).read(), rv.CELL, supplies=dict(rv.SUPPLIES),
                 loads={"VREF": rv.CL}, workdir=os.path.join(
                     D, "pvt", f"{corner}_{tag}"),
                 corner=corner, temp=temp, ibias_ua=ibias)


def vref_at(corner, vdd, temp):
    t = tb(corner, temp=temp)
    # override the fixed supply value for this run
    t.supplies = {"VDD": float(vdd), "VSS": 0.0}
    r = t.op()
    if not r.ok:
        raise RuntimeError(f"op failed {corner} {vdd} {temp}")
    return r.value("VREF")


def main():
    out = {"netlist": PEX, "corners": {}, "ibias_sensitivity_uA": {},
           "notes": {"ibias_convention": "pin delivers current out to generator"}}

    for c in CORNERS:
        e = {}
        # full temperature sweep at nominal VDD -> tempco
        t = tb(c)
        rt = t._run("dc", t.build_deck(
            [], [f"dc temp {rv.T_LO:g} {rv.T_HI:g} {rv.T_STEP:g}",
                 "wrdata dc.dat v(VREF)"]), "T", ["VREF"], datfile="dc.dat")
        vs = list(rt.get("VREF"))
        xs = [rv.T_LO + rv.T_STEP * i for i in range(len(vs))]
        e["vref_vs_temp_v"] = {int(x): round(y, 5) for x, y in zip(xs, vs)}
        e["tempco_ppm_c"] = round((max(vs) - min(vs)) / vs[len(xs) // 2]
                                  / rv.SPAN_T * 1e6, 1)
        e["slope_mv_c"] = round(rv._lsq_slope(xs, vs) * 1e3, 4)

        # VDD x TEMP grid + line regulation windows
        grid, linewin = {}, {}
        for temp in TEMPS:
            tl = tb(c, temp=temp)
            rl = tl._run("dc", tl.build_deck(
                [], ["dc Vsupply0 2.7 3.6 0.05",
                     "wrdata dc.dat v(VREF)"]), "vdd", ["VREF"],
                datfile="dc.dat")
            vl = list(rl.get("VREF"))
            i30 = int(round((3.0 - 2.7) / 0.05))
            win = vl[i30:]
            grid[f"{temp}C"] = {f"{v}V": round(vl[int(round((v - 2.7) / 0.05))], 5)
                                for v in VDDS}
            linewin[f"{temp}C"] = {
                "dvref_3p0_3p6_mv": round((max(win) - min(win)) * 1e3, 3),
                "line_reg_mv_per_v": round((max(win) - min(win)) / 0.6 * 1e3, 2),
                "vref_at_2p7": round(vl[0], 5)}
        e["vref_grid_V"] = grid
        e["line"] = linewin
        out["corners"][c] = e
        print(c, "tempco", e["tempco_ppm_c"],
              "grid27", e["vref_grid_V"]["27C"])

    # IBIAS sensitivity on the final layout, typical corner
    for ib in (10.0, 20.0, 30.0):
        r = tb("typical", ibias=ib, tag=f"ib{ib:g}").op()
        out["ibias_sensitivity_uA"][f"{ib:g}uA"] = round(r.value("VREF"), 5)
    print("IBIAS:", out["ibias_sensitivity_uA"])

    with open(os.path.join(D, "pvt_characterization.json"), "w") as f:
        json.dump(out, f, indent=2)
    print("wrote pvt_characterization.json")


if __name__ == "__main__":
    main()
