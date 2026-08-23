"""Corrected PVT characterization for the deepseek_vref_1v2 design.

Runs lean per-corner sweeps (temperature, supply, IBIAS) with one ngspice
invocation each, and writes pvt_characterization.json with corner VREF,
tempco, line regulation and IBIAS sensitivity for the typical/ff/ss corners.
"""
import os
import re
import json
import sys

os.environ.setdefault("PDK_ROOT", os.path.expanduser("~/.volare"))
os.environ.setdefault("PDK", "gf180mcuD")
os.environ.setdefault("PDKPATH", os.path.expanduser("~/.volare/gf180mcuD"))

from mbg.simulation import run_spice
from run_vref import NETLIST, CELL, LIB, DESIGN, _read_dat

OUTDIR = os.path.dirname(os.path.abspath(__file__))
WD = os.path.join(OUTDIR, "sim", "pvt")
os.makedirs(WD, exist_ok=True)


def sweep_deck(netlist, cell, *, sweep="temp", corner="typical", temp=27.0,
               vdd=3.3, ibias=20e-6, cl=1e-12):
    from run_vref import parse_ports
    roles, ports = parse_ports(netlist, cell)
    core = "\n".join(l for l in netlist.splitlines()
                     if not l.strip().lower().startswith((".lib", ".include")))
    body = []
    body.append(f".include '{DESIGN}'")
    body.append(f".lib '{LIB}' {corner}")
    body.append(f".temp {temp}")
    body.append("")
    body.append(core.strip())
    body.append("")
    body.append(f"VDD {roles['vdd']} 0 {vdd}")
    body.append(f"VSSV {roles['vss']} 0 0")
    body.append(f"IIB 0 {roles['ibias']} DC {ibias}")
    body.append(f"CL {roles['vref']} 0 {cl}")
    body.append(f"X1 {' '.join(ports)} {cell}")
    body.append(".control")
    body.append("op")
    body.append(f"print v({roles['vref']})")
    body.append(f"print i(VDD)")
    body.append("set wr_singlescale")
    if sweep == "temp":
        body.append("dc temp -40 125 5")
        body.append(f"wrdata out.dat v({roles['vref']})")
    elif sweep == "vdd":
        body.append("dc VDD 2.7 3.6 0.05")
        body.append(f"wrdata out.dat v({roles['vref']})")
    elif sweep == "ibias":
        body.append("dc IIB 8u 32u 1u")
        body.append(f"wrdata out.dat v({roles['vref']})")
    body.append(".endc")
    body.append(".end")
    return "\n".join(body)


def run_sweep(netlist, *, sweep, corner, temp=27.0, workdir):
    os.makedirs(workdir, exist_ok=True)
    p = os.path.join(workdir, "out.dat")
    if os.path.isfile(p):
        os.remove(p)
    deck = sweep_deck(NETLIST, CELL, sweep=sweep, corner=corner, temp=temp)
    r = run_spice(deck, workdir=workdir, timeout=500, fmt="dat")
    out = {}
    for m in re.finditer(r"([\w()#.]+)\s*=\s*(-?\d*\.?\d*[eE][+-]?\d*)",
                         r.get("stdout", "")):
        out[m.group(1).lower()] = float(m.group(2))
    rows = _read_dat(p)
    return rows, out


def characterize():
    corners = ["typical", "ff", "ss"]
    temps = [-40, 0, 27, 60, 90, 125]
    result = {"corners": {}, "tempco_ppmC": {}, "line_reg_mV_V": {},
              "vref_swing_mV": {}, "idd_ua": {}, "ibias": {}}

    for corner in corners:
        wd = os.path.join(WD, corner)
        # temperature sweep at 3.3 V / 20 uA
        trows, out = run_sweep(NETLIST, sweep="temp", corner=corner, workdir=wd)
        if not trows:
            print(f"[PVT] temp sweep failed for {corner}")
            continue
        vref_27 = None
        for t, v in trows:
            if abs(t - 27) <= 2.5:
                vref_27 = v
        tmin = min(v for _, v in trows)
        tmax = max(v for _, v in trows)
        result["tempco_ppmC"][corner] = round(
            (tmax - tmin) / (1.2 * 165.0) * 1e6, 1)
        result["corners"][corner] = {"T": {str(t): round(v, 4)
                                           for t, v in trows}}
        result["idd_ua"][corner] = round(abs(
            out.get("i(vdd)", out.get("vdd#branch", 0))) * 1e6, 1)

        # supply sweep at 27 C -> line regulation and variation
        vrows, _ = run_sweep(NETLIST, sweep="vdd", corner=corner, workdir=wd)
        if vrows:
            vlo = v_hi = None
            for x, v in vrows:
                if abs(x - 3.0) < 0.02:
                    vlo = v
                if abs(x - 3.6) < 0.02:
                    v_hi = v
            if vlo is not None and v_hi is not None:
                result["line_reg_mV_V"][corner] = round((v_hi - vlo) / 0.6 * 1e3, 1)
            result["vref_swing_mV"][corner] = round(
                (max(v for _, v in vrows) - min(v for _, v in vrows)) * 1e3, 1)
            result["corners"][corner]["VDD"] = {
                "3.0": round(dict(vrows).get(3.0, float("nan")), 4),
                "3.3": round(dict(vrows).get(3.3, float("nan")), 4),
                "3.6": round(dict(vrows).get(3.6, float("nan")), 4),
                "2.7": round(dict(vrows).get(2.7, float("nan")), 4)}

        # IBIAS sensitivity at 27 C
        irows, _ = run_sweep(NETLIST, sweep="ibias", corner=corner, workdir=wd)
        if irows:
            idict = {}
            for x, v in irows:
                if abs(x - 10e-6) < 0.6e-6:
                    idict["10u"] = round(v, 4)
                if abs(x - 20e-6) < 0.6e-6:
                    idict["20u"] = round(v, 4)
                if abs(x - 30e-6) < 0.6e-6:
                    idict["30u"] = round(v, 4)
            result["ibias"][corner] = idict

        # 9-point PVT grid: VDD sweep at -40 and 125 C
        for t in (-40, 125):
            vrows, _ = run_sweep(NETLIST, sweep="vdd", corner=corner, temp=t,
                                 workdir=wd)
            if vrows:
                result["corners"][corner].setdefault("VDD_T", {})[str(t)] = {
                    "3.0": round(dict(vrows).get(3.0, float("nan")), 4),
                    "3.3": round(dict(vrows).get(3.3, float("nan")), 4),
                    "3.6": round(dict(vrows).get(3.6, float("nan")), 4)}
        print(f"[PVT] {corner}: done")

    path = os.path.join(OUTDIR, "pvt_characterization.json")
    with open(path, "w") as f:
        json.dump(result, f, indent=2)
        f.write("\n")
    print(f"[PVT] wrote {path}")
    return result


if __name__ == "__main__":
    res = characterize()
    for c in ("typical", "ff", "ss"):
        if c not in res["tempco_ppmC"]:
            continue
        print(f"  {c}: tempco={res['tempco_ppmC'][c]}ppm/C "
              f"line={res['line_reg_mV_V'].get(c)}mV/V "
              f"swing={res['vref_swing_mV'].get(c)}mV "
              f"idd={res['idd_ua'].get(c)}uA "
              f"ibias={res['ibias'].get(c)}")
