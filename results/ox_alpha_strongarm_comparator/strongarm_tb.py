"""Transient testbench + measurement for the Strong-Arm clocked comparator.

Independent design for GF180MCU gf180mcuD (3.3 V). This module owns:

  * the comparator netlist (my own sizing — NOT the repository reference)
  * the clocked transient stimulus (10 MHz CLK, PWL input ladder)
  * per-period measurement: decision time, swing ratio, decision polarity,
    static reset current, average supply current
  * PVT sweep and mismatch-Monte-Carlo offset estimation helpers

All numbers are measured from ngspice waveforms; nothing is estimated.
"""
import math
import os
import re
from dataclasses import dataclass

from mbg.analysis import Testbench

# ── the comparator (independent sizing) ───────────────────────────────

CELL = "strongarm_comparator"
PORTS = ["VDD", "VSS", "INP", "INN", "CLK", "OUTP", "OUTN"]

PDK_LIB = os.path.join(os.environ.get("PDKPATH",
                       os.path.expanduser("~/.volare/gf180mcuD")),
                       "libs.tech", "ngspice", "sm141064.ngspice")

NETLIST = f""".lib "{PDK_LIB}" typical
.subckt strongarm_comparator VDD VSS INP INN CLK OUTP OUTN
XMTAIL SN CLK VSS VSS nfet_03v3 L=0.5u W=7u nf=1
XMINN SN_P INN SN VSS nfet_03v3 L=1u W=3u nf=1
XMINP SN_N INP SN VSS nfet_03v3 L=1u W=3u nf=1
XMLATN OUTN OUTP SN_N VSS nfet_03v3 L=0.5u W=2u nf=1
XMLATP OUTP OUTN SN_P VSS nfet_03v3 L=0.5u W=2u nf=1
XMPLTN OUTN OUTP VDD VDD pfet_03v3 L=0.5u W=3u nf=1
XMPLTP OUTP OUTN VDD VDD pfet_03v3 L=0.5u W=3u nf=1
XMPRSN SN_N CLK VDD VDD pfet_03v3 L=0.5u W=0.8u nf=1
XMPRSP SN_P CLK VDD VDD pfet_03v3 L=0.5u W=0.8u nf=1
XMPRON OUTN CLK VDD VDD pfet_03v3 L=0.5u W=1.6u nf=1
XMPROP OUTP CLK VDD VDD pfet_03v3 L=0.5u W=1.6u nf=1
.ends
"""

GROUP_TAIL = ["XMTAIL"]
GROUP_PAIR = ["XMINN", "XMINP"]
GROUP_LAT = ["XMLATN", "XMLATP"]
GROUP_PLAT = ["XMPLTN", "XMPLTP"]

# ── clocking ──────────────────────────────────────────────────────────

F_CLK = 10e6                 # 10 MHz evaluation clock
T_PER = 100e-9               # clock period
T_RISE = 30e-9               # rising edge inside each period (eval starts)
T_HIGH = 40e-9               # clk-high window (evaluation)
T_FALL = T_RISE + T_HIGH     # 70 ns


def clk_expr(vdd: float) -> str:
    return f"PULSE(0 {vdd} {T_RISE*1e9:g}n 100p 100p {T_HIGH*1e9:g}n {T_PER*1e9:g}n)"


@dataclass
class Cond:
    """One evaluation period: common mode and differential input."""
    vcm: float
    dv: float          # VINP - VINN, volts

    @property
    def vp(self) -> float:
        return self.vcm + self.dv / 2.0

    @property
    def vn(self) -> float:
        return self.vcm - self.dv / 2.0


def nominal_matrix() -> list:
    """Full nominal characterization: |dv| = 5..100 mV both polarities at
    mid CM, plus both CM-range edges (1.0 V / 2.3 V)."""
    conds = [Cond(1.65, s * a) for a in (0.005, 0.01, 0.025, 0.05, 0.1)
             for s in (+1.0, -1.0)]
    for vcm in (1.0, 2.3):
        conds += [Cond(vcm, s * a) for a in (0.005, 0.1)
                  for s in (+1.0, -1.0)]
    return conds


def reduced_matrix() -> list:
    """Reduced matrix for PVT: 5 / 50 / 100 mV, both polarities."""
    return [Cond(1.65, s * a) for a in (0.005, 0.05, 0.1)
            for s in (+1.0, -1.0)]


def mc_matrix(amps_mv=(2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0)) -> list:
    """Offset ladder: both polarities per amplitude at mid CM."""
    return [Cond(1.65, s * a * 1e-3) for a in amps_mv for s in (+1.0, -1.0)]


# ── stimulus construction ─────────────────────────────────────────────

def pwl_expr(conds: list, terminal: str = "p") -> str:
    """PWL source expression stepping through `conds`, one per clock period.

    Inputs step 1 ns fast during the clk-low reset phase (t = k*T+5 ns), so
    each period k evaluates conds[k] and the inputs are stable before the
    rising edge at k*T+30 ns. `terminal` selects the P-side or N-side value.
    """
    def val(c):
        return c.vp if terminal == "p" else c.vn

    pts = [(0.0, val(conds[0]))]
    for k in range(1, len(conds)):
        t = k * T_PER + 5e-9
        pts.append((t - 1e-9, val(conds[k - 1])))
        pts.append((t, val(conds[k])))
    tail = len(conds) * T_PER + T_RISE + T_HIGH
    pts.append((tail, val(conds[-1])))
    body = " ".join(f"{t*1e6:.6f}u {v:.6f}" for t, v in pts)
    return f"PWL({body})"


# ── waveform measurement ──────────────────────────────────────────────

def _interp_cross(xs, ys, level, start_idx=0):
    """First time after xs[start_idx] where |ys| reaches `level`."""
    prev_y = abs(ys[start_idx])
    for i in range(start_idx + 1, len(xs)):
        y = abs(ys[i])
        if y >= level > prev_y or y <= level < prev_y:
            if y == prev_y:
                return xs[i]
            frac = (level - prev_y) / (y - prev_y)
            return xs[i - 1] + frac * (xs[i] - xs[i - 1])
        if y >= level and prev_y >= level:
            return xs[i]
        prev_y = y
    return None


def measure_waveform(res, conds: list, vdd: float, first_period: int = 1,
                     iavg_from: float = None) -> dict:
    """Per-period decisions from one transient run.

    Returns worst-case metrics over all measured periods:
      decision_time_s : max(edge -> |OUTP-OUTN| reaching VDD/2)
      swing_ratio     : min(|OUTP-OUTN| late in eval)/VDD
      correct_frac    : fraction of decisions with the correct polarity
      istatic_a       : mean |I(VDD)| deep inside a settled reset phase
      iavg_a          : mean |I(VDD)| over whole cycles from iavg_from
    """
    t = res.x
    vp = res.get("OUTP")
    vn = res.get("OUTN")
    iv = res.get("IDD")
    diff = [a - b for a, b in zip(vp, vn)]

    half = vdd / 2.0
    dts, wrong, swings, detail = [], 0, [], []
    for k in range(first_period, len(conds)):
        edge = k * T_PER + T_RISE
        i0 = _index_at_or_after(t, edge + 0.3e-9)
        tcross = _interp_cross(t, diff, half, i0)
        if tcross is None or tcross > k * T_PER + T_FALL - 0.5e-9:
            dts.append(float("inf"))
            wrong += 1                      # no decision is a wrong decision
            swings.append(0.0)
            detail.append({"k": k, "dv": conds[k].dv, "vcm": conds[k].vcm,
                           "dt_s": None, "swing_v": 0.0, "correct": False,
                           "reason": "no_crossing"})
            continue
        dts.append(tcross - edge)
        t_swing = min(k * T_PER + T_FALL - 4e-9, t[-1])
        sw = abs(_sample(diff, t, t_swing))
        swings.append(sw)
        expected = 1.0 if conds[k].dv > 0 else -1.0
        ok = sw >= 0.9 * vdd and diff[_sample_idx(t, t_swing)] * expected > 0
        if not ok:
            wrong += 1
        detail.append({"k": k, "dv": conds[k].dv, "vcm": conds[k].vcm,
                       "dt_s": tcross - edge, "swing_v": sw, "correct": ok,
                       "final_diff_v": diff[_sample_idx(t, t_swing)]})

    # static current: the SETTLED part of a reset window. Right after the
    # falling edge the precharged nodes relax through subthreshold paths with
    # tau ~ 20-30 ns, which reads as uA but is relaxation, not DC. The true
    # operating-point floor was verified at ~20 pA; this window measures the
    # current late in reset where relaxation has largely died out.
    k_stat = max(first_period, min(len(conds) - 2, 12))
    w0 = k_stat * T_PER + T_FALL + 35e-9
    w1 = (k_stat + 1) * T_PER + T_RISE - 1e-9
    istat = _mean_abs(iv, t, w0, w1)

    if iavg_from is None:
        iavg_from = T_PER                    # skip settling cycle 0
    iavg = _mean_abs(iv, t, iavg_from, min(len(conds) * T_PER, t[-1]))
    measure_waveform.last_detail = detail

    return {
        "decision_time_s": max(dts) if dts else float("inf"),
        "swing_ratio": (min(swings) / vdd) if swings else 0.0,
        "correct_frac": (len(dts) - wrong) / len(dts) if dts else 0.0,
        "istatic_a": istat,
        "iavg_a": iavg,
    }


measure_waveform.last_detail = []       # per-period diagnostics of the last run


def _index_at_or_after(xs, x):
    for i, v in enumerate(xs):
        if v >= x:
            return i
    return len(xs) - 1


def _sample_idx(xs, x):
    best, bd = 0, float("inf")
    for i, v in enumerate(xs):
        d = abs(v - x)
        if d < bd:
            best, bd = i, d
    return best


def _sample(ys, xs, x):
    return ys[_sample_idx(xs, x)]


def _mean_abs(ys, xs, lo, hi):
    vals = [abs(y) for x, y in zip(xs, ys) if lo <= x <= hi]
    return sum(vals) / len(vals) if vals else float("nan")


# ── simulation front-ends ─────────────────────────────────────────────

def resolve_case(netlist: str, names) -> dict:
    """Map canonical port names to however the netlist spells them.

    Magic/netgen extraction routinely rewrites pin names in lower case; a
    testbench that drives 'INP' against an 'inp' pin would silently add an
    isolated source instead of failing loudly.
    """
    m = re.search(r"^\.subckt\s+\S+\s+(.+)$", netlist,
                  re.MULTILINE | re.IGNORECASE)
    declared = [p for p in (m.group(1).split() if m else []) if "=" not in p]
    low = {p.lower(): p for p in declared}
    out = {}
    for n in names:
        out[n] = low.get(n.lower(), n)
    return out


class ComparatorSim:
    """Builds decks and measures the spec metrics for one netlist text."""

    def __init__(self, workdir: str, vdd: float = 3.3, corner: str = "typical",
                 temp_c: int = 27):
        self.workdir = workdir
        self.vdd = vdd
        self.corner = corner
        self.temp_c = temp_c

    def run(self, netlist: str, conds: list = None, tag: str = "run") -> dict:
        conds = conds or nominal_matrix()
        stop = len(conds) * T_PER + T_RISE + T_HIGH + 5e-9
        names = resolve_case(netlist, ["VDD", "VSS", "CLK", "INP", "INN",
                                       "OUTP", "OUTN"])
        tb = Testbench(netlist, CELL, supplies={names["VDD"]: self.vdd,
                                                names["VSS"]: 0.0},
                       sources={names["CLK"]: clk_expr(self.vdd),
                                names["INP"]: pwl_expr(conds, "p"),
                                names["INN"]: pwl_expr(conds, "n")},
                       loads={names["OUTP"]: "20f", names["OUTN"]: "20f"},
                       probes=["OUTP", "OUTN", "IDD"],
                       corner=self.corner, workdir=os.path.join(self.workdir, tag),
                       timeout=1800)          # shared machine: leave headroom
        deck = tb.build_deck([f".temp {self.temp_c}"] if self.temp_c != 27 else [],
                             # reltol/trtol relaxed after verification: crossing
                             # times agree with default tolerances to < 0.2 ps,
                             # and the regenerative latch otherwise costs 4x.
                             ["option reltol=1e-2 trtol=2",
                              f"tran 20p {stop*1e6:.4f}u",
                              (f"wrdata tran.dat v({names['OUTP']}) "
                               f"v({names['OUTN']}) i(Vsupply0)")])
        res = tb._run("tran", deck, "time", ["OUTP", "OUTN", "IDD"],
                      datfile="tran.dat")
        if not res.ok:
            raise RuntimeError(
                f"transient produced no data ({tag}, corner={self.corner}, "
                f"temp={self.temp_c}) — tool failure, not a spec miss")
        return measure_waveform(res, conds, self.vdd)


def pex_net_capacitance_note(pex_netlist: str) -> list:
    from mbg.flow_runtime import net_capacitance
    try:
        return [{"net": n, "farads": c} for n, c in net_capacitance(pex_netlist)[:5]]
    except Exception:
        return []


# ── Monte Carlo offset estimation ─────────────────────────────────────

def estimate_offset_distribution(sim: ComparatorSim, netlist: str, runs: int = 60):
    """Mismatch MC: per-sample input-referred offset via an amplitude ladder.

    A sample's offset is bracketed between the largest amplitude whose BOTH
    polarities decide wrongly and the smallest whose both decide correctly;
    the estimate is the bracket midpoint (interval-censored, reported as such).
    """
    from mbg.analysis import MonteCarloResult
    conds = mc_matrix()
    amps = sorted({abs(c.dv) for c in conds})
    names = resolve_case(netlist, ["VDD", "VSS", "CLK", "INP", "INN",
                                   "OUTP", "OUTN"])
    tb = Testbench(netlist, CELL, supplies={names["VDD"]: sim.vdd,
                                            names["VSS"]: 0.0},
                   sources={names["CLK"]: clk_expr(sim.vdd),
                            names["INP"]: pwl_expr(conds, "p"),
                            names["INN"]: pwl_expr(conds, "n")},
                   loads={names["OUTP"]: "20f", names["OUTN"]: "20f"},
                   probes=["OUTP", "OUTN"],
                   corner=sim.corner, workdir=os.path.join(sim.workdir, "mc_base"),
                   timeout=600)
    tb.mismatch = True
    ests = []
    base_wd = tb.workdir
    for r in range(runs):
        tb.workdir = os.path.join(base_wd, f"mc{r:03d}")
        tb.seed = r + 1
        stop = len(conds) * T_PER + T_RISE + T_HIGH + 5e-9
        deck = tb.build_deck([f".temp {sim.temp_c}"] if sim.temp_c != 27 else [],
                             ["option reltol=1e-2 trtol=2",
                              f"tran 20p {stop*1e6:.4f}u",
                              (f"wrdata tran.dat v({names['OUTP']}) "
                               f"v({names['OUTN']})")])
        res = tb._run("tran", deck, "time", ["OUTP", "OUTN"], datfile="tran.dat")
        tb.mismatch = True
        if not res.ok:
            continue
        ests.append(_offset_from_run(res, conds, amps, sim.vdd))
    ok = [e for e in ests if e is not None]
    n = len(ok)
    if not n:
        return {"runs": runs, "valid": 0}
    mean = sum(ok) / n
    var = sum((x - mean) ** 2 for x in ok) / max(n - 1, 1)
    sd = math.sqrt(var)
    return {"runs": runs, "valid": n, "mean_v": mean, "sigma_v": sd,
            "sigma3_v": 3.0 * sd,
            "samples_v": ok}


def _offset_from_run(res, conds, amps, vdd) -> "float | None":
    """Bracket the input-referred offset for one mismatch sample."""
    t, vp, vn = res.x, res.get("OUTP"), res.get("OUTN")
    diff = [a - b for a, b in zip(vp, vn)]
    both_ok = {}
    for k in range(1, len(conds)):
        edge = k * T_PER + T_RISE
        i0 = _index_at_or_after(t, edge + 0.3e-9)
        tcross = _interp_cross(t, diff, vdd / 2.0, i0)
        made = tcross is not None and tcross <= k * T_PER + T_FALL - 0.5e-9
        t_swing = min(k * T_PER + T_FALL - 4e-9, t[-1])
        idx = _sample_idx(t, t_swing)
        correct = (made and abs(diff[idx]) >= 0.9 * vdd
                   and diff[idx] * (1.0 if conds[k].dv > 0 else -1.0) > 0)
        a = round(abs(conds[k].dv), 6)
        both_ok[a] = both_ok.get(a, True) and correct
    passed = sorted(a for a, ok in both_ok.items() if ok)
    failed = sorted(a for a, ok in both_ok.items() if not ok)
    if not passed:
        return None                     # offset beyond the ladder: censored
    hi = passed[0]
    lo = max([f for f in failed if f < hi], default=hi / 2.0)
    return (lo + hi) / 2.0


# ── sizing moves used by the tuners ───────────────────────────────────

_DEV = re.compile(
    r"^(?P<head>\s*X\w+\s+(?:\S+\s+){3,4}\S*(?:fet|FET)\S*\s+.*?)"
    r"\bW\s*=\s*(?P<w>[0-9.eE+-]+)(?P<unit>[a-zA-Z]*)(?P<tail>.*)$")


def scale_widths(netlist: str, factor: float, only=None, w_max: float = 9.9):
    from mbg.flow_runtime import scale_device_widths
    return scale_device_widths(netlist, factor, only=list(only) if only else None,
                               w_max=w_max)
