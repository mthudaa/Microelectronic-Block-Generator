"""Measurement for the Strong-Arm clocked comparator.

Runs the same metric set on a schematic netlist or a Magic-extracted
(post-PEX) netlist, so pre-layout and PEX numbers are directly comparable.

Metrics
-------
Required (flow specs):
  t_dec_ns        worst-case decision time over all input cases (<= 5 ns)
  out_swing_v     final differential swing (>= 0.9 * VDD)
  i_avg_ua        average supply current at the clock frequency (<= 500 uA)
  i_static_ua     supply current between comparisons, reset-quiescent (<= 10 uA)
  n_correct       number of cases (out of N) that decided with correct polarity
  precharge_ok    number of evaluations whose mid-reset outputs both >= 0.9*VDD
  regenerate_ok   number of evaluations that showed a regenerative transition
  icmr_lo / icmr_hi   largest contiguous input common-mode range where the
                      comparator still decides correctly within the delay budget

Characterization-only (info specs, reported not gated):
  t_dec_<v>mv_ns  worst decision time over both polarities at |VIN_DIFF| = <v> mV
  offset_mean_mv / offset_1sigma_mv / offset_3sigma_mv / mc_runs  (mismatch MC)

Polarity convention (verified by simulation): with INP > INN the differential
output OUTP - OUTN is positive (OUTP high, OUTN low).
"""

from __future__ import annotations

import math
import os
import re
import statistics

import numpy as np

from mbg.simulation import run_spice
from mbg.analysis import SimResult, _parse_wrdata

CELL = "strongarm_comparator"
_PORTS = ("VDD", "VSS", "INP", "INN", "CLK", "OUTP", "OUTN")

# Input differentials to characterize: |VIN_DIFF| = 5/10/25/50/100 mV, both signs.
VD_CASES = [5e-3, 10e-3, 25e-3, 50e-3, 100e-3,
            -5e-3, -10e-3, -25e-3, -50e-3, -100e-3]

_DEV_RE = re.compile(
    r"^(?P<head>\s*X\w+\s+(?:\S+\s+){3,4}\S*(?:fet|FET)\S*\s+.*?)"
    r"\b[Ww]\s*=\s*(?P<w>[0-9.eE+-]+)(?P<unit>[a-zA-Z]*)(?P<tail>.*)$")


def scale_devices(netlist: str, names, factor: float, w_max: float = 10.0) -> str:
    """Scale device widths (W) by ``factor`` for the named instances.

    ``names`` is a set of instance names (e.g. {"XM2", "XM3"}), or ``None`` to
    scale every transistor. Respects the GF180 per-finger width limit.
    """
    out = []
    for line in netlist.splitlines():
        m = _DEV_RE.match(line)
        if not m:
            out.append(line)
            continue
        if names is not None and line.split()[0] not in names:
            out.append(line)
            continue
        w = float(m.group("w"))
        unit = m.group("unit") or ""
        new_w = w * factor
        if unit.lower().startswith("u") and new_w >= w_max:
            new_w = w_max - 0.01
        out.append(f"{m.group('head')}W={new_w:g}{unit}{m.group('tail')}")
    return "\n".join(out) + ("\n" if netlist.endswith("\n") else "")


def strip_lib_lines(netlist: str) -> str:
    """Return the netlist without .lib/.include lines (we add our own)."""
    return "\n".join(
        l for l in netlist.splitlines()
        if not l.strip().lower().startswith((".lib", ".include"))).strip()


def find_ports(netlist: str, cell: str):
    m = re.search(rf"^\.subckt\s+{re.escape(cell)}\s+(.+)$", netlist,
                  re.MULTILINE | re.IGNORECASE)
    if not m:
        raise ValueError(f".subckt {cell} not found in netlist")
    return [p for p in m.group(1).split() if "=" not in p]


def map_roles(netlist: str, cell: str):
    """Map logical roles to the port names in this netlist.

    The schematic lists ports as VDD VSS INP INN CLK OUTP OUTN, but the
    Magic-extracted netlist re-orders them. Stimulus must be wired by name.
    """
    ports = find_ports(netlist, cell)
    roles = {"vdd": None, "vss": None, "inp": None, "inn": None,
             "clk": None, "outp": None, "outn": None}
    for p in ports:
        pl = p.lower().replace("!", "")
        if pl in ("vdd", "vcc", "avdd", "vdda"):
            roles["vdd"] = roles["vdd"] or p
        elif pl in ("vss", "gnd", "avss", "vss!", "vssa"):
            roles["vss"] = roles["vss"] or p
        elif pl in ("clk", "ck", "clock"):
            roles["clk"] = roles["clk"] or p
        elif pl in ("inp", "ip", "vinp", "vip", "inp!", "in", "vin"):
            roles["inp"] = roles["inp"] or p
        elif pl in ("inn", "inm", "im", "vinn", "vinm", "inm!"):
            roles["inn"] = roles["inn"] or p
        elif "out" in pl:
            if pl.endswith("p") or pl == "out":
                roles["outp"] = roles["outp"] or p
            else:
                roles["outn"] = roles["outn"] or p
        elif pl.startswith("vd"):
            roles["vdd"] = roles["vdd"] or p
        elif pl.startswith("vs"):
            roles["vss"] = roles["vss"] or p
    missing = [r for r, v in roles.items() if v is None]
    if missing:
        raise ValueError(f"could not identify port roles {missing} among {ports}")
    return roles, ports


def build_deck(netlist: str, *, corner: str, temp: float, vdd: float,
               vcm: float, vd_list, clk_period: float, t_eval: float,
               loads: dict, mismatch: bool = False, seed: int | None = None,
               pdk_models: str | None = None, tstep: str = "20p") -> str:
    """One transient deck; the inputs step to ``vd_list[k]`` every clock cycle.

    The k-th clock cycle (evaluation at t_eval + k*period) sees differential
    ``vd_list[k]`` (positive = INP above INN), so a single run characterises
    every case under identical loading.
    """
    pdk_models = pdk_models or os.path.join(
        os.environ.get("PDKPATH", os.path.expanduser("~/.volare/gf180mcuD")),
        "libs.tech", "ngspice", "sm141064.ngspice")
    pdk_design = os.path.join(
        os.path.dirname(pdk_models), "design.ngspice")

    # Wire stimulus to whichever port the netlist uses for each role. The
    # extracted (post-PEX) netlist re-orders the subckt ports.
    roles, ports = map_roles(netlist, CELL)
    P_VDD, P_VSS = roles["vdd"], roles["vss"]
    P_INP, P_INN = roles["inp"], roles["inn"]
    P_CLK, P_OUTP, P_OUTN = roles["clk"], roles["outp"], roles["outn"]

    n = len(vd_list)
    total = clk_period * n

    def pwl(vals):
        pts = [f"0 {vals[0]:.7f}"]
        for k in range(1, n):
            pts.append(f"{k * clk_period:.6g} {vals[k]:.7f}")
        return " ".join(pts)

    head = []
    if os.path.isfile(pdk_design):
        head.append(f".include '{pdk_design}'")
    head.append(f".lib '{pdk_models}' {corner}")
    head.append(f".temp {temp}")
    if mismatch:
        head.append(".param sw_stat_mismatch=1")

    vp = [vcm + vd / 2.0 for vd in vd_list]
    vn = [vcm - vd / 2.0 for vd in vd_list]

    body = head + [strip_lib_lines(netlist), ""]
    body += [f"Vsupply0 {P_VDD} 0 DC {vdd:.6f}",
             f"Vsupply1 {P_VSS} 0 DC 0.0",
             f"Vsrc0 {P_INP} 0 PWL({pwl(vp)})",
             f"Vsrc1 {P_INN} 0 PWL({pwl(vn)})",
             f"Vsrc2 {P_CLK} 0 PULSE(0 {vdd:.6f} {t_eval:.6g} 0.1n 0.1n "
             f"{0.5 * clk_period:.6g} {clk_period:.6g})"]
    for node, cap in loads.items():
        name = roles[node.lower()] if node.lower() in roles else node
        body.append(f"C_load_{node} {name} 0 {cap:.6g}")
    body.append(f"Xdut {' '.join(ports)} {CELL}")
    body += ["", ".probe tran i(Vsupply0)", ".control"]
    if seed is not None:
        body.append(f"set seed={seed}")
    body += [f"tran {tstep} {total:.6g}",
             f"wrdata comb.dat v({P_OUTP}) v({P_OUTN}) v({P_CLK}) i(Vsupply0)",
             ".endc", ".end", ""]
    return "\n".join(body)


def run_deck(deck: str, workdir: str, timeout: int = 600) -> SimResult:
    """Run a deck and parse the transient into a SimResult."""
    os.makedirs(workdir, exist_ok=True)
    r = run_spice(deck, workdir=workdir, timeout=timeout, fmt="dat")
    res = SimResult(analysis="tran", x_name="time", returncode=r["returncode"],
                    stdout=r.get("stdout", ""), stderr=r.get("stderr", ""),
                    workdir=r.get("workdir", ""), deck=deck)
    if r["returncode"] != 0:
        res.stderr = (res.stderr or "") + (r.get("stdout") or "")
        return res
    for p in r.get("dat_paths") or []:
        if os.path.basename(p) == "comb.dat":
            _parse_wrdata(res, p, "time", ["outp", "outn", "clk", "i_vdd"])
            break
    return res


def clk_rise_times(clk, t, vdd, t_lo=0.0, t_hi=None):
    """50%-VDD upward crossings of the clock."""
    if t_hi is None:
        t_hi = t[-1]
    out = []
    for i in range(1, len(t)):
        if t[i] < t_lo or t[i] > t_hi:
            continue
        a, b = clk[i - 1], clk[i]
        if a < 0.5 * vdd <= b and b != a:
            out.append(t[i - 1] + (0.5 * vdd - a) / (b - a) * (t[i] - t[i - 1]))
    return out


def _first_cross(t, a, b, level, t0, t1):
    """First crossing of (a - b) through ``+level`` or ``-level`` in (t0, t1]."""
    prev = None
    for i in range(len(t)):
        if t[i] <= t0:
            continue
        if t[i] > t1:
            break
        d = a[i] - b[i]
        if prev is None:
            prev = (t[i], d)
            continue
        t_p, d_p = prev
        for lv in (level, -level):
            if d_p != d and (d_p - lv) * (d - lv) <= 0:
                return t_p + (lv - d_p) / (d - d_p) * (t[i] - t_p)
        prev = (t[i], d)
    return None


def analyze_cycles(res: SimResult, *, vdd: float, vd_list, clk_period: float,
                   t_eval: float, delay_budget: float = 5e-9):
    """Per-evaluation-cycle decision metrics from one combined transient."""
    outp = np.asarray(res.signals.get("outp", []), dtype=float)
    outn = np.asarray(res.signals.get("outn", []), dtype=float)
    clk = np.asarray(res.signals.get("clk", []), dtype=float)
    # ngspice reports the current *into* the supply source's + terminal, so
    # the current drawn by the circuit is the negated reading.
    i_vdd = -np.asarray(res.signals.get("i_vdd", []), dtype=float)
    t = np.asarray(res.x, dtype=float)
    if len(t) == 0:
        return []

    rises = clk_rise_times(clk, t, vdd)
    cycles = []
    for k, vd in enumerate(vd_list):
        if k >= len(rises):
            break
        tr = rises[k]
        eval_end = tr + 0.6 * clk_period
        tc = _first_cross(t, outp, outn, 0.5 * vdd, tr, eval_end)
        t_dec = (tc - tr) if tc is not None else None

        # sample the settled differential at 40% into the evaluation window
        idx = np.searchsorted(t, tr + 0.4 * clk_period)
        idx = min(idx, len(outp) - 1)
        diff_settled = float(outp[idx] - outn[idx])
        correct = (diff_settled > 0) if vd >= 0 else (diff_settled < 0)

        # mid-reset precharge level (before this evaluation edge)
        idx_pc = np.searchsorted(t, tr - 0.25 * clk_period)
        idx_pc = max(0, min(idx_pc, len(outp) - 1))
        precharge_lo = min(float(outp[idx_pc]), float(outn[idx_pc]))

        cycles.append({
            "vd": vd,
            "t_rise": tr,
            "t_dec": t_dec,
            "diff_settled": diff_settled,
            "correct": bool(correct),
            "regenerated": tc is not None,
            "precharge_lo": precharge_lo,
            "i_vdd_mean": float(np.mean(i_vdd)),
        })

    # static current: quiescent reset windows [tr - 0.4p, tr - 0.1p], k >= 1
    stat = []
    for k in range(1, len(rises)):
        lo, hi = rises[k] - 0.4 * clk_period, rises[k] - 0.1 * clk_period
        m = (t >= lo) & (t <= hi)
        if m.any():
            stat.append(float(np.mean(i_vdd[m])))
    static_ua = 1e6 * (float(np.mean(stat)) if stat else 0.0)

    return cycles, static_ua


def run_combined(netlist, *, vcm=1.65, vdd=3.3, temp=27.0, corner="typical",
                 vd_list=None, clk_freq=10e6, loads=None, mismatch=False,
                 seed=None, workdir="sim", timeout=600, tstep="20p"):
    """Run the multi-cycle transient for a set of differentials."""
    vd_list = list(vd_list if vd_list is not None else VD_CASES)
    loads = loads or {"OUTP": 20e-15, "OUTN": 20e-15}
    clk_period = 1.0 / clk_freq
    t_eval = 0.2 * clk_period
    deck = build_deck(netlist, corner=corner, temp=temp, vdd=vdd, vcm=vcm,
                      vd_list=vd_list, clk_period=clk_period, t_eval=t_eval,
                      loads=loads, mismatch=mismatch, seed=seed, tstep=tstep)
    res = run_deck(deck, workdir)
    if res.returncode != 0:
        raise RuntimeError(
            f"ngspice failed (rc={res.returncode}): "
            f"{(res.stderr or res.stdout or '')[-800:]}")
    cycles, static_ua = analyze_cycles(res, vdd=vdd, vd_list=vd_list,
                                       clk_period=clk_period, t_eval=t_eval)
    if len(cycles) != len(vd_list):
        raise RuntimeError(
            f"expected {len(vd_list)} evaluation cycles, parsed {len(cycles)}")
    return res, cycles, static_ua


def measure_comparator(netlist, *, vdd=3.3, vss=0.0, vcm=1.65, temp=27.0,
                       corner="typical", clk_freq=10e6, loads=None,
                       workdir="sim", delay_budget=5e-9, timeout=600,
                       do_icmr=True, icmr_step=0.1, tstep="50p"):
    """Full nominal metric set for the flow loops."""
    clk_period = 1.0 / clk_freq
    res, cycles, static_ua = run_combined(
        netlist, vcm=vcm, vdd=vdd, temp=temp, corner=corner,
        clk_freq=clk_freq, loads=loads, workdir=workdir, timeout=timeout,
        tstep=tstep)

    t_dec = [c["t_dec"] for c in cycles]
    t_dec_ns = max((d * 1e9 for d in t_dec if d is not None), default=float("nan"))
    out_swing = max(abs(c["diff_settled"]) for c in cycles)
    n_correct = sum(1 for c in cycles if c["correct"])
    precharge_ok = sum(1 for c in cycles
                       if c["precharge_lo"] >= 0.9 * vdd)
    regen_ok = sum(1 for c in cycles if c["regenerated"])
    i_avg_ua = 1e6 * float(np.mean([c["i_vdd_mean"] for c in cycles]))

    m = {
        "t_dec_ns": t_dec_ns,
        "out_swing_v": out_swing,
        "i_avg_ua": i_avg_ua,
        "i_static_ua": static_ua,
        "n_correct": n_correct,
        "precharge_ok": precharge_ok,
        "regenerate_ok": regen_ok,
        "n_cases": len(cycles),
    }
    # per-differential decision times (worst over both polarities)
    for vd in (5e-3, 10e-3, 25e-3, 50e-3, 100e-3):
        ds = [c["t_dec"] for c in cycles if abs(c["vd"]) == vd
              and c["t_dec"] is not None]
        m[f"t_dec_{int(vd * 1000)}mv_ns"] = (
            max(ds) * 1e9 if ds else float("nan"))

    # per-case detail for the report
    m["_cases"] = [dict(c) for c in cycles]

    if do_icmr:
        lo, hi = measure_icmr(netlist, vdd=vdd, temp=temp, corner=corner,
                              clk_freq=clk_freq, loads=loads,
                              workdir=os.path.join(workdir, "icmr"),
                              delay_budget=delay_budget, timeout=timeout,
                              step=icmr_step)
        m["icmr_lo"] = lo
        m["icmr_hi"] = hi
    return m


def measure_icmr(netlist, *, vdd=3.3, temp=27.0, corner="typical",
                 clk_freq=10e6, loads=None, workdir="sim",
                 delay_budget=5e-9, vmin=0.7, vmax=2.8, step=0.1, timeout=600):
    """Largest contiguous common-mode range with correct, fast decisions."""
    loads = loads or {"OUTP": 20e-15, "OUTN": 20e-15}
    clk_period = 1.0 / clk_freq
    ok = {}
    for vcm in np.arange(vmin, vmax + 1e-9, step):
        vcm = round(float(vcm), 4)
        try:
            res, cycles, _ = run_combined(
                netlist, vcm=vcm, vdd=vdd, temp=temp, corner=corner,
                vd_list=[25e-3, -25e-3], clk_freq=clk_freq, loads=loads,
                workdir=os.path.join(workdir, f"vcm{vcm:.2f}"),
                timeout=timeout)
        except RuntimeError:
            ok[vcm] = False
            continue
        good = all(c["correct"] for c in cycles) and all(
            (c["t_dec"] is not None and c["t_dec"] <= delay_budget)
            for c in cycles)
        ok[vcm] = bool(good)
    vcms = sorted(ok)
    best = (None, None)
    cur = None
    for v in vcms:
        if ok[v]:
            if cur is None:
                cur = [v, v]
            else:
                cur[1] = v
        else:
            if cur is not None and (best[0] is None
                                    or cur[1] - cur[0] > best[1] - best[0]):
                best = (cur[0], cur[1])
            cur = None
    if cur is not None and (best[0] is None or cur[1] - cur[0] > best[1] - best[0]):
        best = (cur[0], cur[1])
    return best


def measure_offset_mc(netlist, *, vcm=1.65, vdd=3.3, temp=27.0, runs=60,
                      clk_freq=10e6, loads=None, workdir="sim",
                      timeout=600, ramp_span=0.030, ramp_step=0.005,
                      tstep="0.5n"):
    """Input-referred offset via mismatch Monte Carlo.

    Each MC sample runs one multi-cycle transient whose differential input
    steps from ``-ramp_span`` to ``+ramp_span`` across the clock cycles. The
    sign flip between consecutive cycles brackets the sample's input-referred
    offset, so one run per sample yields a 2.5 mV-resolution estimate.
    """
    loads = loads or {"OUTP": 20e-15, "OUTN": 20e-15}
    vd_ramp = list(np.arange(-ramp_span, ramp_span + 1e-12, ramp_step))
    offsets = []
    for i in range(runs):
        wd = os.path.join(workdir, f"mc{i:03d}")
        res, cycles, _ = run_combined(
            netlist, vcm=vcm, vdd=vdd, temp=temp, corner="statistical",
            vd_list=vd_ramp, clk_freq=clk_freq, loads=loads,
            mismatch=True, seed=i + 1, workdir=wd, timeout=timeout,
            tstep=tstep)
        sign = [+1 if c["diff_settled"] > 0 else -1 for c in cycles]
        # diff_settled > 0 == decided "plus" == INP was judged above INN.
        # vd > Vos decides plus; the flip point between consecutive cycles
        # therefore brackets the sample's input-referred offset.
        flip = None
        for k in range(1, len(sign)):
            if sign[k - 1] != sign[k]:
                v_l = vd_ramp[k - 1]
                v_h = vd_ramp[k]
                flip = 0.5 * (v_l + v_h)
                break
        if flip is None:
            # All cycles decided the same way. vd > Vos gives a "plus"
            # decision, so all-plus means Vos is below the lowest vd and
            # all-minus means Vos is above the highest vd.
            flip = vd_ramp[0] if sign[-1] == 1 else vd_ramp[-1]
        offsets.append(flip)
    if not offsets:
        raise RuntimeError("Monte Carlo produced no samples")
    a = np.asarray(offsets) * 1e3  # mV
    return {
        "offset_mean_mv": float(np.mean(a)),
        "offset_1sigma_mv": float(np.std(a)),
        "offset_3sigma_mv": float(3.0 * np.std(a)),
        "mc_runs": len(a),
        "offset_samples_mv": a,
    }
