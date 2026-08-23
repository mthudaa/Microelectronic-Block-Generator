"""Empirical topology exploration for the 1.2V MOS-only voltage reference.

Each candidate is measured with ONE ngspice invocation that runs three DC
sweeps (temperature, supply, IBIAS) and writes text tables via wrdata.
"""
import os
import re
import sys

os.environ.setdefault("PDK_ROOT", os.path.expanduser("~/.volare"))
os.environ.setdefault("PDK", "gf180mcuD")
os.environ.setdefault("PDKPATH", os.path.expanduser("~/.volare/gf180mcuD"))

from mbg.simulation import run_spice

LIB = os.path.join(os.environ["PDKPATH"], "libs.tech", "ngspice", "sm141064.ngspice")
DESIGN = os.path.join(os.environ["PDKPATH"], "libs.tech", "ngspice", "design.ngspice")

CELL = "vref_1v2"
WD = "/tmp/opencode/vref_sim"


def build_deck(netlist, *, temp=27.0, vdd=3.3, vss=0.0, ibias=20e-6, cl=1e-12,
               corner="typical"):
    body = []
    body.append(f".include '{DESIGN}'")
    body.append(f".lib '{LIB}' {corner}")
    body.append(f".temp {temp}")
    body.append("")
    body.append(netlist.strip())
    body.append("")
    body.append("VDD VDD 0 " + str(vdd))
    body.append("VSSV VSS 0 " + str(vss))
    body.append("IIB 0 IBIAS DC " + str(ibias))
    body.append("CL VREF 0 " + str(cl))
    body.append("")
    body.append("X1 VDD VSS VREF IBIAS vref_1v2")
    body.append(".control")
    body.append("op")
    body.append("print v(VREF)")
    body.append("print i(VDD) i(IIB)")
    body.append("set wr_singlescale")
    body.append("dc temp -40 125 5")
    body.append("wrdata temp.dat v(VREF)")
    body.append("dc VDD 2.7 3.6 0.05")
    body.append("wrdata vdd.dat v(VREF)")
    body.append("dc IIB 8u 32u 1u")
    body.append("wrdata ib.dat v(VREF)")
    body.append(".endc")
    body.append(".end")
    return "\n".join(body)


def _read_dat(path):
    rows = []
    if not os.path.isfile(path):
        return rows
    with open(path) as f:
        for ln in f:
            ln = ln.strip()
            if not ln or ln.startswith(("#", "Index", "Variables", "x", "Values",
                                        "Points", "Title", "Date", "Plotname",
                                        "Flags", "No.")) or ln.startswith("No. of"):
                continue
            parts = ln.split()
            if len(parts) >= 2:
                try:
                    rows.append((float(parts[0]), float(parts[1])))
                except ValueError:
                    continue
    return rows


def measure(netlist, workdir=None):
    """Return a full characterization dict for one netlist."""
    wd = workdir or WD
    os.makedirs(wd, exist_ok=True)
    for f in ("temp.dat", "vdd.dat", "ib.dat"):
        p = os.path.join(wd, f)
        if os.path.isfile(p):
            os.remove(p)
    deck = build_deck(netlist)
    r = run_spice(deck, workdir=wd, timeout=300, fmt="dat")
    out = {}
    for name, val in re.findall(
            r"^\s*([\w()#\.]+)\s*=\s*(-?\d*\.?\d*[eE]?[+-]?\d+)\s*$",
            r.get("stdout", ""), re.MULTILINE):
        out[name.lower()] = float(val)

    trows = _read_dat(os.path.join(wd, "temp.dat"))
    vrows = _read_dat(os.path.join(wd, "vdd.dat"))
    irows = _read_dat(os.path.join(wd, "ib.dat"))
    if not trows:
        print("  !! no temp.dat produced; ngspice stdout tail:")
        print("     " + (r.get("stdout") or "")[-600:].replace("\n", "\n     "))
        return None

    vref27 = None
    for t, v in trows:
        if abs(t - 27) < 2.5:
            vref27 = v
    for x, v in vrows:
        if abs(x - 3.3) < 0.03:
            vref27 = v
    if vref27 is None:
        vref27 = trows[0][1]
    tmin = min(v for _, v in trows)
    tmax = max(v for _, v in trows)
    tc = (tmax - tmin) / (1.2 * 165.0) * 1e6
    vlo = v_hi = v27 = v27b = None
    for x, v in vrows:
        if abs(x - 3.0) < 0.02:
            vlo = v
        if abs(x - 3.6) < 0.02:
            v_hi = v
        if abs(x - 3.3) < 0.02:
            v27 = v
        if abs(x - 2.7) < 0.02:
            v27b = v
    line = (v_hi - vlo) / 0.6 * 1000.0 if (v_hi is not None and vlo is not None) else None
    iv = {}
    for x, v in irows:
        if abs(x - 10e-6) < 0.6e-6:
            iv[10] = v
        if abs(x - 20e-6) < 0.6e-6:
            iv[20] = v
        if abs(x - 30e-6) < 0.6e-6:
            iv[30] = v
    idd = None
    for key in ("i(vdd)", "vdd#branch"):
        if key in out:
            idd = out[key]
            break
    return {
        "vref_27": vref27, "vref@3v3": v27, "vref@2v7": v27b,
        "vref_min": tmin, "vref_max": tmax,
        "tempco_ppmC": tc,
        "line_reg_mV/V": line,
        "vref@10u": iv.get(10), "vref@20u": iv.get(20), "vref@30u": iv.get(30),
        "idd_A": idd,
    }


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else ""
    net = open(path).read() if path and os.path.isfile(path) else CANDIDATE
    r = measure(net)
    if r is None:
        return 1
    for k, v in r.items():
        print(f"  {k:16s} = {v if v is None else '%.4g' % v}")
    return 0


CANDIDATE = """
* v0: simplest — IBIAS mirrored into a diode-connected nfet output.
.subckt vref_1v2 VDD VSS VREF IBIAS
XM0 ibg ibg VSS VSS nfet_03v3 L=2u W=4u nf=2
XM1 vref ibg VDD VDD pfet_03v3 L=2u W=4u nf=2
XM2 vref vref VSS VSS nfet_03v3 L=1u W=1u nf=1
.ends
"""

if __name__ == "__main__":
    sys.exit(main())
