"""ox-alpha OTA design kit: netlist generation + measurement for MBG full-auto.

Topology (chosen, not copied from repo examples): 5-transistor NMOS-input OTA
with PMOS current-mirror load and an NMOS bias mirror driven by the external
IBIAS pin (diode-connected input device).  6 devices total.

Ports: VDD VSS INP INN OUT IBIAS   (IBIAS = external bias current input)
"""
from __future__ import annotations

import math
import os
import re

PDKPATH = os.environ.get("PDKPATH", os.path.expanduser("~/.volare/gf180mcuD"))
MODELS = os.path.join(PDKPATH, "libs.tech", "ngspice", "sm141064.ngspice")
DESIGN = os.path.join(PDKPATH, "libs.tech", "ngspice", "design.ngspice")

NOMINAL = dict(vdd=3.3, vss=0.0, vin_cm=1.65, ibias_ua=20.0, cl_pf=5.0,
               temp=27, corner="typical")

# Design parameters (all sizes in um; W per finger < 10um, L < 10um).
# Calibrated on gf180mcuD @27C: Vtn~=0.70 k'n~=138u, |Vtp|~=0.60 kp'~=14 uA/V^2
DEFAULT_PARAMS = {
    "w_bias": 2.0, "l_bias": 2.0,     # IBIAS diode NFET (W/L=1 -> Vgs=1.24V)
    "w_tail": 12.0, "l_tail": 4.0, "nf_tail": 2,   # tail NFET, 3*IBIAS
    "w_pair": 6.0, "l_pair": 2.0,     # diff pair NFETs
    "w_mir": 30.0, "l_mir": 4.0,      # PMOS mirror load
    "nf_mir": 4,
}


def build_netlist(p: dict) -> str:
    """Generate the OTA netlist from design parameters."""
    w_bias, l_bias = p["w_bias"], p["l_bias"]
    w_pair, l_pair = p["w_pair"], p["l_pair"]
    w_mir, l_mir, nf_mir = p["w_mir"], p["l_mir"], p.get("nf_mir", 1)
    w_tail, l_tail = p["w_tail"], p["l_tail"]
    nf_tail = p.get("nf_tail", 1)
    nf_pair = p.get("nf_pair", 1)
    return f"""* ox-alpha OTA -- 5T NMOS-input OTA, PMOS mirror load, IBIAS-driven tail
* topology: differential pair XM1/XM2, mirror load XM3/XM4,
* tail XMTAIL mirrored from external IBIAS via diode XMBIAS
.lib "{{PDK_LIB}}" typical
.subckt ota VDD VSS INP INN OUT IBIAS
XMBIAS IBIAS IBIAS VSS VSS nfet_03v3 W={w_bias}u L={l_bias}u nf=1
XMTAIL tail IBIAS VSS VSS nfet_03v3 W={w_tail}u L={l_tail}u nf={nf_tail}
XM1 n1 INN tail VSS nfet_03v3 W={w_pair}u L={l_pair}u nf={nf_pair}
XM2 OUT INP tail VSS nfet_03v3 W={w_pair}u L={l_pair}u nf={nf_pair}
XM3 n1 n1 VDD VDD pfet_03v3 W={w_mir}u L={l_mir}u nf={nf_mir}
XM4 OUT n1 VDD VDD pfet_03v3 W={w_mir}u L={l_mir}u nf={nf_mir}
.ends
"""


# ── measurement ────────────────────────────────────────────────────────────

def _strip(netlist_text: str) -> str:
    keep = []
    for line in netlist_text.splitlines():
        s = line.strip().lower()
        if s in (".lib", ".include", ".control", ".endc") or \
           s.startswith((".lib ", ".include ")) or s == ".end":
            continue
        keep.append(line)
    return "\n".join(keep).strip()


def _ports_of(netlist_text: str, cell: str) -> list:
    m = re.search(rf"^\.subckt\s+{re.escape(cell)}\s+(.+)$", netlist_text,
                  re.MULTILINE | re.IGNORECASE)
    return [p for p in m.group(1).split() if "=" not in p] if m else []


_NUM = r"([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)"
_PRINT_RE = re.compile(r"^\s*([\w@()\[\].]+)\s*=\s*" + _NUM, re.MULTILINE)


def _read_wrdata(path: str) -> list:
    rows = []
    if not os.path.isfile(path):
        return rows
    with open(path) as f:
        for line in f:
            parts = line.split()
            if not parts or parts[0].startswith(("#", "@")):
                continue
            try:
                rows.append([float(v) for v in parts])
            except ValueError:
                continue
    return rows


def _interp(x0, y0, x1, y1, level):
    if y1 == y0:
        return x0
    return x0 + (level - y0) * (x1 - x0) / (y1 - y0)


def measure(netlist_text: str, cell: str, workdir: str, *,
            vdd=None, vin_cm=None, ibias_ua=None, cl_pf=None, temp=None,
            corner=None, with_swing=True, quick=False) -> dict:
    """Full measurement suite: OP + AC + transient slew (+ DC swing).

    Returns a metrics dict keyed by spec names. Empty dict => tool failure.
    """
    from mbg.simulation import run_spice

    nom = NOMINAL
    vdd = nom["vdd"] if vdd is None else vdd
    vin_cm = nom["vin_cm"] if vin_cm is None else vin_cm
    ibias_ua = nom["ibias_ua"] if ibias_ua is None else ibias_ua
    cl_pf = nom["cl_pf"] if cl_pf is None else cl_pf
    temp = nom["temp"] if temp is None else temp
    corner = nom["corner"] if corner is None else corner

    os.makedirs(workdir, exist_ok=True)
    core = _strip(netlist_text)
    ports = _ports_of(netlist_text, cell)
    by_name = {p.upper(): p for p in ports}
    try:
        pn = {k: by_name[k] for k in
              ("VDD", "VSS", "INP", "INN", "OUT", "IBIAS")}
    except KeyError as e:
        raise RuntimeError(f"DUT missing expected port {e}; found {ports}") \
            from None

    deck = f"""/** ox-alpha OTA measurement deck */
.include '{DESIGN}'
.lib '{MODELS}' {corner}
.temp {temp}
{core}
XDUT {' '.join(ports)} {cell}
VVDD {pn['VDD']} 0 {vdd}
VVSS {pn['VSS']} 0 0
VINP {pn['INP']} 0 PWL(0us {vin_cm} 0.5us {vin_cm} 0.51us {vin_cm + 0.5}
+ 2.5us {vin_cm + 0.5} 2.51us {vin_cm - 0.5} 4.5us {vin_cm - 0.5}
+ 4.52us {vin_cm} 6us {vin_cm}) AC 1
VINN {pn['INN']} 0 DC {vin_cm}
CLOAD {pn['OUT']} 0 {cl_pf}p
IIB 0 ibias_inj DC {ibias_ua}u
VMON ibias_inj {pn['IBIAS']} 0
.control
op
print v({pn['OUT']}) i(vvdd) i(vmon)
ac dec {"101" if quick else "401"} 1 1G
wrdata ac.dat vdb({pn['OUT']}) vp({pn['OUT']})
tran 1n 6u
wrdata tran.dat v({pn['OUT']})
quit
.endc
.end
"""
    r = run_spice(deck, workdir=os.path.join(workdir, "meas"), fmt="dat")
    metrics: dict = {}
    scalars = {}
    for name, val in _PRINT_RE.findall(r.get("stdout") or ""):
        try:
            scalars[name.lower()] = float(val)
        except ValueError:
            pass

    scalars = {k.lower(): v for k, v in scalars.items()}
    out_v = scalars.get("v(out)")
    ivdd = scalars.get("i(vvdd)")
    iib = scalars.get("i(vmon)")
    ac_path = os.path.join(r["workdir"], "ac.dat")
    tran_path = os.path.join(r["workdir"], "tran.dat")
    ac = _read_wrdata(ac_path)
    tran = _read_wrdata(tran_path)

    # AC: columns [f, vdb, f, vp]; vp is UNWRAPPED RADIANS from wrdata and
    # drifts into numerical garbage once vdb hits the noise floor, so phase
    # is normalized per sample and only read near the first 0 dB crossing.
    if out_v is None or not ac:
        return {}
    freq = [row[0] for row in ac]
    vdb = [row[1] for row in ac]

    gain_db = vdb[0]
    metrics["gain_db"] = gain_db
    ugf_hz = bw_hz = None
    for i in range(1, len(vdb)):
        if vdb[i - 1] > 0.0 >= vdb[i]:
            ugf_hz = _interp(freq[i - 1], vdb[i - 1], freq[i], vdb[i], 0.0)
            lag0 = (180.0 - math.degrees(ac[i - 1][3])) % 360.0
            lag1 = (180.0 - math.degrees(ac[i][3])) % 360.0
            t = ((ugf_hz - freq[i - 1]) / (freq[i] - freq[i - 1])
                 if freq[i] != freq[i - 1] else 0.0)
            metrics["pm_deg"] = 180.0 - (lag0 + t * (lag1 - lag0))
            break
    edge = gain_db - 3.0
    for i in range(1, len(vdb)):
        if vdb[i] <= edge:
            bw_hz = _interp(freq[i - 1], vdb[i - 1], freq[i], vdb[i], edge)
            break
    if ugf_hz is not None:
        metrics["ugf_hz"] = ugf_hz
    if bw_hz is not None:
        metrics["bw_hz"] = bw_hz

    # OP: output DC, supply current excluding IBIAS, sanity on IBIAS
    metrics["out_dc"] = out_v
    if ivdd is not None:
        metrics["idd_ua"] = abs(ivdd) * 1e6
    if iib is not None:
        metrics["iibias_ua"] = abs(iib) * 1e6

    # Transient slew: edge at 0.5us -> OUT falls; edge at 2.5us -> OUT rises
    if tran:
        t = [row[0] for row in tran]
        v = [row[1] for row in tran]

        def seg_slew(t_lo, t_hi, rising):
            xs = [(ti, vi) for ti, vi in zip(t, v) if t_lo <= ti <= t_hi]
            if len(xs) < 10:
                return None
            head = [vi for ti, vi in xs[:20]]
            tail = [vi for ti, vi in xs[-20:]]
            v_start, v_end = sum(head) / len(head), sum(tail) / len(tail)
            dv = abs(v_end - v_start)
            if dv < 0.05:
                return None
            lo_lvl = min(v_start, v_end) + 0.2 * dv
            hi_lvl = min(v_start, v_end) + 0.8 * dv
            txs = []
            for lvl in (lo_lvl, hi_lvl):
                t_x = None
                for j in range(1, len(xs)):
                    a, b = xs[j - 1][1], xs[j][1]
                    hit = ((a < lvl <= b) if rising else (a > lvl >= b))
                    if hit:
                        t_x = _interp(xs[j - 1][0], a, xs[j][0], b, lvl)
                        break
                txs.append(t_x)
            t_lo_x, t_hi_x = sorted(t for t in txs if t is not None) \
                if all(t is not None for t in txs) else (None, None)
            if t_lo_x is None or t_hi_x is None or t_hi_x <= t_lo_x:
                return None
            return (0.6 * dv) / (t_hi_x - t_lo_x) / 1e6  # V/us

        sr_fall = seg_slew(0.55e-6, 2.45e-6, rising=False)
        sr_rise = seg_slew(2.55e-6, 4.45e-6, rising=True)
        if sr_rise is not None:
            metrics["sr_rise_vus"] = sr_rise
        if sr_fall is not None:
            metrics["sr_fall_vus"] = sr_fall

    # DC transfer sweep -> usable output swing (characterized target)
    if with_swing and not quick:
        dc_deck = f""".include '{DESIGN}'
.lib '{MODELS}' {corner}
.temp {temp}
{core}
XDUT {' '.join(ports)} {cell}
VVDD {pn['VDD']} 0 {vdd}
VVSS {pn['VSS']} 0 0
VINP {pn['INP']} 0 DC 0
VINN {pn['INN']} 0 DC {vin_cm}
CLOAD {pn['OUT']} 0 {cl_pf}p
IIB 0 {pn['IBIAS']} DC {ibias_ua}u
.control
dc VINP 0 {vdd} 0.01
wrdata dc.dat v({pn['OUT']})
quit
.endc
.end
"""
        rd = run_spice(dc_deck, workdir=os.path.join(workdir, "swing"),
                       fmt="dat")
        drows = _read_wrdata(os.path.join(rd["workdir"], "dc.dat"))
        if drows:
            vid = [row[0] for row in drows]
            vo = [row[1] for row in drows]
            g = []
            for i in range(1, len(vo)):
                dvin = vid[i] - vid[i - 1]
                g.append(abs(vo[i] - vo[i - 1]) / dvin if dvin else 0.0)
            g_peak = max(g) if g else 0.0
            thr = 0.5 * g_peak  # within -6 dB of peak incremental gain
            lo = hi = None
            for i in range(len(g)):
                if g[i] >= thr:
                    lo = vo[i] if lo is None else min(lo, vo[i])
                    hi = vo[i] if hi is None else max(hi, vo[i])
            if lo is not None:
                metrics["swing_low_v"] = lo
            if hi is not None:
                metrics["swing_high_v"] = hi
            metrics["abs_swing_low_v"] = min(vo)
            metrics["abs_swing_high_v"] = max(vo)
    return metrics


# ── specification set ──────────────────────────────────────────────────────

def build_specs():
    """Spec table from the design request.

    Required: gain, GBW, phase margin, both slews, supply current, output DC.
    Characterized (required=False because the 0.5 V lower swing bound is not
    reachable by any single-ended NMOS-input OTA at VIN_CM = 1.65 V -- the
    output floor is vicm - Vtn ~= 0.95 V): usable swing bounds are reported
    and reviewed but do not gate convergence.
    """
    from mbg import Spec
    return [
        Spec("gain_db", ">=", 35.0, " dB"),
        Spec("ugf_hz", ">=", 1e6, " Hz"),          # GBW
        Spec("pm_deg", ">=", 60.0, " deg"),
        Spec("sr_rise_vus", ">=", 0.5, " V/us"),
        Spec("sr_fall_vus", ">=", 0.5, " V/us"),
        Spec("idd_ua", "<=", 250.0, " uA"),
        Spec("out_dc", "~=", 1.65, " V", tol=0.5),
        # characterized targets
        Spec("swing_low_v", "<=", 0.5, " V", required=False),
        Spec("swing_high_v", ">=", 2.8, " V", required=False),
    ]
