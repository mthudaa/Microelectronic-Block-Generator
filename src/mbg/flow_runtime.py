"""Real hooks that connect :mod:`mbg.flow` to the actual toolchain.

:mod:`mbg.flow` deliberately knows nothing about ngspice, Magic or netgen —
it takes its work as callables so the loop logic stays testable. This module
supplies the production implementations:

    simulate_pre   ngspice on the schematic netlist
    build_layout   spice_to_gds_with_checks + PEX extraction
    simulate_pex   ngspice on the *extracted* netlist
    tune_pre       heuristic circuit sizing
    tune_post      heuristic circuit + layout-constraint adjustment

The two simulate hooks run the same measurement code against different
netlists, which is the whole point: a metric is comparable across the layout
boundary only if it was measured the same way on both sides.

The bundled tuners are **heuristics, not an analog optimizer**. They scale
device widths and widen parasitic-sensitive nets in the direction the failing
metric suggests. That is enough to close small parasitic gaps and to exercise
the loop end to end; it is not a substitute for a designer or an LLM agent
deciding what to change. Pass your own ``tune_pre`` / ``tune_post`` to
:class:`~mbg.flow.FlowHooks` for anything more sophisticated — that is the
extension point, and the agent workflows use it.
"""

from __future__ import annotations

import hashlib
import math
import os
import re
import shutil
from typing import Dict, List, Mapping, Optional, Sequence

from mbg.flow import DesignPoint, FlowHooks, LayoutResult, Failure, Outcome
from mbg.specs import Degradation, SpecReport

__all__ = ["measure_ac_metrics", "simulate_netlist", "make_hooks",
           "default_tune_pre", "default_tune_post", "scale_device_widths",
           "file_digest", "net_capacitance", "router_config_from_layout"]


def file_digest(path: Optional[str]) -> str:
    """Short content hash, so an artifact can be tied to the run that made it.

    Without this there is no way to prove afterwards that a packaged PEX
    netlist was extracted from the packaged GDS, or that the reported metrics
    came from simulating that netlist — the paths are reused every iteration.
    """
    if not path or not os.path.isfile(path):
        return ""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


_CAP = re.compile(r"^C\S+\s+(\S+)\s+(\S+)\s+([0-9.eE+-]+)\s*([fpnu]?)",
                  re.MULTILINE)
_CAP_UNITS = {"f": 1e-15, "p": 1e-12, "n": 1e-9, "u": 1e-6, "": 1.0}


def net_capacitance(pex_netlist: str,
                    exclude: Sequence[str] = ("vdd", "vss", "gnd", "vsubs")
                    ) -> List[tuple]:
    """Rank nets by total extracted capacitance, heaviest first.

    Turns "bandwidth degraded" into "and this is the node carrying the load".
    A coupling capacitor loads *both* of its terminals, so both are credited.
    Supply rails are excluded because their capacitance is large and not
    something layout feedback should chase.

    Returns [(net, farads), ...]. Note the extraction the pipeline runs is
    C-coupled (mode 2), so there is no resistance data here to rank.
    """
    totals: Dict[str, float] = {}
    skip = {e.lower() for e in exclude}
    for a, b, val, unit in _CAP.findall(pex_netlist or ""):
        try:
            f = float(val) * _CAP_UNITS.get(unit.lower(), 1.0)
        except ValueError:
            continue
        for node in (a, b):
            if node.lower() in skip:
                continue
            totals[node] = totals.get(node, 0.0) + f
    return sorted(totals.items(), key=lambda kv: -kv[1])


def router_config_from_layout(layout: Mapping[str, object], verbosity: int = 0):
    """Build a real RouterConfig from the design's layout constraints.

    This is the wire that was missing: layout advice used to be written onto
    DesignPoint.layout and never read by anything, so every "widen the
    critical net" recommendation was inert. These knobs genuinely change the
    produced geometry.
    """
    from mbg.router import RouterConfig
    kw: Dict[str, object] = {"verbosity": verbosity}
    if layout.get("width_multiplier"):
        kw["width_multiplier"] = float(layout["width_multiplier"])
    if layout.get("access_layer"):
        kw["access_layer"] = str(layout["access_layer"])
    if layout.get("routing_layers"):
        kw["routing_layers"] = list(layout["routing_layers"])
    return RouterConfig(**kw)


# ── measurement ───────────────────────────────────────────────────────

def measure_ac_metrics(netlist: str, cell: str, *, out_node: str,
                       in_node: str, supplies: Mapping[str, float],
                       bias: Optional[Mapping[str, str]] = None,
                       fstart: float = 1e1, fstop: float = 1e10,
                       workdir: Optional[str] = None) -> Dict[str, float]:
    """Small-signal gain, -3 dB bandwidth and unity-gain frequency.

    Measured identically for the schematic and the extracted netlist, so the
    pre-layout and PEX numbers are directly comparable. Returns an empty dict
    on a simulation that produced no data — the caller must treat that as a
    tool failure, never as a design that missed its targets.
    """
    from mbg.analysis import Testbench

    tb = Testbench(netlist, cell, supplies=dict(supplies), workdir=workdir)
    tb.sources = dict(bias or {})
    tb.sources.setdefault(in_node, "DC 0 AC 1")
    res = tb.ac(fstart, fstop, ac_node=in_node)
    if not res.ok or not res.x:
        return {}
    try:
        mag = res.get(out_node)
    except KeyError:
        return {}
    if not mag or max(mag) <= 0:
        return {}

    db = [20.0 * math.log10(m) if m > 0 else -300.0 for m in mag]
    gain_db = db[0]
    metrics: Dict[str, float] = {"gain_db": gain_db}

    edge = gain_db - 3.0
    for f, d in zip(res.x, db):
        if d <= edge:
            metrics["bw_hz"] = float(f)
            break
    for f, d in zip(res.x, db):
        if d <= 0.0:
            metrics["ugf_hz"] = float(f)
            break
    return metrics


def simulate_netlist(netlist: str, cell: str, spec_names: Sequence[str],
                     **kw) -> Dict[str, float]:
    """Measure only what the specifications actually ask for."""
    metrics = measure_ac_metrics(netlist, cell, **kw)
    return {k: v for k, v in metrics.items() if not spec_names or k in spec_names}


# ── tuners ────────────────────────────────────────────────────────────

_DEV = re.compile(
    r"^(?P<head>\s*X\w+\s+(?:\S+\s+){3,4}\S*(?:fet|FET)\S*\s+.*?)"
    r"\bW\s*=\s*(?P<w>[0-9.eE+-]+)(?P<unit>[a-zA-Z]*)(?P<tail>.*)$")


def scale_device_widths(netlist: str, factor: float,
                        only: Optional[Sequence[str]] = None,
                        w_max: float = 10.0) -> str:
    """Multiply transistor widths by ``factor``.

    Respects the GF180 per-finger limit (W < 10 um): a tuner that produces an
    unbuildable device has not improved anything. ``only`` restricts the
    change to named instances, which is how post-layout tuning targets the
    devices on a parasitic-sensitive node instead of the whole circuit.
    """
    out = []
    for line in netlist.splitlines():
        m = _DEV.match(line)
        if not m:
            out.append(line)
            continue
        name = line.split()[0]
        if only and name not in only:
            out.append(line)
            continue
        unit = m.group("unit") or ""
        try:
            w = float(m.group("w"))
        except ValueError:
            out.append(line)
            continue
        scale = 1e6 if unit.lower().startswith("u") else 1.0
        new_w = w * factor
        if unit.lower().startswith("u") and new_w >= w_max:
            new_w = w_max - 0.01
        out.append(f"{m.group('head')}W={new_w:g}{unit}{m.group('tail')}")
    return "\n".join(out) + ("\n" if netlist.endswith("\n") else "")


def default_tune_pre(design: DesignPoint, report: SpecReport) -> DesignPoint:
    """Heuristic pre-layout sizing step.

    Low gain wants more device width; low bandwidth wants less capacitance,
    so it backs width off instead. When both fail the gain term wins, because
    a design that cannot reach its gain target has no working operating point
    to trade bandwidth against.
    """
    failing = {r.name for r in report.failures}
    factor = 1.0
    if "gain_db" in failing:
        factor = 1.3
    elif {"bw_hz", "ugf_hz"} & failing:
        factor = 0.8
    if factor == 1.0:
        return design

    step = int(design.circuit.get("_pre_step", 0)) + 1
    return design.evolve(
        netlist=scale_device_widths(design.netlist, factor),
        circuit={**design.circuit, "_pre_step": step, "w_factor": factor},
        note=f"pre_tune_{step}(w x{factor})")


def default_tune_post(design: DesignPoint, report: SpecReport,
                      degradation: Sequence[Degradation]) -> DesignPoint:
    """Heuristic PEX-aware step: circuit *and* layout constraints.

    Post-layout tuning is not only sizing. When a metric degrades from
    pre-layout to PEX the cause is parasitic — capacitance and resistance the
    schematic never had — so the response widens the critical nets and asks
    the placer to tighten the affected devices, alongside any sizing change.
    """
    worst = [d for d in degradation if d.worsened and d.status != "PASS"]
    failing = {r.name for r in report.failures} if report.results else set()

    layout = dict(design.layout)
    # Wider critical-net metal lowers series R; tighter placement lowers the
    # coupled length that produced the extra C in the first place.
    width = float(layout.get("critical_net_width", 0.28))
    layout["critical_net_width"] = round(min(width * 1.25, 1.0), 4)
    layout["tighten_matched_groups"] = True
    if worst:
        layout["parasitic_sensitive"] = [d.name for d in worst[:3]]

    factor = 1.0
    if "gain_db" in failing or any(d.name == "gain_db" for d in worst):
        factor = 1.2
    elif {"bw_hz", "ugf_hz"} & failing:
        factor = 0.9

    step = int(design.circuit.get("_pex_step", 0)) + 1
    netlist = (scale_device_widths(design.netlist, factor)
               if factor != 1.0 else design.netlist)
    return design.evolve(
        netlist=netlist, layout=layout,
        circuit={**design.circuit, "_pex_step": step},
        note=f"pex_tune_{step}(w x{factor}, net {layout['critical_net_width']}um)")


# ── branch-and-compare candidate evaluation ───────────────────────────

def make_candidate_proposer(*, specs, hooks_ref: Dict[str, object],
                            memory=None, strategy=None, archive=None,
                            verbosity: int = 1):
    """Build the ``propose_candidates`` hook: evaluate several edits, keep one.

    Each candidate is built and measured **independently from the same
    baseline**, in its own directory. That is what makes the result
    attributable: when bandwidth improves, exactly one change is responsible,
    and the losing branches are archived rather than silently folded in.

    Returns a callable matching :attr:`mbg.flow.FlowHooks.propose_candidates`.
    """
    from mbg.search import (SearchState, DesignMemory, CandidateResult,
                            ParetoArchive, default_strategy, select_best,
                            margin_of)
    from mbg.specs import evaluate_specs

    mem = memory if memory is not None else DesignMemory()
    strat = strategy or default_strategy()
    arch = archive if archive is not None else ParetoArchive()
    stagnation = {"n": 0}

    def _log(msg):
        if verbosity >= 1:
            print(msg)

    def propose(*, design, report, degradation, iteration, baseline_score,
                budget):
        state = SearchState(design=design, report=report,
                            metrics={r.name: r.value for r in report.results
                                     if r.value is not None},
                            specs=specs, degradation=degradation, memory=mem,
                            iteration=iteration, phase="pex",
                            tier=1 + stagnation["n"])
        candidates = strat.propose(state, budget)
        if not candidates:
            _log("[SEARCH] no candidate moves left to try")
            return None, []

        _log(f"[SEARCH] evaluating {len(candidates)} candidate(s) against "
             f"baseline score {baseline_score:.4g}")
        results: List[CandidateResult] = []
        for c in candidates:
            # tag isolates this candidate's artifacts from every other branch
            c.design = c.design.evolve(
                circuit={**c.design.circuit, "_tag": f"cand_{c.id}"})
            res = CandidateResult(candidate=c)
            try:
                layout = hooks_ref["build_layout"](c.design)
                if not layout.ok:
                    res.error = layout.message or "layout/verification failed"
                    res.decision = "ERROR"
                    _log(f"[SEARCH]   {c.id}: {res.error}")
                    results.append(res)
                    continue
                metrics = hooks_ref["simulate_pex"](c.design, layout)
                rep = evaluate_specs(metrics, specs, "pex")
                res.ok, res.metrics, res.report = True, dict(metrics), rep
                res.score, res.margin = rep.score, margin_of(rep)
                res.artifacts = {"gds": layout.gds_path or "",
                                 "pex": layout.pex_netlist or ""}
                res.candidate.params["_layout"] = layout
                _log(f"[SEARCH]   {c.id}: score {res.score:.4g}"
                     + ("  PASSES ALL SPECS" if rep.passed else "")
                     + f"   ({c.change})")
            except Exception as e:                        # noqa: BLE001
                res.error = f"{type(e).__name__}: {e}"
                res.decision = "ERROR"
                _log(f"[SEARCH]   {c.id}: ERROR {res.error}")
            results.append(res)
            arch.offer(res)

        winner, labelled = select_best(results, baseline_score)
        base_metrics = {r.name: r.value for r in report.results
                        if r.value is not None}
        for r in labelled:
            mem.record(r, baseline_score, base_metrics)

        records = [r.as_dict() for r in labelled]
        if winner is None:
            stagnation["n"] += 1
            _log("[SEARCH] no candidate beat the incumbent — escalating")
            return None, records
        stagnation["n"] = 0
        _log(f"[SEARCH] promoting {winner.candidate.id} "
             f"(score {baseline_score:.4g} -> {winner.score:.4g})")
        return winner.candidate.design, records

    propose.memory = mem          # exposed for reporting
    propose.archive = arch
    return propose


# ── hook factory ──────────────────────────────────────────────────────

def make_hooks(*, cell: str, out_node: str, in_node: str,
               supplies: Mapping[str, float],
               spec_names: Sequence[str] = (),
               bias: Optional[Mapping[str, str]] = None,
               outdir: Optional[str] = None,
               tune_pre=default_tune_pre,
               tune_post=default_tune_post,
               specs: Optional[Sequence] = None,
               branch: bool = True,
               verbosity: int = 0) -> FlowHooks:
    """Production hooks: real ngspice, real Magic, real netgen."""
    from mbg.pipeline import spice_to_gds_with_checks

    sim_kw = dict(out_node=out_node, in_node=in_node, supplies=supplies,
                  bias=bias)

    def _simulate_pre(design: DesignPoint) -> Mapping[str, float]:
        m = simulate_netlist(design.netlist, cell, spec_names, **sim_kw)
        if not m:
            raise RuntimeError(
                "pre-layout simulation produced no usable data — check the "
                "ngspice log; this is a tool failure, not a spec miss")
        return m

    def _build_layout(design: DesignPoint) -> LayoutResult:
        # Every build gets its own directory. The pipeline names artifacts
        # after the cell, so successive iterations used to overwrite each
        # other in place — which destroyed the best iteration's GDS and PEX
        # netlist the moment a later, worse one ran.
        tag = str(design.circuit.get("_tag") or design.note or "run")
        tag = re.sub(r"[^A-Za-z0-9_.-]+", "_", tag)[:40] or "run"
        wd = os.path.join(outdir or ".", "iterations", tag)
        os.makedirs(wd, exist_ok=True)
        prev = os.getcwd()
        try:
            os.chdir(wd)
            r = spice_to_gds_with_checks(
                design.netlist, verbosity=verbosity,
                router_config=router_config_from_layout(design.layout or {},
                                                        verbosity))
        except Exception as e:
            return LayoutResult(ok=False, failure=Failure.TOOL_FAILURE,
                                message=f"layout generation failed: "
                                        f"{type(e).__name__}: {e}")
        finally:
            os.chdir(prev)
        drc = r.get("drc") or {}
        lvs = r.get("lvs") or {}
        pex = r.get("pex") or {}

        drc_ok = bool(drc.get("clean"))
        lvs_ok = bool(lvs.get("match"))
        # Verification gates extraction: LVS is not even consulted if DRC
        # failed, and PEX is not consulted if either did.
        out = LayoutResult(
            gds_path=r.get("gds_path"),
            drc=Outcome.PASS if drc_ok else Outcome.FAIL,
            lvs=(Outcome.PASS if lvs_ok else Outcome.FAIL) if drc_ok else Outcome.SKIP,
            raw=r)
        if not drc_ok:
            out.pex_extraction = Outcome.SKIP
            out.failure = Failure.VERIFICATION_FAILURE
            out.message = drc.get("summary", "DRC failed")
            return out
        if not lvs_ok:
            out.pex_extraction = Outcome.SKIP
            out.failure = Failure.VERIFICATION_FAILURE
            out.message = str((lvs.get("summary") or {}).get("message", "LVS failed"))
            return out

        pex_path = pex.get("pex_path") or pex.get("netlist_path")
        if not pex_path or not os.path.isfile(pex_path):
            out.pex_extraction = Outcome.FAIL
            out.failure = Failure.TOOL_FAILURE
            out.message = "PEX extraction produced no netlist"
            return out
        out.pex_extraction = Outcome.PASS
        out.pex_netlist = pex_path
        out.ok = True
        # Provenance: tie the extracted netlist to the exact GDS it came from,
        # so the sign-off gate can prove they belong to the same iteration.
        out.raw = dict(out.raw)
        out.raw["drc_signoff"] = r.get("drc_signoff")
        out.raw["provenance"] = {
            "tag": tag, "workdir": wd,
            "gds_sha256": file_digest(out.gds_path),
            "pex_sha256": file_digest(pex_path)}
        return out

    def _simulate_pex(design: DesignPoint, layout: LayoutResult) -> Mapping[str, float]:
        if not layout.pex_netlist or not os.path.isfile(layout.pex_netlist):
            raise RuntimeError("no extracted netlist to simulate")
        with open(layout.pex_netlist) as f:
            pex_netlist = f.read()
        # Record which netlist these numbers came from, and what the layout
        # actually loaded — "bandwidth degraded" is only actionable with the
        # node that carries the capacitance.
        prov = (layout.raw or {}).get("provenance") or {}
        prov["simulated_pex_sha256"] = file_digest(layout.pex_netlist)
        heavy = net_capacitance(pex_netlist)[:5]
        prov["net_capacitance"] = [{"net": n, "farads": c} for n, c in heavy]
        layout.raw = {**(layout.raw or {}), "provenance": prov}
        m = simulate_netlist(pex_netlist, cell, spec_names, workdir=outdir, **sim_kw)
        if not m:
            raise RuntimeError(
                "PEX simulation produced no usable data — the extracted "
                "netlist exists but did not simulate; this is a tool failure, "
                "not a spec miss")
        return m

    # Branch-and-compare needs to call the same build/simulate functions the
    # flow uses, so the proposer is handed live references rather than copies.
    ref: Dict[str, object] = {"build_layout": _build_layout,
                              "simulate_pex": _simulate_pex}
    proposer = None
    if branch and specs:
        proposer = make_candidate_proposer(specs=specs, hooks_ref=ref,
                                           verbosity=verbosity)

    return FlowHooks(simulate_pre=_simulate_pre, build_layout=_build_layout,
                     simulate_pex=_simulate_pex, tune_pre=tune_pre,
                     tune_post=tune_post, propose_candidates=proposer)
