"""Driver: /mbg-full-auto for the ox-alpha OTA on gf180mcuD.

Run from $MBG_ROOT with the MBG venv python:
    cd $MBG_ROOT && $MBG_VENV/bin/python /tmp/opencode/ox_alpha/run_flow.py
"""
from __future__ import annotations

import itertools
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ota_design import DEFAULT_PARAMS, build_netlist, build_specs, measure

from mbg.flow import DesignPoint
from mbg.flow_runtime import make_hooks, make_candidate_proposer
from mbg.full_auto import run_full_auto, FullAutoConfig
from mbg.search import Candidate

OUTDIR = "results/ox_alpha_ota"
CELL = "ota"

REQUEST = """Design an Operational Transconductance Amplifier (OTA) using the
Microelectronic-Block-Generator framework with the GF180MCU gf180mcuD PDK.
Ports: VDD VSS INP INN OUT IBIAS. IBIAS is an external bias current input.
VDD = 3.3 V, VSS = 0 V, nfet_03v3 / pfet_03v3. Nominal: VDD=3.3 V,
IBIAS=20 uA, VIN_CM=1.65 V, CL=5 pF, TEMP=27 C.
Specifications: DC gain >= 35 dB; GBW >= 1 MHz; phase margin >= 60 deg;
rising slew rate >= 0.5 V/us; falling slew rate >= 0.5 V/us;
supply current excluding IBIAS <= 250 uA; output DC at zero differential
input = 1.65 V +/- 0.5 V; usable output swing >= 0.5-2.8 V; load 5 pF.
Also characterize CMRR, PSRR, input common-mode range, power, noise and
offset where supported. PVT: VDD = 3.0/3.3/3.6 V, TEMP = -40/27/125 C and
GF180 process corners."""

_specs = build_specs()
_spec_names = [s.name for s in _specs]

hooks = make_hooks(cell=CELL, in_node="inp", out_node="out",
                   supplies={"vdd": 3.3, "vss": 0.0},
                   spec_names=_spec_names, specs=_specs,
                   outdir=OUTDIR, verbosity=1)

_sim_counter = itertools.count()


def _sim(netlist_text: str) -> dict:
    n = next(_sim_counter)
    wd = os.path.join(OUTDIR, "sims", f"m{n:04d}")
    return measure(netlist_text, CELL, wd)


def _legalize(q: dict) -> dict:
    q = dict(q)
    q.setdefault("nf_bias", 1)
    q.setdefault("nf_tail", 1)
    q.setdefault("nf_pair", 1)
    q.setdefault("nf_mir", 1)
    for key in ("w_bias", "w_tail", "w_pair", "w_mir"):
        w, nf_key = q[key], "nf_" + key.split("_")[1]
        while w / max(1, q[nf_key]) > 9.5:
            q[nf_key] += 1
        if q[f"l_{key.split('_')[1]}"] >= 10 or w > 200:
            raise ValueError(f"{key} out of GF180 limits after edit")
    return q


def _mk_design(params: dict, note: str) -> DesignPoint:
    params = _legalize(params)
    return DesignPoint(cell=CELL, netlist=build_netlist(params),
                       circuit=dict(params), layout={}, note=note)


def next_edits(p: dict, report) -> list:
    """Single-edit moves, most important first. Each is one hypothesis."""
    edits = []

    def add(tag, desc, **kv):
        q = {**p, **kv}
        if any(abs(float(q[k]) - float(p[k])) < 1e-9 for k in kv):
            return
        try:
            _legalize(q)
        except ValueError:
            return
        edits.append((tag, desc, kv))

    res = {r.name: r for r in report.results}
    od = res.get("out_dc")
    if od is not None and od.status == "FAIL" and od.value is not None:
        if od.value > 1.65:
            add("mir_shrink", "raise |Vov_p| to pull OUT_DC toward 1.65",
                w_mir=round(p["w_mir"] * 0.8, 2))
        else:
            add("mir_grow", "lower |Vov_p| to lift OUT_DC toward 1.65",
                w_mir=round(p["w_mir"] * 1.25, 2))

    failing = {r.name for r in report.failures}
    if "gain_db" in failing:
        add("l_mir_up", "longer mirror L raises ro_out and gain",
            l_mir=min(p["l_mir"] + 1.0, 8.0))
        add("l_pair_up", "longer pair L raises ro2 and gain",
            l_pair=min(p["l_pair"] + 1.0, 5.0))
    if {"ugf_hz", "bw_hz"} & failing:
        add("i_up_ugf", "more tail current raises gm and GBW",
            w_tail=min(round(p["w_tail"] * 1.3, 2), 28.0))
        add("pair_wide", "wider pair raises gm at same current",
            w_pair=min(round(p["w_pair"] * 1.3, 2), 36.0))
    if "pm_deg" in failing:
        add("i_dn_pm", "less tail current lowers UGF vs parasitic poles",
            w_tail=max(round(p["w_tail"] * 0.85, 2), 4.0))
    if {"sr_rise_vus", "sr_fall_vus"} & failing:
        add("i_up_sr", "more tail current raises slew rate",
            w_tail=min(round(p["w_tail"] * 1.4, 2), 28.0))
    if "idd_ua" in failing:
        add("i_dn_idd", "trim tail current to meet supply budget",
            w_tail=max(round(p["w_tail"] * 0.8, 2), 4.0))
    return edits


def tune_pre(design: DesignPoint, report) -> DesignPoint:
    edits = next_edits(design.circuit, report)
    if not edits:
        return design
    tag, desc, kv = edits[0]
    print(f"[TUNE-PRE] {tag}: {desc} {kv}")
    return design.evolve(
        netlist=build_netlist({**design.circuit, **kv}),
        circuit={**design.circuit, **kv},
        note=f"pre_{tag}")


def tune_post(design: DesignPoint, report, degradation) -> DesignPoint:
    edits = next_edits(design.circuit, report)
    layout = dict(design.layout)
    width = float(layout.get("critical_net_width", 0.28))
    worst = [d for d in degradation if d.worsened and d.status != "PASS"]
    if worst:
        layout["critical_net_width"] = round(min(width * 1.25, 1.0), 4)
        layout["tighten_matched_groups"] = True
        layout["parasitic_sensitive"] = [d.name for d in worst[:3]]
    if not edits:
        return design.evolve(layout=layout) if layout != design.layout else design
    tag, desc, kv = edits[0]
    print(f"[TUNE-POST] {tag}: {desc} {kv}")
    return design.evolve(
        netlist=build_netlist({**design.circuit, **kv}),
        circuit={**design.circuit, **kv}, layout=layout,
        note=f"pex_{tag}")


class OtaStrategy:
    """Branch-and-compare over designer knobs: distinct single edits."""
    name = "ota_designer"

    def propose(self, state, budget):
        cands = []
        seen = set()
        for tag, desc, kv in next_edits(state.design.circuit, state.report):
            change = f"{tag}:{kv}"
            if change in seen or state.memory.exhausted(change):
                continue
            seen.add(change)
            d = state.design.evolve(
                netlist=build_netlist({**state.design.circuit, **kv}),
                circuit={**state.design.circuit, **kv},
                note=f"cand_{tag}")
            cands.append(Candidate(
                id=f"{state.iteration}_{tag}", design=d, hypothesis=desc,
                change=json.dumps(kv), rationale=desc,
                expected_effect="improve the failing metric without "
                                "trading away a passing one",
                risk="interlocked knobs (W/L of the mirror moves OUT_DC)",
                target="circuit", params={"knob": tag},
                source=self.name))
            if len(cands) >= budget:
                break
        return cands


# replace the bundled simulate hooks with the OTA measurement suite
hooks.simulate_pre = lambda design: _sim(design.netlist)
hooks.simulate_pex = lambda design, layout: measure(
    open(layout.pex_netlist).read(), CELL,
    os.path.join(OUTDIR, "sims", f"pex_{next(_sim_counter):04d}"),
    quick=False)

hooks.tune_pre = tune_pre
hooks.tune_post = tune_post

proposer = make_candidate_proposer(
    specs=_specs,
    hooks_ref={"build_layout": hooks.build_layout,
               "simulate_pex": hooks.simulate_pex},
    strategy=OtaStrategy(), verbosity=1)
hooks.propose_candidates = proposer

if __name__ == "__main__":
    initial = _mk_design(DEFAULT_PARAMS, "initial")
    cfg = FullAutoConfig.for_effort("normal", outdir=OUTDIR)
    res = run_full_auto(REQUEST, hooks, cell=CELL, specs=_specs,
                        netlist=initial.netlist, config=cfg)
    print("\n=== RESULT ===")
    print("status:", res.status)
    print("tapeout_ready:", res.tapeout_ready)
    if res.signoff is not None:
        print(res.signoff.table())
    print("report:", res.report_path)
    sys.exit(0)
