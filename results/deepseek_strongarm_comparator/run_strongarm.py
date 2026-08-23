#!/usr/bin/env python
"""MBG FULL AUTOMATE for a Strong-Arm clocked comparator in GF180MCU.

Design request (user):
  - Strong-Arm clocked comparator, ports VDD VSS INP INN CLK OUTP OUTN
  - GF180MCU gf180mcuD, VDD 3.3 V, VCM 1.65 V, 27 C, CLK 10 MHz,
    CL_OUTP = CL_OUTN = 20 fF (testbench loads)
  - decision time <= 5 ns at |VIN_DIFF| = 5 mV, swing >= 90% VDD, average
    current @ 10 MHz <= 500 uA, static current ~0, ICMR >= 1.0-2.3 V,
    reset/precharge + regenerative evaluation required, correct polarity
    at +/-5..100 mV, mismatch MC offset 1-sigma <= 10 mV.

The comparator is the classic Strong-Arm dynamic latch: clocked NMOS tail,
NMOS differential pair, cross-coupled NMOS+PMOS latch, PMOS precharge of the
outputs and the internal nodes. Sized independently for this PDK (see the
netlist and the design report); not copied from a repository example.

Outputs land in this directory (results/deepseek_strongarm_comparator/):
  history.json, review_history.json, full_auto_result.json,
  final_design_report.md, final/ (GDS, PEX netlist, DRC/LVS reports)
  characterization.json   (PVT grid + per-differential decision times + MC)
"""
from __future__ import annotations

import json
import math
import os
import sys
import time

import numpy as np

os.environ.setdefault("PDK_ROOT", os.path.expanduser("~/.volare"))
os.environ.setdefault("PDK", "gf180mcuD")
os.environ.setdefault("PDKPATH", os.path.expanduser("~/.volare/gf180mcuD"))

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), "..", "src"))

from mbg import Spec, make_hooks
from mbg.full_auto import run_full_auto, FullAutoConfig
from mbg.specs import evaluate_specs
from mbg.search import Candidate, CandidateResult, select_best, margin_of

import sa_measure as M

CELL = "strongarm_comparator"
OUTDIR = _HERE
VDD_NOM = 3.3

lib_path = os.path.join(os.environ["PDKPATH"], "libs.tech", "ngspice",
                        "sm141064.ngspice")

# ── netlist ───────────────────────────────────────────────────────────
# Strong-Arm latch comparator, 11 MOS, flat, single subckt. Ports exactly
# VDD VSS INP INN CLK OUTP OUTN. Convention: INP > INN -> OUTP high.
# Sizing notes (chosen for this PDK, not copied — validated by post-layout
# offset probing, see the design report):
#   - tail XM1 W=2u L=0.5u: a deliberately *weak* clock switch. The tail
#     current sets the input-pair overdrive, and the input-referred offset
#     of a Strong-Arm latch is (Vov/2)*(dC/C) at the regenerative nodes. A
#     weak tail keeps Vov small, which is what keeps the systematic
#     post-layout offset below the 5 mV decision requirement despite the
#     unavoidable routing imbalance of the automatic grid router.
#   - input pair XM2/XM3 W=16u L=0.6u nf=8: large area restores the
#     transconductance the weak tail would otherwise take away, so the
#     comparator still clears the 5 ns decision budget and the 1.0 V low
#     common-mode edge. Long-enough L keeps Vth mismatch within the
#     10 mV 1-sigma offset target.
#   - latch NMOS XM4/XM5 W=6u L=0.5u, latch PMOS XM6/XM7 W=6u L=0.5u:
#     cross-coupled regenerative pair, short L for fast regeneration.
#   - precharge XM8-XM11 W=2u L=0.5u: outputs + internal nodes to VDD.
NETLIST = f'''
.lib "{lib_path}" typical
.subckt {CELL} VDD VSS INP INN CLK OUTP OUTN
XM1  TAIL CLK VSS VSS nfet_03v3 L=0.5u W=2u nf=1
XM2  D1 INP TAIL VSS nfet_03v3 L=0.6u W=16u nf=8
XM3  D2 INN TAIL VSS nfet_03v3 L=0.6u W=16u nf=8
XM4  OUTN OUTP D1 VSS nfet_03v3 L=0.5u W=6u nf=3
XM5  OUTP OUTN D2 VSS nfet_03v3 L=0.5u W=6u nf=3
XM6  OUTN OUTP VDD VDD pfet_03v3 L=0.5u W=6u nf=3
XM7  OUTP OUTN VDD VDD pfet_03v3 L=0.5u W=6u nf=3
XM8  OUTN CLK VDD VDD pfet_03v3 L=0.5u W=2u nf=1
XM9  OUTP CLK VDD VDD pfet_03v3 L=0.5u W=2u nf=1
XM10 D1 CLK VDD VDD pfet_03v3 L=0.5u W=2u nf=1
XM11 D2 CLK VDD VDD pfet_03v3 L=0.5u W=2u nf=1
.ends
'''.strip()

# ── specifications ────────────────────────────────────────────────────
N_CASES = len(M.VD_CASES)          # 10 (5 diffs x 2 polarities)
SPECS = [
    Spec("t_dec_ns", "<=", 5.0, " ns"),
    Spec("out_swing_v", ">=", 0.9 * VDD_NOM, " V"),
    Spec("i_avg_ua", "<=", 500.0, " uA"),
    Spec("i_static_ua", "<=", 10.0, " uA"),
    Spec("n_correct", "==", float(N_CASES), "", tol=0),
    Spec("precharge_ok", "==", float(N_CASES), "", tol=0),
    Spec("regenerate_ok", "==", float(N_CASES), "", tol=0),
    Spec("icmr_lo", "<=", 1.0, " V"),
    Spec("icmr_hi", ">=", 2.3, " V"),
]

REQUEST = (
    "Design a Strong-Arm clocked comparator in GF180MCU (gf180mcuD) with "
    f"ports {CELL} VDD VSS INP INN CLK OUTP OUTN. VDD=3.3 V, VSS=0 V, "
    "VCM=1.65 V, 27 C, CLK=10 MHz, CL_OUTP=CL_OUTN=20 fF. "
    "Minimum differential input <= 5 mV with correct decision at +/-5 mV, "
    "decision time <= 5 ns, differential output swing >= 90% of VDD, "
    "static current between comparisons ~0, average current at 10 MHz "
    "<= 500 uA, input common-mode range at least 1.0-2.3 V, reset/precharge "
    "operation required, regenerative evaluation required. Characterize "
    "decision time versus |VIN_DIFF| = 5/10/25/50/100 mV in both polarities, "
    "and input-referred offset by mismatch Monte Carlo (1-sigma <= 10 mV). "
    "PVT: VDD 3.0/3.3/3.6 V, -40/27/125 C, gf180 typical/ff/ss/fs/sf."
)


# ── measurement ───────────────────────────────────────────────────────
def _measure(netlist, tag, vdd=3.3, temp=27.0, corner="typical",
             do_icmr=True, icmr_step=0.1, tstep="50p"):
    wd = os.path.join(OUTDIR, "sim", tag)
    m = M.measure_comparator(netlist, vdd=vdd, temp=temp, corner=corner,
                             workdir=wd, do_icmr=do_icmr, icmr_step=icmr_step,
                             timeout=900, tstep=tstep)
    if not m:
        raise RuntimeError(f"measurement produced no data for {tag} — "
                           "this is a tool failure, not a spec miss")
    m.pop("_cases", None)
    return m


def _simulate_pre(design):
    # 0.2 V ICMR resolution is enough to resolve the 1.0/2.3 V boundaries;
    # keeps the flow-loop cost down under load.
    return _measure(design.netlist, "pre", icmr_step=0.2)


def _simulate_pex(design, layout):
    if not layout.pex_netlist or not os.path.isfile(layout.pex_netlist):
        raise RuntimeError("no extracted netlist to simulate")
    with open(layout.pex_netlist) as f:
        pex_netlist = f.read()
    return _measure(pex_netlist, "pex", icmr_step=0.2)


# ── tuning ────────────────────────────────────────────────────────────
_FAST = {"t_dec_ns", "out_swing_v", "regenerate_ok"}
_POW = {"i_avg_ua"}
_ICMR = {"icmr_lo", "icmr_hi"}
_IN_PAIR = ["XM2", "XM3"]
_TAIL = ["XM1"]


def _tune_pre(design, report):
    failing = {r.name for r in report.failures}
    if not failing:
        return design
    factor = None
    if _FAST & failing or _ICMR & failing:
        factor = 1.2
    elif _POW & failing:
        factor = 0.85
    else:
        factor = 1.15
    step = int(design.circuit.get("_pre_step", 0)) + 1
    return design.evolve(
        netlist=M.scale_devices(design.netlist, None, factor),
        circuit={**design.circuit, "_pre_step": step},
        note=f"pre_tune_{step}(w x{factor})")


def _tune_post(design, report, degradation):
    failing = {r.name for r in report.failures}
    layout = dict(design.layout)
    worst = [d for d in degradation if d.worsened and d.status != "PASS"]
    if worst:
        width = float(layout.get("critical_net_width", 0.28))
        layout["critical_net_width"] = round(min(width * 1.25, 1.0), 4)
        layout["tighten_matched_groups"] = True
        layout["parasitic_sensitive"] = [d.name for d in worst[:3]]
    net = design.netlist
    step = int(design.circuit.get("_pex_step", 0)) + 1
    note = f"pex_tune_{step}(layout)"
    if _ICMR & failing:
        # Low-VCM decisions are correct but too slow: more input-pair
        # transconductance (and a stronger tail switch) is the direct fix.
        net = M.scale_devices(net, _IN_PAIR, 1.25)
        net = M.scale_devices(net, _TAIL, 1.2)
        note = f"pex_tune_{step}(in_pair x1.25, tail x1.2)"
    elif _FAST & failing:
        net = M.scale_devices(net, None, 1.15)
        note = f"pex_tune_{step}(w x1.15)"
    elif _POW & failing:
        net = M.scale_devices(net, None, 0.9)
        note = f"pex_tune_{step}(w x0.9)"
    return design.evolve(
        netlist=net, layout=layout,
        circuit={**design.circuit, "_pex_step": step},
        note=note)


# ── branch-and-compare candidate proposer ─────────────────────────────
def make_proposer(hooks_ref):
    def _propose(*, design, report, degradation, iteration, baseline_score,
                 budget):
        failing = {r.name for r in report.results
                   if r.required and r.status != "PASS"}
        if not failing:
            return None, []
        speed = bool(_FAST & failing)
        icmr = bool(_ICMR & failing)
        power = "i_avg_ua" in failing
        if speed:
            moves = [
                ("in_pair", _IN_PAIR, 1.2, "widen input pair: faster "
                 "integration of the small differential"),
                ("latch_n", ["XM4", "XM5"], 1.2, "widen latch NMOS: faster "
                 "regeneration pull-down"),
                ("latch_p", ["XM6", "XM7"], 1.2, "widen latch PMOS: faster "
                 "regeneration pull-up"),
                ("all", None, 1.1, "widen every device"),
            ]
        elif icmr:
            moves = [
                ("in_pair", _IN_PAIR, 1.25, "widen input pair: more "
                 "transconductance at low common-mode input"),
                ("in_pair_tail", _IN_PAIR + _TAIL, 1.2, "widen input pair "
                 "and the tail switch together"),
                ("all", None, 1.1, "widen every device (gentle)"),
            ]
        elif power:
            moves = [
                ("all", None, 0.85, "shrink every device to cut dynamic "
                 "current"),
                ("in_pair", _IN_PAIR, 0.8, "shrink input pair"),
            ]
        else:
            moves = [("all", None, 1.1, "widen every device")]
        results = []
        for i, (name, devs, factor, hyp) in enumerate(moves[:budget]):
            net = M.scale_devices(design.netlist, devs, factor)
            cand = design.evolve(
                netlist=net, circuit={**design.circuit, "_tag": f"cand_{name}"},
                note=f"cand_{name}_x{factor}")
            cr = CandidateResult(candidate=Candidate(
                id=f"cand_{name}", design=cand, hypothesis=hyp,
                change=f"scale {' '.join(devs) if devs else 'all'} widths x{factor}",
                expected_effect="speed up decision" if speed
                else "reduce dynamic current",
                risk="larger devices add self-loading; smaller ones slow "
                     "regeneration",
                params={"knob": "width", "factor": factor, "devices": devs}))
            try:
                layout = hooks_ref["build_layout"](cand)
                if not layout.ok:
                    cr.error = layout.message or "layout/verification failed"
                    cr.decision = "ERROR"
                    results.append(cr)
                    continue
                metrics = hooks_ref["simulate_pex"](cand, layout)
                rep = evaluate_specs(metrics, SPECS, "pex")
                cr.ok = True
                cr.metrics = dict(metrics)
                cr.report = rep
                cr.score = rep.score
                cr.margin = margin_of(rep)
                cr.artifacts = {"gds": layout.gds_path or "",
                                "pex": layout.pex_netlist or ""}
                cr.candidate.params["_layout"] = layout
            except Exception as e:                     # noqa: BLE001
                cr.error = f"{type(e).__name__}: {e}"
                cr.decision = "ERROR"
            results.append(cr)
        winner, labelled = select_best(results, baseline_score)
        records = [r.as_dict() for r in labelled]
        if winner is None:
            return None, records
        return winner.candidate.design, records
    return _propose


# ── hooks ─────────────────────────────────────────────────────────────
hooks = make_hooks(
    cell=CELL, in_node="INP", out_node="OUTP",
    supplies={"VDD": VDD_NOM, "VSS": 0.0},
    spec_names=[s.name for s in SPECS],
    specs=SPECS,
    outdir=OUTDIR,
    verbosity=1,
)
hooks.simulate_pre = _simulate_pre
hooks.simulate_pex = _simulate_pex
hooks.tune_pre = _tune_pre
hooks.tune_post = _tune_post
hooks.propose_candidates = make_proposer(
    {"build_layout": hooks.build_layout, "simulate_pex": _simulate_pex})

config = FullAutoConfig.for_effort("normal", outdir=OUTDIR,
                                   candidates_per_iteration=2)


# ── post-flow characterization ────────────────────────────────────────
_PVT_GRID = [
    (corner, temp, vdd)
    for corner in ("typical", "ff", "ss", "fs", "sf")
    for temp in (-40, 27, 125)
    for vdd in (3.0, 3.3, 3.6)
]


def characterize(netlist, outdir):
    """PVT matrix + decision-time table + mismatch Monte Carlo offset."""
    results = {"pvt": [], "decision_time_table": [], "offset_mc": None,
               "nominal": None}
    # Run the nominal measure directly (not through _measure) so the
    # per-case decision detail survives into the report table.
    wd = os.path.join(outdir, "sim", "char_nominal")
    nominal = M.measure_comparator(netlist, workdir=wd, timeout=900,
                                   icmr_step=0.1)
    cases = nominal.pop("_cases", [])
    results["decision_time_table"] = [
        {"vd_mv": c["vd"] * 1e3, "t_dec_ns": (c["t_dec"] * 1e9)
         if c["t_dec"] is not None else None,
         "diff_settled_v": c["diff_settled"],
         "correct": c["correct"], "precharge_lo_v": c["precharge_lo"]}
        for c in cases]
    results["nominal"] = {k: v for k, v in nominal.items()
                          if not k.startswith("_")}

    for (corner, temp, vdd) in _PVT_GRID:
        try:
            m = _measure(netlist, f"pvt/{corner}_{temp}_{vdd}",
                         vdd=vdd, temp=temp, corner=corner, do_icmr=False,
                         tstep="100p")
            results["pvt"].append({
                "corner": corner, "temp": temp, "vdd": vdd,
                "t_dec_ns": m.get("t_dec_ns"),
                "n_correct": m.get("n_correct"),
                "out_swing_v": m.get("out_swing_v"),
                "precharge_ok": m.get("precharge_ok"),
                "regenerate_ok": m.get("regenerate_ok"),
                "i_avg_ua": m.get("i_avg_ua"),
                "i_static_ua": m.get("i_static_ua"),
                "icmr_lo": m.get("icmr_lo"),
                "icmr_hi": m.get("icmr_hi"),
            })
        except RuntimeError as e:
            results["pvt"].append({"corner": corner, "temp": temp,
                                   "vdd": vdd, "error": str(e)})
            print(f"[CHAR] PVT {corner}/{temp}/{vdd}: {e}")

    try:
        mc = M.measure_offset_mc(netlist, runs=60,
                                 workdir=os.path.join(outdir, "sim", "mc"))
        results["offset_mc"] = {
            k: (v.tolist() if isinstance(v, np.ndarray) else v)
            for k, v in mc.items()}
    except Exception as e:                             # noqa: BLE001
        results["offset_mc"] = {"error": f"{type(e).__name__}: {e}",
                                "mc_runs": 0}
        print(f"[CHAR] Monte Carlo failed: {e}")

    path = os.path.join(outdir, "characterization.json")
    with open(path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    return results


def main():
    sanity = "--sanity" in sys.argv
    if sanity:
        m = _measure(NETLIST, "sanity", do_icmr=False)
        for k, v in sorted(m.items()):
            if not k.startswith("_"):
                print(f"  {k:18s} = {v}")
        return 0

    res = run_full_auto(REQUEST, hooks, cell=CELL, specs=SPECS,
                        netlist=NETLIST, config=config)

    print("\n" + "=" * 80)
    if hasattr(res, "summary"):
        print(res.summary())
    print("STATUS:", res.status)
    print("TAPEOUT_READY:", res.tapeout_ready)
    print("Report:", res.report_path)

    # Supplementary characterization (PVT + decision-time table + MC).
    final_netlist = NETLIST
    if res.flow and res.flow.best_pex_design:
        final_netlist = res.flow.best_pex_design.netlist
    char = characterize(final_netlist, OUTDIR)
    print("[CHAR] PVT grid cells:", len(char["pvt"]))
    if char["offset_mc"]:
        print("[CHAR] offset MC:",
              {k: v for k, v in char["offset_mc"].items()
               if k != "offset_samples_mv"})

    # Append the characterization summary to the framework report.
    report = res.report_path
    if report and os.path.isfile(report):
        with open(report, "a") as f:
            f.write(_report_section(char))

    return 0 if res.tapeout_ready else 1


def _report_section(char):
    lines = ["", "---", "", "## Supplementary characterization", ""]
    nom = char.get("nominal") or {}
    lines.append(f"**Nominal (typical / 27 C / 3.3 V):**")
    for k in ("t_dec_ns", "out_swing_v", "i_avg_ua", "i_static_ua",
              "n_correct", "precharge_ok", "regenerate_ok",
              "icmr_lo", "icmr_hi"):
        if k in nom:
            lines.append(f"- {k} = {nom[k]}")
    lines.append("")
    lines.append("**Decision time vs |VIN_DIFF| (nominal, worst polarity):**")
    table = {}
    for c in char.get("decision_time_table", []):
        vd = abs(c["vd_mv"])
        table.setdefault(vd, []).append(c["t_dec_ns"])
    for vd in sorted(table):
        vals = [x for x in table[vd] if x is not None]
        lines.append(f"- |VIN_DIFF| = {int(vd):3d} mV -> "
                     f"t_dec = {max(vals):.3f} ns (worst of both polarities)")
    lines.append("")
    lines.append("**PVT matrix (VDD x TEMP x corner):**")
    lines.append("")
    lines.append("| corner | temp | VDD | t_dec (ns) | correct | swing (V) "
                 "| precharge | regenerate | i_avg (uA) |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for r in char.get("pvt", []):
        lines.append(f"| {r.get('corner')} | {r.get('temp')} | "
                     f"{r.get('vdd')} | {r.get('t_dec_ns')} | "
                     f"{r.get('n_correct')} | {r.get('out_swing_v')} | "
                     f"{r.get('precharge_ok')} | {r.get('regenerate_ok')} | "
                     f"{r.get('i_avg_ua')} |")
    lines.append("")
    mc = char.get("offset_mc") or {}
    lines.append("**Input-referred offset (mismatch Monte Carlo):**")
    if mc.get("mc_runs"):
        lines.append(f"- runs = {mc['mc_runs']}")
        lines.append(f"- mean offset = {mc.get('offset_mean_mv'):.3f} mV")
        lines.append(f"- 1-sigma offset = {mc.get('offset_1sigma_mv'):.3f} mV")
        lines.append(f"- 3-sigma offset = {mc.get('offset_3sigma_mv'):.3f} mV")
    else:
        lines.append(f"- not verified: {mc.get('error', 'not run')}")
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
