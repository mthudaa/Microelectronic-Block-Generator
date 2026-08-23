"""Drive /mbg-full-auto for the self-starting ring oscillator (ox-alpha run).

Run from the repository root:
    cd "$MBG_ROOT" && python3 results/ox_alpha_oscillator/run_full_auto.py

The bundled mbg.flow_runtime.simulate_netlist measures small-signal AC
metrics; this run monkeypatches it so every pre-layout and PEX simulation
measures oscillator behaviour instead (frequency, duty cycle, swing levels,
startup time, average supply current, sustained cycles).
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.environ.get("MBG_ROOT") or os.path.abspath(
    os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(REPO, "src"))
sys.path.insert(0, HERE)

import mbg.flow_runtime as fr
from osc_sim import (simulate_osc_netlist, scale_device_lengths,
                     scale_pmos_widths)
from osc_design import oscillator_netlist

OUTDIR = os.path.join(RESULTS := HERE, "")  # results dir == this file's dir


# ── measurement override ──────────────────────────────────────────────

def _measure(netlist, cell, spec_names, **kw):
    return simulate_osc_netlist(netlist, cell, spec_names,
                                workdir=os.path.join(HERE, "simwork"))


fr.simulate_netlist = _measure


# ── specifications (exactly the user's targets) ───────────────────────

from mbg import Spec

SPECS = [
    Spec("freq_hz", ">=", 10e6, " Hz"),
    Spec("freq_hz", "<=", 100e6, " Hz"),
    Spec("startup_time_s", "<=", 5e-6, " s"),
    Spec("duty_cycle_pct", ">=", 40.0, " %"),
    Spec("duty_cycle_pct", "<=", 60.0, " %"),
    Spec("volt_high_v", ">=", 2.97, " V"),
    Spec("volt_low_v", "<=", 0.33, " V"),
    Spec("i_avg_a", "<=", 1e-3, " A"),
    Spec("cycles_sustained", ">=", 100.0, ""),
]


# ── oscillator-aware tuners ───────────────────────────────────────────

def _apply_moves(netlist, moves):
    net = netlist
    ls = ws = 1.0
    for kind, factor in moves:
        if kind == "L":
            net = scale_device_lengths(net, factor)
            ls *= factor
        else:
            net = scale_pmos_widths(net, factor)
            ws *= factor
    return net, ls, ws


def tune_osc(design, report, prefix):
    failing = {r.name for r in report.failures}
    vals = {r.name: r.value for r in report.results if r.value is not None}
    moves = []
    if "freq_hz" in failing and vals.get("freq_hz") is not None:
        if vals["freq_hz"] > 100e6:
            moves.append(("L", 1.25))
        elif vals["freq_hz"] < 10e6:
            moves.append(("L", 0.8))
    if "duty_cycle_pct" in failing and vals.get("duty_cycle_pct") is not None:
        moves.append(("WP", 1.15 if vals["duty_cycle_pct"] < 50.0 else 0.87))
    step = int(design.circuit.get(f"_{prefix}_step", 0)) + 1
    circ = {**design.circuit, f"_{prefix}_step": step}
    note = f"{prefix}_tune_{step}"
    if not moves:
        return design.evolve(note=note + "(no move)")
    net, ls, ws = _apply_moves(design.netlist, moves)
    circ["l_scale"] = round(float(circ.get("l_scale", 1.0)) * ls, 6)
    circ["wp_scale"] = round(float(circ.get("wp_scale", 1.0)) * ws, 6)
    note += "(" + ",".join(f"{k}x{f:g}" for k, f in moves) + ")"
    return design.evolve(netlist=net, circuit=circ, note=note)


def tune_pre(design, report):
    return tune_osc(design, report, "pre")


def tune_post(design, report, degradation):
    layout = dict(design.layout)
    width = float(layout.get("critical_net_width", 0.28))
    layout["critical_net_width"] = round(min(width * 1.25, 1.0), 4)
    layout["tighten_matched_groups"] = True
    worst = [d.name for d in degradation if d.worsened][:3]
    if worst:
        layout["parasitic_sensitive"] = worst
    stepped = tune_osc(design, report, "pex")
    return stepped.evolve(layout={**layout, **stepped.layout})


# ── branch-and-compare strategy (LOOP B) ──────────────────────────────

def make_osc_strategy():
    from mbg.search import SearchStrategy, Candidate

    class OscStrategy(SearchStrategy):
        name = "oscillator"

        def propose(self, state, budget):
            failing = set(state.failing())
            m = state.metrics
            out = []
            n = len(out)

            def add(cid, factor, knob="L", hyp="", risk=""):
                nonlocal n
                if len(out) >= budget:
                    return
                n += 1
                if knob == "L":
                    net = scale_device_lengths(state.design.netlist, factor)
                    circ = {**state.design.circuit,
                            "l_scale": round(float(
                                state.design.circuit.get("l_scale", 1.0))
                                * factor, 6)}
                    change = f"scale channel lengths x{factor:g}"
                else:
                    net = scale_pmos_widths(state.design.netlist, factor)
                    circ = {**state.design.circuit,
                            "wp_scale": round(float(
                                state.design.circuit.get("wp_scale", 1.0))
                                * factor, 6)}
                    change = f"scale PMOS widths x{factor:g}"
                out.append(Candidate(
                    id=cid, design=state.design.evolve(netlist=net,
                                                       circuit=circ),
                    hypothesis=hyp or change, change=change,
                    rationale="ring delay tracks L (quadratic) and Wp/Wn "
                              "ratio sets the trip point",
                    expected_effect="move freq_hz toward the 10-100 MHz "
                                    "window / recentre duty",
                    risk=risk or "overshoot past the opposite bound",
                    target="circuit",
                    params={"knob": knob, "factor": factor}, source=self.name))

            f = m.get("freq_hz")
            if f is not None and ("freq_hz" in failing or True):
                # always offer frequency-direction moves; cheap and measurable
                if f > 55e6:
                    add("up_L_s", 1.15, hyp="slow the ring slightly")
                    add("up_L_l", 1.35, hyp="slow the ring substantially")
                elif f < 30e6:
                    add("dn_L_s", 0.85, hyp="speed the ring up")
                    add("dn_L_l", 0.7, hyp="speed the ring up strongly")
                else:
                    add("trim_L_u", 1.08, hyp="small slowdown, margin gain")
                    add("trim_L_d", 0.92, hyp="small speedup, margin gain")
            if "duty_cycle_pct" in failing:
                d = m.get("duty_cycle_pct") or 50.0
                add("wp_up", 1.18, knob="WP",
                    hyp="shift trip point, widen high time" if d < 50
                    else "shift trip point, narrow high time")
                add("wp_dn", 0.85, knob="WP",
                    hyp="counter-move for duty margin")
            return out[:budget]

    return OscStrategy()


# ── main ──────────────────────────────────────────────────────────────

def main():
    from mbg.full_auto import run_full_auto, FullAutoConfig
    from mbg import make_hooks
    from mbg.flow_runtime import make_candidate_proposer

    cell = "oscillator"
    netlist = oscillator_netlist()
    with open(os.path.join(HERE, "prompt.txt")) as f:
        request = f.read()
    with open(os.path.join(HERE, "generated_netlist.spice"), "w") as f:
        f.write(netlist)

    hooks = make_hooks(cell=cell, in_node="OSC_OUT", out_node="OSC_OUT",
                       supplies={"vdd": 3.3, "vss": 0.0},
                       spec_names=[s.name for s in SPECS],
                       specs=SPECS,
                       outdir=OUTDIR, verbosity=1,
                       tune_pre=tune_pre, tune_post=tune_post)
    hooks.propose_candidates = make_candidate_proposer(
        specs=SPECS,
        hooks_ref={"build_layout": hooks.build_layout,
                   "simulate_pex": hooks.simulate_pex},
        strategy=make_osc_strategy(), verbosity=1)

    t0 = time.time()
    res = run_full_auto(request, hooks, cell=cell, specs=SPECS,
                        netlist=netlist,
                        config=FullAutoConfig.for_effort(
                            "normal", outdir=OUTDIR))
    print("\n=== FULL AUTO RESULT ===")
    print("status:", res.status, "| tapeout_ready:", res.tapeout_ready)
    print("elapsed:", round(time.time() - t0, 1), "s")
    if res.signoff:
        print(res.signoff.table())
    if res.flow and res.flow.best_pex:
        bp = res.flow.best_pex
        print("\nbest PEX metrics:")
        for r in bp.results:
            v = "MISSING" if r.value is None else (
                f"{r.value:.4g}" if isinstance(r.value, float) else str(r.value))
            print(f"  {r.name:<20} {v:<12} {r.op} {r.target:<10g} -> {r.status}")
    if res.report_path:
        print("report:", res.report_path)
    with open(os.path.join(HERE, "full_auto_run_summary.json"), "w") as f:
        json.dump(res.as_dict(), f, indent=2, default=str)
    return 0 if res.tapeout_ready else 1


if __name__ == "__main__":
    sys.exit(main())
