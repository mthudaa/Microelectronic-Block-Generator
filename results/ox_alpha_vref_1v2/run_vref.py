#!/usr/bin/env python
"""MBG full-auto run: 1.2-V MOS-only voltage reference, gf180mcuD.

Topology (4 MOS, MOSFET-only, no R/C/BJT):
    XM1/XM2 pfet_03v3 mirror; the IBIAS pin delivers the external current to
            a generator tied to VSS (PFET diode input).
    XMT     nfet diode (moderate inversion), drain/gate = VREF.
    XMB     nfet common-gate with XMT, held in triode.
    VREF = VGS(XMT) + VDS(XMB); the triode term carries a positive tempco
    that cancels the negative tempco of the VGS term. Sizing sets the split.

Run: $MBG_VENV/bin/python results/ox_alpha_vref_1v2/run_vref.py
"""
import json
import math
import os
import sys

REPO = os.environ.get("MBG_ROOT",
                      "/home/huda/opensource-project/Microelectronic-Block-Generator")
sys.path.insert(0, os.path.join(REPO, "src"))

from mbg import Spec                                    # noqa: E402
from mbg.analysis import Testbench                      # noqa: E402
from mbg.flow import DesignPoint, FlowHooks             # noqa: E402
from mbg.flow_runtime import make_hooks                 # noqa: E402
from mbg.full_auto import FullAutoConfig, run_full_auto  # noqa: E402

CELL = "vref_1v2"
OUTDIR = os.path.dirname(os.path.abspath(__file__))
SUPPLIES = {"VDD": 3.3, "VSS": 0.0}
CL = "1p"
T_LO, T_HI, T_STEP = -40.0, 125.0, 5.0
SPAN_T = T_HI - T_LO

# Seed from pre-flight characterisation:
# VREF~1.17-1.18 V, tempco ~270 ppm/C, line-reg ~11 mV/V at typical corner.
# Grid discipline: SPICE W is TOTAL width and gLayout builds fingers of
# W/nf, so every W/nf is kept an exact multiple of 0.05 um >= 0.5 um --
# otherwise Magic extracts a quantised finger width and netgen flags a
# >1% device-property error against the schematic (seen at W=9.5 nf=16).
# Tuning therefore moves L and nf only, never W.
SEED = dict(mp_w=2.0, mp_l=8.0, mt_w=9.6, mt_l=0.35, mt_nf=12,
            mb_w=9.5, mb_l=7.45)
MT_NF_CHOICES = [8, 12, 16]      # finger widths 1.2 / 0.8 / 0.6 um

NETLIST_TMPL = """\
* 1.2-V MOS-only voltage reference (externally biased self-cascode)
* VREF = VGS(XMT) + VDS(XMB); XMB is common-gate triode supplying the
* positive-tempco term against the negative-tempco VGS(XMT) term.
* IBIAS pin convention: pin delivers IBIAS out to a generator tied to VSS.
.subckt vref_1v2 VDD VSS VREF IBIAS
XM1 IBIAS IBIAS VDD VDD pfet_03v3 W={mp_w:g}u L={mp_l:g}u nf=1
XM2 VREF  IBIAS VDD VDD pfet_03v3 W={mp_w:g}u L={mp_l:g}u nf=1
XMT VREF  VREF  VMB  VSS nfet_03v3 W={mt_w:g}u L={mt_l:g}u nf={mt_nf:d}
XMB VMB   VREF  VSS  VSS nfet_03v3 W={mb_w:g}u L={mb_l:g}u nf=1
.ends
"""

SPECS = [
    Spec("vref_nominal", ">=", 1.15, " V"),
    Spec("vref_nominal", "<=", 1.25, " V"),
    Spec("tempco_ppm_c", "<=", 300.0, " ppm/C"),
    Spec("line_reg_mv_per_v", "<=", 100.0, " mV/V"),
    Spec("dvref_line_mv", "<=", 60.0, " mV"),
    Spec("ivdd_uA", "<=", 300.0, " uA"),
]

PKEYS = ("mp_w", "mp_l", "mt_w", "mt_l", "mt_nf", "mb_w", "mb_l")


def build_netlist(p):
    return NETLIST_TMPL.format(**p)


def clamp_params(p):
    """Legal, grid-safe sizing: W fixed on-grid, L in range, nf discrete."""
    q = dict(p)
    q["mp_w"] = 2.0
    q["mt_w"] = 9.6
    q["mb_w"] = 9.5
    q["mp_l"] = min(max(float(q["mp_l"]), 1.0), 10.0)
    q["mt_l"] = min(max(float(q["mt_l"]), 0.30), 4.0)
    q["mb_l"] = min(max(float(q["mb_l"]), 0.5), 10.0)
    nf = int(q.get("mt_nf", 12))
    q["mt_nf"] = min(MT_NF_CHOICES, key=lambda c: (abs(c - nf), c))
    return q


class RefTB(Testbench):
    """Testbench with the external bias generator on the IBIAS pin."""

    def __init__(self, *a, ibias_ua=20.0, **kw):
        super().__init__(*a, **kw)
        self.ibias_ua = float(ibias_ua)

    def _stimulus(self):
        lines = super()._stimulus()
        lines.append(f"IBIN IBIAS VSS DC {self.ibias_ua:g}u")
        return lines


def _lsq_slope(xs, ys):
    n = len(xs)
    sx, sy = sum(xs), sum(ys)
    sxx = sum(x * x for x in xs)
    sxy = sum(x * y for x, y in zip(xs, ys))
    return (n * sxy - sx * sy) / (n * sxx - sx * sx)


def measure(netlist_text, workdir):
    """All reference metrics from ngspice DC analyses, typical corner."""
    m = {}
    tb = RefTB(netlist_text, CELL, supplies=dict(SUPPLIES),
               loads={"VREF": CL}, workdir=workdir, corner="typical")

    # nominal op + supply current (let/print parses reliably)
    r_op = tb._run("op", tb.build_deck(
        [], ["op", "print v(VREF)", "let ivdd = i(Vsupply0)",
             "print ivdd"]), "", ["VREF"])
    if not r_op.ok:
        raise RuntimeError("nominal op did not simulate")
    vref27 = r_op.value("VREF")
    ivdd_tot = abs(r_op.value("ivdd"))
    m["vref_nominal"] = vref27
    # internal consumption = total VDD current minus what exits via IBIAS
    m["ivdd_uA"] = max(ivdd_tot * 1e6 - 20.0, 0.0)

    # temperature sweep (-40 .. 125 C)
    rt = tb._run("dc", tb.build_deck(
        [], [f"dc temp {T_LO:g} {T_HI:g} {T_STEP:g}",
             "wrdata dc.dat v(VREF)"]), "T", ["VREF"], datfile="dc.dat")
    if not rt.ok or not rt.x:
        raise RuntimeError("temperature sweep produced no data")
    vs = list(rt.get("VREF"))
    xs = [T_LO + T_STEP * i for i in range(len(vs))]
    m["t_slope_mv_c"] = _lsq_slope(xs, vs) * 1e3
    m["vref_t_min"], m["vref_t_max"] = min(vs), max(vs)
    m["tempco_ppm_c"] = ((max(vs) - min(vs)) / vref27 / SPAN_T * 1e6)

    # line sweep 2.7 .. 3.6 V; spec window 3.0 .. 3.6
    rl = tb._run("dc", tb.build_deck(
        [], ["dc Vsupply0 2.7 3.6 0.02",
             "wrdata dc.dat v(VREF)"]), "vdd", ["VREF"], datfile="dc.dat")
    if not rl.ok or not rl.x:
        raise RuntimeError("line sweep produced no data")
    vl = list(rl.get("VREF"))
    i30 = int(round((3.0 - 2.7) / 0.02))
    win = vl[i30:]
    m["dvref_line_mv"] = (max(win) - min(win)) * 1e3
    m["line_reg_mv_per_v"] = (max(win) - min(win)) / 0.6 * 1e3
    m["vref_at_2p7"] = vl[0]

    # IBIAS sensitivity at 10 uA and 30 uA
    for ib in (10.0, 30.0):
        tbi = RefTB(netlist_text, CELL, supplies=dict(SUPPLIES),
                    loads={"VREF": CL},
                    workdir=os.path.join(workdir, f"ib{ib:g}"),
                    corner="typical", ibias_ua=ib)
        ri = tbi.op()
        if not ri.ok:
            raise RuntimeError(f"IBIAS={ib:g}uA op did not simulate")
        m[f"vref_i{ib:g}u"] = ri.value("VREF")
    return m


# -- measurement-directed knob moves ----------------------------------

_TRIED = {}


def _key(p):
    return tuple(round(float(p[k]), 4) for k in PKEYS)


def _evolve(design, p, note):
    p = clamp_params(p)
    return design.evolve(netlist=build_netlist(p),
                         circuit={**design.circuit, "params": p},
                         note=note)


def _report_metrics(report):
    return {r.name: r.value for r in report.results if r.value is not None}


def tune_pre(design, report):
    """One measured step toward vref ~1.20 V and slope ~0."""
    met = _report_metrics(report)
    p = dict(design.circuit.get("params") or SEED)
    step = int(design.circuit.get("_pre_step", 0)) + 1
    vref = met.get("vref_nominal") or 1.2
    slope = met.get("t_slope_mv_c") or 0.0
    lreg = met.get("line_reg_mv_per_v") or 0.0

    if lreg > 100.0:
        p["mp_l"] = min(p["mp_l"] * 1.5, 10.0)
        why = f"line-reg {lreg:.1f} mV/V -> longer mirror L"
    elif vref < 1.18 and slope <= 0.10:
        p["mb_l"] *= 1.25
        why = f"vref {vref:.3f} V low, slope {slope:+.2f} -> +triode share"
    elif vref < 1.18:
        p["mt_l"] *= 0.85
        why = f"vref {vref:.3f} V low, slope {slope:+.2f} -> MT density up"
    elif vref > 1.22 and slope >= -0.10:
        p["mb_l"] *= 0.85
        why = f"vref {vref:.3f} V high, slope {slope:+.2f} -> -triode share"
    elif vref > 1.22:
        p["mt_l"] *= 1.18
        why = f"vref {vref:.3f} V high, slope {slope:+.2f} -> MT density down"
    else:
        p["mb_l"] *= (0.90 if slope > 0 else 1.10)
        why = f"in-band; trim TC (slope {slope:+.2f} mV/C)"

    new = _evolve(design, p, f"pre_tune_{step}: {why}")
    tries = 0
    while _key(new.circuit["params"]) in _TRIED and tries < 4:
        p = dict(new.circuit["params"])
        if abs(vref - 1.20) > 0.03:
            p["mb_l"] *= (1.08 if vref < 1.20 else 0.925)
        else:
            p["mb_l"] *= (0.94 if slope > 0 else 1.06)
        new = _evolve(design, p, f"pre_tune_{step}: retry {tries+1}")
        tries += 1
    _TRIED[_key(new.circuit["params"])] = True
    print(f"[TUNE-PRE] {why}")
    return new


def tune_post(design, report, degradation):
    """PEX-aware single step: sizing trim plus layout constraints."""
    met = _report_metrics(report) if report is not None and report.results \
        else {}
    p = dict(design.circuit.get("params") or SEED)
    step = int(design.circuit.get("_pex_step", 0)) + 1
    layout = dict(design.layout or {})
    layout["critical_net_width"] = 0.28
    worst = [d.name for d in (degradation or []) if d.worsened][:3]
    if worst:
        layout["parasitic_sensitive"] = worst

    vref = met.get("vref_nominal")
    slope = met.get("t_slope_mv_c")
    why = "pex tune"
    if vref is not None and vref < 1.18:
        p["mb_l"] *= 1.12
        why = f"pex vref {vref:.3f} V low -> +triode share"
    elif vref is not None and vref > 1.22:
        p["mb_l"] *= 0.89
        why = f"pex vref {vref:.3f} V high -> -triode share"
    elif slope is not None and abs(slope) > 0.30:
        p["mb_l"] *= (0.92 if slope > 0 else 1.09)
        why = f"pex TC trim (slope {slope:+.2f} mV/C)"
    new = _evolve(design, p, f"pex_tune_{step}: {why}")
    new = new.evolve(layout=layout)
    print(f"[TUNE-POST] {why}")
    return new


# -- branch-and-compare proposer (LOOP B) ------------------------------

def propose_candidates(*, design, report, degradation, iteration,
                       baseline_score, budget):
    from mbg.specs import evaluate_specs

    met = _report_metrics(report) if report is not None else {}
    base_p = dict(design.circuit.get("params") or SEED)
    vref = met.get("vref_nominal") or 1.2
    slope = met.get("t_slope_mv_c") or 0.0

    moves = []          # (param, factor, hypothesis)
    if vref < 1.19:
        moves += [("mb_l", 1.15, "+triode share raises level"),
                  ("mt_l", 0.85, "MT density up raises VGS")]
    if vref > 1.21:
        moves += [("mb_l", 0.87, "-triode share lowers level"),
                  ("mt_l", 1.18, "MT density down lowers VGS")]
    if abs(met.get("tempco_ppm_c") or 999) >= 300 or abs(slope) > 0.25:
        f = 0.90 if slope > 0 else 1.12
        moves += [("mb_l", f, f"TC trim toward slope~0 (slope {slope:+.2f})")]
    if (met.get("line_reg_mv_per_v") or 0) > 60.0:
        moves += [("mp_l", 1.4, "longer mirror L cuts CLM feedthrough")]
    if not moves:                      # in-band polish: widen margins
        moves += [("mb_l", 0.95, "polish A"), ("mb_l", 1.05, "polish B"),
                  ("mt_nf", 1, "polish C")]

    cands, seen = [], {_key(base_p)}
    for i, (k, f, hyp) in enumerate(moves[:budget * 2]):
        p = dict(base_p)
        p[k] = float(p[k]) * f if k != "mt_nf" else max(
            1, int(p["mt_nf"]) + (2 if f > 1 else -2))
        p = clamp_params(p)
        kk = _key(p)
        if kk in seen or kk in _TRIED:
            continue
        seen.add(kk)
        cid = f"P{iteration}.{len(cands)+1}"
        cands.append(dict(id=cid, params=p, change=f"{k} x{f:g}", hyp=hyp))
        if len(cands) >= budget:
            break

    records = []
    best = None
    for c in cands:
        keep = {k: v for k, v in design.circuit.items()
                if k.startswith("_") and k != "_tag"}
        cdesign = _evolve(design, c["params"],
                          f"{c['id']}: {c['change']}").evolve(
            circuit={**keep, "params": c["params"],
                     "_tag": f"cand_{c['id']}"})
        rec = dict(id=c["id"], change=f"{c['change']} ({c['hyp']})",
                   params=c["params"])
        try:
            metrics = PROBE_SIM(cdesign)
            rep = evaluate_specs(metrics, SPECS, "cand")
            rec.update(score=rep.score, passed=rep.passed,
                       metrics={n: r.value for n, r in
                                ((s.name, s) for s in rep.results).items()
                                if r.value is not None},
                       decision="MEASURED")
            _TRIED[_key(c["params"])] = True
            if rep.score <= baseline_score and \
               (best is None or rep.score < best[0]):
                best = (rep.score, cdesign, rec)
            print(f"[SEARCH]   {c['id']} score {rep.score:.4g}"
                  + ("  PASSES ALL SPECS" if rep.passed else ""))
        except Exception as e:                                 # noqa: BLE001
            rec.update(decision="ERROR", error=str(e))
            print(f"[SEARCH]   {c['id']} error: {e}")
        records.append(rec)

    if best is None:
        return None, records
    return best[1], records


# -- wiring into /mbg-full-auto ----------------------------------------

PROBE_SIM = None          # set in main(): layout + PEX simulation of one design


def simulate_pre(design):
    tag = str(design.note or "base").replace(" ", "_")[:40] or "base"
    wd = os.path.join(OUTDIR, "pre_sim", tag)
    os.makedirs(wd, exist_ok=True)
    net = design.netlist or build_netlist(design.circuit.get("params") or SEED)
    return measure(net, wd)


def simulate_pex(design, layout):
    if not layout.pex_netlist or not os.path.isfile(layout.pex_netlist):
        raise RuntimeError("no extracted netlist to simulate")
    with open(layout.pex_netlist) as f:
        pex_text = f.read()
    tag = str(design.note or "pex").replace(" ", "_")[:40] or "pex"
    wd = os.path.join(OUTDIR, "post_sim", tag)
    os.makedirs(wd, exist_ok=True)
    return measure(pex_text, wd)


REQUEST = """Design a 1.2-V MOS-only voltage reference in GF180MCU gf180mcuD
(3.3 V devices only, no BJT/resistor/capacitor reference-setting elements).
Ports: .subckt vref_1v2 VDD VSS VREF IBIAS; IBIAS is an external 20 uA bias
current input. Nominal: VDD=3.3 V, CL=1 pF, 27 C.
Targets: vref_nominal between 1.15 and 1.25 V (nominal 1.20 V),
tempco_ppm_c <= 300 ppm/C over -40..125 C, line_reg_mv_per_v <= 100 mV/V,
dvref_line_mv <= 60 mV over 3.0..3.6 V, ivdd_uA <= 300 uA excluding IBIAS.
Characterize IBIAS at 10/20/30 uA and supply from 2.7 to 3.6 V; report PVT
at VDD 3.0/3.3/3.6 V and -40/27/125 C plus GF180 process corners."""


def main():
    global PROBE_SIM
    mh = make_hooks(cell=CELL, out_node="VREF", in_node="IBIAS",
                    supplies=SUPPLIES, spec_names=[s.name for s in SPECS],
                    specs=SPECS, outdir=OUTDIR, verbosity=1)

    def probe_sim(design):
        layout = mh.build_layout(design)
        if not layout.ok:
            raise RuntimeError(
                f"layout/verification failed: {layout.message}")
        return simulate_pex(design, layout)

    PROBE_SIM = probe_sim

    hooks = FlowHooks(simulate_pre=simulate_pre,
                      build_layout=mh.build_layout,
                      simulate_pex=simulate_pex,
                      tune_pre=tune_pre,
                      tune_post=tune_post,
                      propose_candidates=propose_candidates)

    seed = clamp_params(SEED)
    cfg = FullAutoConfig.for_effort(os.environ.get("MBG_EFFORT", "normal"),
                                    outdir=OUTDIR)
    res = run_full_auto(REQUEST, hooks, cell=CELL, specs=SPECS,
                        netlist=build_netlist(seed), config=cfg)

    print("\n" + "=" * 64)
    print(f"[RESULT] status         : {res.status}")
    print(f"[RESULT] tapeout_ready  : {res.tapeout_ready}")
    print(f"[RESULT] message        : {res.message}")
    print(f"[RESULT] report         : {res.report_path}")
    try:
        print(res.signoff.table())
    except Exception:
        pass

    summary = {
        "status": res.status,
        "tapeout_ready": bool(res.tapeout_ready),
        "message": res.message,
        "report_path": res.report_path,
        "elapsed_s": round(getattr(res, "elapsed", 0.0) or 0.0, 1),
    }
    with open(os.path.join(OUTDIR, "run_summary.json"), "w") as f:
        json.dump(summary, f, indent=2)
    return 0 if res.tapeout_ready else 1


if __name__ == "__main__":
    sys.exit(main())
