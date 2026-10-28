"""Measurement recipes: the standard characterisation of a block type.

An agent designing a voltage reference should not have to rediscover how to
measure one — which sweep gives the temperature coefficient, how line
regulation is defined, where the bias current goes. These recipes encode
that once, on top of :class:`mbg.analysis.Testbench`, and return plain
dictionaries of metrics whose names match the spec presets below.

    from mbg.measure import measure_vref, SPEC_PRESETS
    m = measure_vref(netlist, corners="all")
    m["metrics"]["tc_ppm_c"], m["per_corner"]["ss"]["vref_v"]

The recipes work unchanged on extracted (PEX) netlists: they only need the
subcircuit's port names.

Metric names (voltage reference):
    vref_v            VREF at 27 C, nominal VDD, nominal corner
    tc_ppm_c          box-method TC over the temperature sweep, worst corner
    vref_t_min_v / vref_t_max_v   extremes of that sweep (nominal corner)
    line_reg_mv_v     max-min of VREF over the VDD window / window span
    dvref_line_mv     max-min of VREF over the VDD window
    ivdd_ua           supply current excluding the bias current
    ibias_sens_mv     largest VREF shift over the IBIAS sweep (info)
    psrr_db           VREF/VDD small-signal gain at 10 Hz (negative = good)
    startup_us        time for VREF to settle within 1 % after a VDD ramp
    vref_pvt_min_v / vref_pvt_max_v   over VDD x T x corners
"""
from __future__ import annotations

import math
import os
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence

from mbg.analysis import Testbench
from mbg.specs import Spec

# ── spec presets and parsing ──────────────────────────────────────────

#: prompt-test/VREF.md, the gate the 13 earlier reference experiments used.
VREF_MD = [
    Spec("vref_v", "==", 1.20, " V", tol=0.05),
    Spec("tc_ppm_c", "<=", 300.0, " ppm/C"),
    Spec("line_reg_mv_v", "<=", 100.0, " mV/V"),
    Spec("dvref_line_mv", "<=", 60.0, " mV"),
    Spec("ivdd_ua", "<=", 300.0, " uA"),
]

#: Bandgap-grade stretch targets — reported, not used as the gate by default.
BANDGAP = [
    Spec("vref_v", "==", 1.20, " V", tol=0.024),
    Spec("tc_ppm_c", "<=", 50.0, " ppm/C"),
    Spec("line_reg_mv_v", "<=", 5.0, " mV/V"),
    Spec("psrr_db", "<=", -40.0, " dB"),
    Spec("startup_us", "<=", 100.0, " us"),
    Spec("ivdd_ua", "<=", 300.0, " uA"),
]

SPEC_PRESETS = {"vref_md": VREF_MD, "bandgap": BANDGAP}

_SHORT = re.compile(r"^\s*(>=|<=|==|~=|>|<)\s*([-+0-9.eE]+)\s*(?:(?:\+-|±)\s*([-+0-9.eE]+))?\s*(.*)$")


def parse_spec(spec: Any) -> List[Spec]:
    """A preset name, ``{name: {op, target, ...}}``, ``{name: "<= 300"}`` or a list.

    The string shorthand is what an agent writes most naturally:
    ``{"tc_ppm_c": "<= 300", "vref_v": "== 1.2 +- 0.05"}``.
    """
    if isinstance(spec, str):
        if spec in SPEC_PRESETS:
            return list(SPEC_PRESETS[spec])
        raise ValueError(f"unknown spec preset {spec!r}; presets: {sorted(SPEC_PRESETS)}")
    out: List[Spec] = []
    items = spec.items() if isinstance(spec, dict) else (
        (d["name"], d) for d in spec)
    for name, d in items:
        if isinstance(d, str):
            m = _SHORT.match(d)
            if not m:
                raise ValueError(f"spec {name}: cannot parse {d!r}; write e.g. '<= 300'")
            op, tgt, tol, unit = m.groups()
            out.append(Spec(name, op, float(tgt), (" " + unit.strip()) if unit.strip() else "",
                            tol=float(tol) if tol else None))
        elif isinstance(d, (int, float)):
            out.append(Spec(name, "==", float(d), tol=0.0))
        else:
            out.append(Spec(name, d.get("op", "<="), float(d["target"]),
                            d.get("unit", ""), tol=d.get("tol"),
                            weight=d.get("weight", 1.0),
                            required=d.get("required", True)))
    return out


# ── helpers ───────────────────────────────────────────────────────────

#: ngspice's default RELTOL (1e-3) is +-1.2 mV on a 1.2 V reference — the
#: same size as the temperature drift being measured, and visible as steps
#: in a PEX temperature sweep. A reference is characterised at 1e-6.
PRECISION = (".options reltol=1e-6 vntol=1e-9 abstol=1e-15",)


_ECHO = re.compile(r"^mbg_(\w+)\s*=\s*(.+)$", re.MULTILINE)


def _echoed(stdout: str) -> Dict[str, List[float]]:
    out: Dict[str, List[float]] = {}
    for m in _ECHO.finditer(stdout or ""):
        vals = []
        for tok in m.group(2).split():
            try:
                vals.append(float(tok))
            except ValueError:
                pass
        out[m.group(1)] = vals
    return out


def _role_ports(ports: Sequence[str], given: Optional[Dict[str, str]]) -> Dict[str, Optional[str]]:
    roles = {"vdd": ("VDD", "AVDD", "VCC", "VPWR"), "vss": ("VSS", "GND", "AVSS", "VGND"),
             "vref": ("VREF", "VOUT", "OUT", "REF"), "ibias": ("IBIAS", "IB", "IREF")}
    out: Dict[str, Optional[str]] = {}
    upper = {p.upper(): p for p in ports}
    for role, names in roles.items():
        if given and given.get(role):
            out[role] = given[role]
            continue
        out[role] = next((upper[n] for n in names if n in upper), None)
    return out


def _settle_time(t: Sequence[float], y: Sequence[float], tol: float = 0.01) -> Optional[float]:
    if not t:
        return None
    final = y[-1]
    band = abs(final) * tol
    last_out = None
    for ti, yi in zip(t, y):
        if abs(yi - final) > band:
            last_out = ti
    return 0.0 if last_out is None else last_out


# ── voltage reference ─────────────────────────────────────────────────

def measure_vref(netlist: str, *, pdk: Optional[str] = None,
                 ports: Optional[Dict[str, str]] = None,
                 vdd: Optional[float] = None,
                 vdd_range: Optional[Sequence[float]] = None,
                 temp_range: Sequence[float] = (-40.0, 125.0, 5.0),
                 ibias: float = 20e-6, ibias_dir: str = "source",
                 ibias_sweep: Sequence[float] = (10e-6, 20e-6, 30e-6),
                 cl: str = "1p", corners: Any = None, quick: bool = False,
                 workdir: str = "vref_meas", timeout: int = 600) -> Dict[str, Any]:
    """Characterise a voltage reference. See the module docstring for metrics."""
    from mbg import pdk_profile
    cell = re.search(r"^\s*\.subckt\s+(\S+)", netlist, re.I | re.M).group(1)
    sub_ports = Testbench._ports_from_netlist(netlist, cell)
    roles = _role_ports(sub_ports, ports)
    for need in ("vdd", "vss", "vref"):
        if not roles[need]:
            raise ValueError(f"cannot find the {need.upper()} port among {sub_ports}; "
                             f"pass ports={{'{need}': '<name>'}}")
    prof = pdk_profile.resolve(pdk) if pdk else Testbench._profile_for(None, netlist)
    vdd = float(vdd if vdd is not None else prof.supply_v)
    lo_v, hi_v = (vdd_range or prof.supply_range)
    t_lo, t_hi, t_step = (list(temp_range) + [5.0])[:3]
    if corners in (None, [], ()):
        corner_list = [prof.default_corner]
    elif corners == "all" or corners == ["all"]:
        corner_list = prof.corners
    else:
        corner_list = [prof.canonical_corner(c) for c in corners]
    use_ib = bool(roles["ibias"]) and ibias > 0
    sign = 1.0 if ibias_dir == "source" else -1.0

    def tb(corner: str, wd: str, supplies=None, isrc=None) -> Testbench:
        isources = {}
        if use_ib:
            isources[roles["ibias"]] = isrc if isrc is not None else sign * ibias
        return Testbench(netlist, cell, pdk=prof.name, corner=corner,
                         supplies=supplies or {roles["vdd"]: vdd, roles["vss"]: 0.0},
                         isources=isources, loads={roles["vref"]: cl},
                         probes=[roles["vref"]], workdir=wd, timeout=timeout,
                         extra_lines=PRECISION)

    vref = roles["vref"]
    per: Dict[str, Dict[str, Any]] = {}
    data: Dict[str, Any] = {}
    warnings: List[str] = []
    for corner in corner_list:
        wd = os.path.join(workdir, corner)
        m: Dict[str, Any] = {}
        t = tb(corner, wd)
        # 1. nominal operating point and supply current
        r = t.run(["op", f"echo \"mbg_op = $&v({vref}) $&i(Vsupply0)\""],
                  analysis="op", workdir=os.path.join(wd, "op"))
        vals = _echoed(r.stdout).get("op", [])
        if len(vals) < 2:
            raise RuntimeError(f"[{corner}] operating point produced no data — see "
                               f"{os.path.join(wd, 'op')}/input.spice")
        m["vref_v"] = vals[0]
        i_tot = abs(vals[1])
        m["ivdd_ua"] = max(i_tot - (ibias if (use_ib and sign < 0) else 0.0), 0.0) * 1e6
        # 2. temperature sweep
        rt = t.dc("temp", t_lo, t_hi, t_step)
        if rt.ok and rt.x:
            ys = rt.get(vref)
            span = (t_hi - t_lo) or 1.0
            m["tc_ppm_c"] = (max(ys) - min(ys)) / abs(m["vref_v"]) / span * 1e6
            m["vref_t_min_v"], m["vref_t_max_v"] = min(ys), max(ys)
            data.setdefault("temp_sweep", {})[corner] = {"t": rt.x, "vref": ys}
        else:
            warnings.append(f"[{corner}] temperature sweep produced no data")
        # 3. line regulation
        sweep_lo = min(lo_v, vdd) - 0.3
        step = 0.02
        rl = t.dc(roles["vdd"], sweep_lo, max(hi_v, vdd), step)
        if rl.ok and rl.x:
            win = [y for x, y in zip(rl.x, rl.get(vref)) if lo_v - 1e-9 <= x <= hi_v + 1e-9]
            if win:
                m["dvref_line_mv"] = (max(win) - min(win)) * 1e3
                m["line_reg_mv_v"] = m["dvref_line_mv"] / max(hi_v - lo_v, 1e-9)
            data.setdefault("line_sweep", {})[corner] = {"vdd": rl.x, "vref": rl.get(vref)}
        else:
            warnings.append(f"[{corner}] line sweep produced no data")
        # 4. PVT grid: VDD {lo, nom, hi} x T {lo, 27, hi}
        ctrl = []
        k = 0
        grid = []
        for v in (lo_v, vdd, hi_v):
            for temp in (t_lo, 27.0, t_hi):
                ctrl += [f"alter Vsupply0 dc={v}", f"option temp={temp}", "op",
                         f"echo \"mbg_pvt{k} = $&v({vref})\""]
                grid.append((v, temp))
                k += 1
        rp = t.run(ctrl, analysis="pvt", workdir=os.path.join(wd, "pvt"))
        ev = _echoed(rp.stdout)
        pvt = [ev.get(f"pvt{i}", [None])[0] for i in range(k)]
        if all(x is not None for x in pvt):
            m["vref_pvt_min_v"], m["vref_pvt_max_v"] = min(pvt), max(pvt)
            data.setdefault("pvt", {})[corner] = [
                {"vdd": g[0], "temp": g[1], "vref": x} for g, x in zip(grid, pvt)]
        if not quick:
            # 5. IBIAS sensitivity
            if use_ib and ibias_sweep:
                ctrl = []
                for i, ib in enumerate(ibias_sweep):
                    ctrl += [f"alter Iisrc0 dc={sign * ib}", "op",
                             f"echo \"mbg_ib{i} = $&v({vref})\""]
                ri = t.run(ctrl, analysis="ibias", workdir=os.path.join(wd, "ibias"))
                ev = _echoed(ri.stdout)
                vs = [ev.get(f"ib{i}", [None])[0] for i in range(len(ibias_sweep))]
                if all(x is not None for x in vs):
                    m["ibias_sens_mv"] = max(abs(x - m["vref_v"]) for x in vs) * 1e3
                    m["vref_vs_ibias"] = dict(zip([f"{ib * 1e6:g}uA" for ib in ibias_sweep], vs))
            # 6. PSRR at 10 Hz
            try:
                tp = tb(corner, os.path.join(wd, "psrr"))
                ra = tp.ac(10, 1e6, points=10, ac_node=roles["vdd"])
                if ra.ok and ra.x:
                    mag = ra.get(vref)
                    m["psrr_db"] = 20 * math.log10(max(mag[0], 1e-12))
                    k1 = min(range(len(ra.x)), key=lambda i: abs(ra.x[i] - 1e3))
                    m["psrr_1k_db"] = 20 * math.log10(max(mag[k1], 1e-12))
            except Exception as e:                       # noqa: BLE001
                warnings.append(f"[{corner}] PSRR: {e}")
            # 7. startup: VDD ramps 0 -> vdd in 10 us; IBIAS ramps with it
            ts = Testbench(netlist, cell, pdk=prof.name, corner=corner,
                           supplies={roles["vdd"]: f"PWL(0 0 10u {vdd})", roles["vss"]: 0.0},
                           isources=({roles["ibias"]: f"PWL(0 0 10u {sign * ibias})"}
                                     if use_ib else {}),
                           loads={vref: cl}, probes=[vref],
                           workdir=os.path.join(wd, "startup"), timeout=timeout,
                           extra_lines=PRECISION)
            rs = ts.tran("0.1u", "200u")
            if rs.ok and rs.x:
                y = rs.get(vref)
                st = _settle_time(rs.x, y)
                m["startup_us"] = st * 1e6 if st is not None else None
                m["startup_final_v"] = y[-1]
                if abs(y[-1] - m["vref_v"]) > 0.05 * abs(m["vref_v"]):
                    warnings.append(f"[{corner}] after the VDD ramp VREF settles at "
                                    f"{y[-1]:.4f} V, not the DC solution {m['vref_v']:.4f} V "
                                    f"— the reference may need a startup circuit")
                    m["startup_ok"] = False
                else:
                    m["startup_ok"] = True
        per[corner] = m

    nominal = per[corner_list[0]] if prof.default_corner not in per else per[prof.default_corner]
    agg: Dict[str, Any] = {"vref_v": nominal.get("vref_v")}
    for key in ("tc_ppm_c", "line_reg_mv_v", "dvref_line_mv", "ivdd_ua",
                "ibias_sens_mv", "startup_us", "psrr_db"):
        vals = [p[key] for p in per.values() if p.get(key) is not None]
        if vals:
            agg[key] = max(vals)
    mins = [p["vref_pvt_min_v"] for p in per.values() if "vref_pvt_min_v" in p]
    maxs = [p["vref_pvt_max_v"] for p in per.values() if "vref_pvt_max_v" in p]
    if mins:
        agg["vref_pvt_min_v"], agg["vref_pvt_max_v"] = min(mins), max(maxs)
    if "vref_t_min_v" in nominal:
        agg["vref_t_min_v"], agg["vref_t_max_v"] = nominal["vref_t_min_v"], nominal["vref_t_max_v"]
    if any(p.get("startup_ok") is False for p in per.values()):
        agg["startup_ok"] = False
    elif any("startup_ok" in p for p in per.values()):
        agg["startup_ok"] = True
    return {"metrics": agg, "per_corner": per, "corners": corner_list,
            "conditions": {"pdk": prof.name, "cell": cell, "ports": roles,
                           "vdd": vdd, "vdd_window": [lo_v, hi_v],
                           "temp_range": [t_lo, t_hi, t_step],
                           "ibias_a": ibias if use_ib else 0.0,
                           "ibias_dir": ibias_dir if use_ib else None, "cl": cl},
            "data": data, "warnings": warnings}


# ── amplifier ─────────────────────────────────────────────────────────

def measure_ota(netlist: str, *, out: str, inp: str, inn: Optional[str] = None,
                supplies: Optional[Dict[str, float]] = None,
                bias: Optional[Dict[str, float]] = None,
                vcm: Optional[float] = None, cl: str = "1p",
                pdk: Optional[str] = None, corner: Optional[str] = None,
                workdir: str = "ota_meas", timeout: int = 600) -> Dict[str, Any]:
    """DC gain, -3 dB bandwidth, unity-gain frequency, phase margin, supply current."""
    from mbg import pdk_profile
    cell = re.search(r"^\s*\.subckt\s+(\S+)", netlist, re.I | re.M).group(1)
    sub_ports = Testbench._ports_from_netlist(netlist, cell)
    prof = pdk_profile.resolve(pdk) if pdk else Testbench._profile_for(None, netlist)
    if not supplies:
        roles = _role_ports(sub_ports, None)
        supplies = {roles["vdd"]: prof.supply_v, roles["vss"]: 0.0}
    vdd = max(supplies.values())
    vcm = vdd / 2 if vcm is None else vcm
    sources = dict(bias or {})
    sources[inp] = vcm
    if inn:
        sources[inn] = vcm
    tb = Testbench(netlist, cell, pdk=prof.name, corner=corner or prof.default_corner,
                   supplies=supplies, sources=sources, loads={out: cl},
                   probes=[out], workdir=workdir, timeout=timeout)
    r = tb.run(["op", f"echo \"mbg_op = $&v({out}) $&i(Vsupply0)\""],
               analysis="op", workdir=os.path.join(workdir, "op"))
    vals = _echoed(r.stdout).get("op", [])
    m: Dict[str, Any] = {}
    if len(vals) >= 2:
        m["vout_dc_v"] = vals[0]
        m["idd_ua"] = abs(vals[1]) * 1e6
        m["power_uw"] = abs(vals[1]) * vdd * 1e6
    ra = tb.ac(1, 1e10, points=20, ac_node=inp)
    if ra.ok and ra.x:
        mag = ra.get(out)
        re_p, im_p = ra.get(f"{out}.re"), ra.get(f"{out}.im")
        db = [20 * math.log10(max(v, 1e-15)) for v in mag]
        m["gain_db"] = db[0]
        bw = ra.bandwidth_3db(out)
        if bw is not None:
            m["bw_hz"] = bw
        ugf = None
        for i in range(1, len(db)):
            if db[i - 1] >= 0 > db[i]:
                t = db[i - 1] / (db[i - 1] - db[i])
                ugf = ra.x[i - 1] * (ra.x[i] / ra.x[i - 1]) ** t
                ph = math.degrees(math.atan2(im_p[i], re_p[i]))
                ph0 = math.degrees(math.atan2(im_p[0], re_p[0]))
                m["phase_margin_deg"] = 180.0 - abs(_unwrap(ph - ph0))
                break
        if ugf is not None:
            m["ugf_hz"] = ugf
    return {"metrics": m, "conditions": {"pdk": prof.name, "cell": cell, "vcm": vcm,
                                         "supplies": supplies, "cl": cl,
                                         "corner": tb.corner}}


def _unwrap(deg: float) -> float:
    while deg <= -360:
        deg += 360
    while deg > 0:
        deg -= 360
    return deg
