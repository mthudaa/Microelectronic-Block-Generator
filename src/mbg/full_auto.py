"""FULL AUTOMATE — one design request, driven to sign-off or a truthful report.

Backs the canonical slash command **`/mbg-full-auto`** on every platform.

This is an orchestration mode, not a large prompt. It sequences the existing
stages, inserts Devil/Angel review gates at the logical boundaries, and lets
the objective tools decide:

    /mbg-full-auto "<design request>"
        -> parse and normalise the specification   (+ review)
        -> LOOP A: pre-layout simulate / evaluate / tune   (+ review)
        -> layout -> DRC -> LVS -> PEX extraction  (+ review)
        -> LOOP B: PEX simulate / evaluate / tune  (+ review)
        -> final sign-off gate                     (+ review)
        -> tapeout package + design report,  or  non-convergence report

Two rules the whole module exists to enforce:

**"Tapeout ready" is a gate, not an adjective.** :class:`SignoffGate` lists
the conditions explicitly, every one is checked against a measured artifact,
and a condition that was not evaluated is reported as `NOT RUN` — never
quietly counted as passed. No corner or Monte-Carlo claim is made unless
those analyses actually ran.

**Reviewers advise; evidence decides.** A critic cannot approve past a failed
DRC, and cannot be bypassed either: an unresolved CRITICAL finding, or a
reviewer that failed to run, blocks sign-off.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import time
from dataclasses import dataclass, field
from typing import Dict, List, Mapping, Optional, Sequence

from mbg.specs import Spec, SpecReport, evaluate_specs, format_spec_table
from mbg.flow import (DesignFlow, DesignPoint, FlowConfig, FlowHooks,
                      FlowResult, Outcome, Failure, Stage)
from mbg.reviewers import (ReviewContext, ReviewLedger, Decision, Verdict,
                           Severity, Finding, run_reviews, synthesize)

__all__ = [
    "AutoStatus", "DesignRequest", "SignoffGate", "SignoffResult",
    "FullAutoConfig", "FullAutoResult", "parse_request", "run_full_auto",
    "MBG_COMMANDS", "CANONICAL_COMMAND",
]

CANONICAL_COMMAND = "/mbg-full-auto"

# Every user-facing MBG slash command. All are namespaced /mbg-*.
MBG_COMMANDS = {
    "/mbg-full-auto": "fully automated design: request -> sign-off or report",
    "/mbg-partial-automate": "same flow, confirming each stage with the user",
    "/mbg-review": "run Devil + Angel review on the current design state",
    "/mbg-signoff": "run the tapeout-ready sign-off gate",
    "/mbg-report": "generate the design report from a completed run",
    "/mbg-status": "show stage, iteration and convergence state of a run",
    "/mbg-check": "environment preflight",
    "/mbg-install": "set up the agent integrations",
    "/mbg-setup-env": "create or repair the Python environment",
    "/mbg-new-skill": "scaffold a canonical MBG skill",
    "/mbg-new-command": "scaffold a canonical MBG workflow",
    "/mbg-review-ai-experiment": "audit an AI experiment record",
    "/mbg-review-extension": "review an MBG agent extension",
}


class AutoStatus:
    SUCCESS = "SUCCESS"                    # tapeout-ready
    NOT_CONVERGED = "NOT_CONVERGED"
    BLOCKED = "BLOCKED"                    # reviewer/critical gate
    TOOL_FAILURE = "TOOL_FAILURE"
    CONFIGURATION_FAILURE = "CONFIGURATION_FAILURE"
    VERIFICATION_FAILURE = "VERIFICATION_FAILURE"
    SPEC_INFEASIBLE = "SPEC_INFEASIBLE"


# ── specification parsing ─────────────────────────────────────────────

# Unit prefixes are domain-dependent, and case is not a reliable guide in
# free text. "100 MHz" and "100 mhz" both mean megahertz — nobody specifies a
# millihertz bandwidth — while "1 mW" always means milliwatt. Sharing one
# table across both reads 100 MHz as 0.1 Hz, which silently turns every
# frequency target into one any circuit passes. Hence one table per domain.
_BIG = {"": 1.0, "k": 1e3, "meg": 1e6, "m": 1e6, "g": 1e9, "t": 1e12}
_SMALL = {"": 1.0, "m": 1e-3, "u": 1e-6, "µ": 1e-6, "n": 1e-9, "p": 1e-12,
          "f": 1e-15}

_METRIC_PATTERNS = [
    ("gain_db", r"gain\s*(?:>=|≥|of at least|at least|:)?\s*([0-9.]+)\s*db",
     " dB", ">=", None),
    ("bw_hz", r"(?:bandwidth|bw|-3\s*db)\s*(?:>=|≥|at least|:)?\s*([0-9.]+)\s*([kmgt]?)\s*hz",
     " Hz", ">=", "big"),
    ("ugf_hz", r"(?:ugf|unity[- ]gain(?:\s*frequency)?|gbw)\s*(?:>=|≥|at least|:)?\s*([0-9.]+)\s*([kmgt]?)\s*hz",
     " Hz", ">=", "big"),
    ("pm_deg", r"phase\s*margin\s*(?:>=|≥|at least|:)?\s*([0-9.]+)\s*(?:deg|°)",
     " deg", ">=", None),
    ("power_w", r"power\s*(?:<=|≤|at most|below|:)?\s*([0-9.]+)\s*([munpµ]?)\s*w",
     " W", "<=", "small"),
]


def _scale(value: str, unit: str, domain: str = "small") -> float:
    table = _BIG if domain == "big" else _SMALL
    return float(value) * table.get((unit or "").lower(), 1.0)


@dataclass
class DesignRequest:
    """A normalised design request.

    Fields are tracked by provenance — `given`, `inferred`, `defaulted`,
    `missing` — because silently inventing a specification is the one thing
    an automated designer must never do.
    """
    raw: str = ""
    cell: str = "design"
    topology: str = ""
    pdk: str = "gf180mcuD"
    vdd: Optional[float] = None
    load_f: Optional[float] = None
    specs: List[Spec] = field(default_factory=list)
    given: List[str] = field(default_factory=list)
    defaulted: List[str] = field(default_factory=list)
    inferred: List[str] = field(default_factory=list)
    missing: List[str] = field(default_factory=list)
    max_pre_iterations: int = 6
    max_pex_iterations: int = 6

    def as_dict(self) -> Dict[str, object]:
        return {
            "raw": self.raw, "cell": self.cell, "topology": self.topology,
            "pdk": self.pdk, "vdd": self.vdd, "load_f": self.load_f,
            "specs": [{"name": s.name, "op": s.op, "target": s.target,
                       "unit": s.unit} for s in self.specs],
            "provenance": {"given": self.given, "defaulted": self.defaulted,
                           "inferred": self.inferred, "missing": self.missing},
        }


def parse_request(text: str, *, cell: Optional[str] = None) -> DesignRequest:
    """Turn a free-text `/mbg-full-auto` request into a normalised spec.

    Only supply a default where doing so is safe (supply voltage, PDK). A
    performance target that was not asked for is *not* invented — it is
    recorded as missing so the reviewers and the user can see the gap.
    """
    req = DesignRequest(raw=text)
    low = text.lower()

    m = re.search(r"\b(?:vdd|supply)\s*(?:=|of|:)?\s*([0-9.]+)\s*v", low)
    if m:
        req.vdd = float(m.group(1))
        req.given.append("vdd")
    else:
        req.vdd = 3.3
        req.defaulted.append("vdd=3.3 (GF180 3.3V devices)")

    m = re.search(r"\b(?:cl|load)\s*(?:=|of|:)?\s*([0-9.]+)\s*([munpµ]?)\s*f\b", low)
    if m:
        req.load_f = _scale(m.group(1), m.group(2), "small")
        req.given.append("load")
    else:
        req.missing.append("load capacitance")

    for name, pat, unit, op, domain in _METRIC_PATTERNS:
        m = re.search(pat, low)
        if not m:
            continue
        groups = m.groups()
        prefix = groups[1] if len(groups) > 1 else ""
        value = _scale(groups[0], prefix, domain or "small")
        req.specs.append(Spec(name, op, value, unit))
        req.given.append(name)

    for kw, topo in (("5t ota", "5T OTA"), ("ota", "OTA"),
                     ("comparator", "comparator"), ("inverter", "inverter"),
                     ("ring oscillator", "ring oscillator"),
                     ("voltage reference", "voltage reference")):
        if kw in low:
            req.topology = topo
            req.inferred.append(f"topology={topo}")
            break

    if cell:
        req.cell = cell
    elif req.topology:
        req.cell = re.sub(r"[^a-z0-9_]+", "_", req.topology.lower()).strip("_")

    if not req.specs:
        req.missing.append("at least one performance target")
    return req


# ── sign-off gate ─────────────────────────────────────────────────────

#: Conditions that cannot be waived by configuration. Physical verification
#: and the artifacts it applies to are what "tapeout ready" *means*; a gate
#: that can be configured to skip DRC can report TAPEOUT_READY for a layout
#: nobody checked, which is precisely the false sign-off this module exists
#: to prevent.
NON_WAIVABLE = ("require_drc_clean", "require_lvs_match",
                "require_pex_extraction", "require_pex_specs",
                "require_gds", "require_pex_netlist",
                "require_drc_signoff")


@dataclass
class SignoffGate:
    """What "tapeout ready" means, stated explicitly and per design class.

    Optional analyses default to *not required*; when they are not required
    they are reported `NOT RUN` and no claim is made about them. Turning one
    on without running it fails the gate rather than passing it silently.

    The conditions in :data:`NON_WAIVABLE` are forced on at construction —
    they describe verification, not preference.
    """
    require_prelayout_specs: bool = True
    require_pex_specs: bool = True
    require_drc_clean: bool = True
    #: Dual-engine DRC: KLayout (sign-off authority, GF180 foundry deck) and
    #: Magic (independent complementary check) must both be clean and must
    #: agree. A Magic-only result no longer satisfies tapeout readiness.
    require_drc_signoff: bool = True
    require_lvs_match: bool = True
    require_pex_extraction: bool = True
    require_gds: bool = True
    require_pex_netlist: bool = True
    require_no_critical_findings: bool = True
    require_complete_reviews: bool = True
    require_report: bool = True
    require_corners: bool = False
    require_monte_carlo: bool = False

    def __post_init__(self):
        forced = [n for n in NON_WAIVABLE if not getattr(self, n, True)]
        for n in forced:
            object.__setattr__(self, n, True)
        self.forced_on = forced        # reported, so the override is visible


@dataclass
class SignoffResult:
    conditions: List[Dict[str, object]] = field(default_factory=list)
    passed: bool = False

    def add(self, name: str, status: str, detail: str = "") -> None:
        self.conditions.append({"condition": name, "status": status,
                                "detail": detail})

    @property
    def failures(self) -> List[Dict[str, object]]:
        return [c for c in self.conditions if c["status"] == "FAIL"]

    @property
    def not_run(self) -> List[Dict[str, object]]:
        return [c for c in self.conditions if c["status"] == "NOT RUN"]

    def as_dict(self) -> Dict[str, object]:
        return {"passed": self.passed, "conditions": self.conditions}

    def table(self) -> str:
        w = max((len(c["condition"]) for c in self.conditions), default=10)
        return "\n".join(
            f"  {c['condition']:<{w}}  {c['status']:<8}"
            + (f"  {c['detail']}" if c["detail"] else "")
            for c in self.conditions)


# ── configuration and result ──────────────────────────────────────────

@dataclass
class FullAutoConfig:
    gate: SignoffGate = field(default_factory=SignoffGate)
    review_mode: str = "full"          # full | critical | signoff_only | off
    reviewers: Sequence[str] = ("devil", "angel")
    outdir: str = "outputs/full_auto"
    verbosity: int = 1
    #: FULL AUTOMATE prioritises convergence over wall-clock. Two PEX
    #: iterations was a root cause of spurious NOT_CONVERGED results: on the
    #: regression inverter the passing design was one step past where the old
    #: budget stopped. Iteration is still bounded, and `patience` ends a run
    #: that has genuinely stopped improving well before the hard limit.
    max_pre_iterations: int = 12
    max_pex_iterations: int = 12
    patience: int = 4
    #: Candidates measured per PEX iteration (branch-and-compare).
    candidates_per_iteration: int = 3
    #: normal | high | exhaustive — search effort, applied by `for_effort`.
    effort: str = "normal"

    @classmethod
    def for_effort(cls, effort: str = "normal", **kw) -> "FullAutoConfig":
        """Preset search budgets. Effort buys iterations and branching."""
        presets = {
            "normal": dict(max_pre_iterations=12, max_pex_iterations=12,
                           candidates_per_iteration=3, patience=4),
            "high": dict(max_pre_iterations=20, max_pex_iterations=20,
                         candidates_per_iteration=4, patience=6),
            "exhaustive": dict(max_pre_iterations=30, max_pex_iterations=30,
                               candidates_per_iteration=5, patience=8),
        }
        if effort not in presets:
            raise ValueError(f"unknown effort {effort!r}; "
                             f"expected one of {sorted(presets)}")
        return cls(effort=effort, **{**presets[effort], **kw})

    def reviews_at(self, stage: str) -> bool:
        if self.review_mode == "off":
            return False
        if self.review_mode == "signoff_only":
            return stage == "FINAL_SIGNOFF"
        if self.review_mode == "critical":
            return stage in ("SPECIFICATION", "PEX_SIMULATION", "FINAL_SIGNOFF")
        return True


@dataclass
class FullAutoResult:
    status: str = AutoStatus.CONFIGURATION_FAILURE
    request: Optional[DesignRequest] = None
    flow: Optional[FlowResult] = None
    signoff: Optional[SignoffResult] = None
    ledger: Optional[ReviewLedger] = None
    decisions: List[Decision] = field(default_factory=list)
    package: Dict[str, str] = field(default_factory=dict)
    report_path: str = ""
    message: str = ""
    elapsed: float = 0.0

    @property
    def tapeout_ready(self) -> bool:
        return self.status == AutoStatus.SUCCESS

    def as_dict(self) -> Dict[str, object]:
        return {
            "status": self.status,
            "tapeout_ready": self.tapeout_ready,
            "message": self.message,
            "elapsed": round(self.elapsed, 3),
            "request": self.request.as_dict() if self.request else None,
            "flow": self.flow.as_dict() if self.flow else None,
            "signoff": self.signoff.as_dict() if self.signoff else None,
            "reviews": self.ledger.summary() if self.ledger else None,
            "package": self.package,
        }


# ── the orchestrator ──────────────────────────────────────────────────

def _log(cfg: FullAutoConfig, level: int, msg: str) -> None:
    if cfg.verbosity >= level:
        print(msg)


def _review_stage(cfg: FullAutoConfig, ctx: ReviewContext,
                  evidence_pass: Optional[bool] = None,
                  hard_gate_ok: Optional[bool] = None) -> Optional[Decision]:
    if not cfg.reviews_at(ctx.stage):
        return None
    reviews = run_reviews(ctx, cfg.reviewers)
    decision = synthesize(ctx, reviews, evidence_pass=evidence_pass,
                          hard_gate_ok=hard_gate_ok)
    if cfg.verbosity >= 1:
        for r in reviews:
            if r.status != "OK":
                print(f"[{r.reviewer.upper()}] {r.status}: {r.error}")
                continue
            worst = r.worst_severity or "none"
            n = len([f for f in r.findings if f.severity != Severity.INFO])
            if r.reviewer == "devil":
                print(f"[DEVIL] {n} finding(s), worst {worst}")
                for f in r.findings[:2]:
                    if f.severity != Severity.INFO:
                        print(f"        {f.severity}: {f.finding}")
            else:
                print(f"[ANGEL] {len(r.recommendations)} recommendation(s)")
                for rec in r.recommendations[:2]:
                    print(f"        {rec.target}: {rec.action}")
        print(f"[DECISION] {decision.verdict} — {decision.reason}")
    return decision


def run_full_auto(request: str, hooks: FlowHooks, *,
                  cell: Optional[str] = None,
                  config: Optional[FullAutoConfig] = None,
                  specs: Optional[Sequence[Spec]] = None,
                  netlist: str = "") -> FullAutoResult:
    """Drive `/mbg-full-auto` end to end.

    ``hooks`` supplies the real work (see :func:`mbg.flow_runtime.make_hooks`)
    so this function stays testable and platform-independent.
    """
    cfg = config or FullAutoConfig()
    started = time.time()
    res = FullAutoResult()
    ledger = ReviewLedger()
    res.ledger = ledger

    _log(cfg, 1, f"[MBG] Command: {CANONICAL_COMMAND}")
    _log(cfg, 1, "[AUTO] Mode: FULL AUTOMATE")

    # ── stage 1: specification ──
    _log(cfg, 1, "\n[STAGE] SPECIFICATION")
    req = parse_request(request, cell=cell)
    if specs:
        req.specs = list(specs)
        req.given.extend(s.name for s in specs if s.name not in req.given)
        req.missing = [m for m in req.missing
                       if m != "at least one performance target"]
    req.max_pre_iterations = cfg.max_pre_iterations
    req.max_pex_iterations = cfg.max_pex_iterations
    res.request = req
    _log(cfg, 1, f"[DESIGNER] normalised {len(req.specs)} target spec(s)"
                 + (f"; missing: {', '.join(req.missing)}" if req.missing else ""))

    ctx = ReviewContext(stage="SPECIFICATION", design=req, ledger=ledger,
                        notes={"missing": req.missing})
    spec_ok = bool(req.specs)
    decision = _review_stage(cfg, ctx, evidence_pass=spec_ok)
    if decision:
        res.decisions.append(decision)
        ledger.record_decision(decision, 0)

    if not req.specs:
        res.status = AutoStatus.CONFIGURATION_FAILURE
        res.message = ("no performance target could be extracted from the "
                       "request, and inventing one would make every later "
                       "result meaningless. State at least one target, e.g. "
                       "'gain >= 40 dB, bandwidth >= 100 MHz'.")
        res.elapsed = time.time() - started
        _finalise(res, cfg, ledger)
        return res

    # ── stages 2-10: the existing two-loop flow ──
    os.makedirs(cfg.outdir, exist_ok=True)
    flow_cfg = FlowConfig(specs=req.specs, outdir=cfg.outdir,
                          max_pre_iterations=cfg.max_pre_iterations,
                          max_pex_iterations=cfg.max_pex_iterations,
                          patience=cfg.patience,
                          candidates_per_iteration=cfg.candidates_per_iteration,
                          verbosity=cfg.verbosity)

    wrapped = _wrap_hooks_with_reviews(hooks, cfg, ledger, res, req)
    flow = DesignFlow(wrapped, flow_cfg).run(
        DesignPoint(cell=req.cell, netlist=netlist or ""))
    res.flow = flow

    # ── stage 11: final sign-off ──
    _log(cfg, 1, "\n[STAGE] FINAL_SIGNOFF")
    gate_ok = (flow.final_layout is not None
               and flow.final_layout.drc == Outcome.PASS
               and flow.final_layout.lvs == Outcome.PASS
               and flow.final_layout.pex_extraction == Outcome.PASS)
    specs_ok = bool(flow.best_pex and flow.best_pex.passed)

    ctx = ReviewContext(stage="FINAL_SIGNOFF", design=req,
                        spec_report=flow.best_pex, pre_report=flow.best_pre,
                        degradation=flow.degradation, layout=flow.final_layout,
                        history=flow.pex, ledger=ledger)
    decision = _review_stage(cfg, ctx, evidence_pass=specs_ok,
                             hard_gate_ok=gate_ok if flow.final_layout else None)
    if decision:
        res.decisions.append(decision)
        ledger.record_decision(decision, len(flow.pex))

    # The report is a deliverable the gate checks, so it must exist before the
    # gate runs — but its own sign-off section depends on the gate. Write it
    # once as evidence, evaluate, then rewrite it with the verdict included.
    # The second write is authoritative.
    res.report_path = _write_report(cfg, res, ledger)

    res.signoff = _evaluate_gate(cfg, flow, decision, res)
    res.status, res.message = _classify(flow, res.signoff, decision)

    if res.status == AutoStatus.SUCCESS:
        res.package = _package(cfg, flow, res)

    res.report_path = _write_report(cfg, res, ledger)
    res.elapsed = time.time() - started
    _finalise(res, cfg, ledger)
    return res


def _wrap_hooks_with_reviews(hooks: FlowHooks, cfg: FullAutoConfig,
                             ledger: ReviewLedger, res: FullAutoResult,
                             req: DesignRequest) -> FlowHooks:
    """Insert review gates around the flow's tuning decisions.

    The reviewers sit where a decision is actually made — the tuner — rather
    than after every subprocess call. The Angel's ranked recommendation is
    passed to the tuner and recorded in the ledger, so the framework can later
    tell whether following that advice improved the measured score.
    """
    state = {"score_before": None}

    def tune_post(design, report, degradation):
        stage = "PEX_SIMULATION"
        ctx = ReviewContext(stage=stage, design=design, spec_report=report,
                            degradation=degradation, ledger=ledger,
                            history=res.flow.pex if res.flow else ())
        decision = _review_stage(cfg, ctx, evidence_pass=False)
        if decision:
            res.decisions.append(decision)
            ledger.record_decision(decision, 0)
            for rec in decision.accepted:
                ledger.propose(rec, stage, 0)
            keys = [r.key() for r in decision.accepted]
            ledger.mark_applied(keys, getattr(report, "score", None))
            state["score_before"] = getattr(report, "score", None)

        base = hooks.tune_post
        if base is None:
            return design
        new = base(design, report, degradation)
        # Carry the Angel's layout advice onto the design point so the next
        # layout attempt can act on it.
        if decision:
            layout = dict(getattr(new, "layout", {}) or {})
            layout["review_actions"] = [r.key() for r in decision.accepted]
            new = new.evolve(layout=layout)
        return new

    def simulate_pex(design, layout):
        metrics = hooks.simulate_pex(design, layout)
        if state["score_before"] is not None:
            report = evaluate_specs(metrics, req.specs, "pex")
            ledger.settle(report.score)
            state["score_before"] = None
        return metrics

    # Forward propose_candidates too. Dropping it here silently disabled
    # branch-and-compare for every /mbg-full-auto run: the flow fell back to
    # the single-edit tuner and no candidate was ever measured.
    return FlowHooks(simulate_pre=hooks.simulate_pre,
                     build_layout=hooks.build_layout,
                     simulate_pex=simulate_pex,
                     tune_pre=hooks.tune_pre,
                     tune_post=tune_post,
                     propose_candidates=hooks.propose_candidates)


def _evaluate_gate(cfg: FullAutoConfig, flow: FlowResult,
                   decision: Optional[Decision],
                   res: FullAutoResult) -> SignoffResult:
    g, s = cfg.gate, SignoffResult()
    layout = flow.final_layout

    def cond(required: bool, name: str, ok: Optional[bool], detail: str = ""):
        if not required:
            s.add(name, "NOT REQUIRED", detail)
        elif ok is None:
            s.add(name, "NOT RUN", detail or "not evaluated")
        else:
            s.add(name, "PASS" if ok else "FAIL", detail)

    # The specs below come from the BEST iteration; the verification rows
    # come from a layout. Assert they are the same iteration, or the gate is
    # joining two different designs.
    best_layout = getattr(flow, "best_pex_layout", None) or layout
    consistent = (flow.best_pex_iteration is None
                  or best_layout is layout
                  or flow.best_pex_iteration == len(flow.pex))
    s.add("artifact consistency", "PASS" if consistent else "FAIL",
          "" if consistent else
          f"specs are from iteration {flow.best_pex_iteration} but the "
          f"packaged layout is from iteration {len(flow.pex)}")
    layout = best_layout

    cond(g.require_prelayout_specs, "pre-layout specs",
         bool(flow.best_pre and flow.best_pre.passed))
    cond(g.require_pex_specs, "PEX specs",
         bool(flow.best_pex and flow.best_pex.passed),
         "" if flow.best_pex else "no PEX simulation completed")
    cond(g.require_drc_clean, "DRC clean",
         (layout.drc == Outcome.PASS) if layout else None)

    # Dual-DRC sign-off. Recorded by the pipeline when both engines ran; an
    # absent verdict is NOT RUN, never an implicit pass.
    signoff = ((layout.raw or {}).get("drc_signoff") or {}) if layout else {}
    verdict = signoff.get("verdict")
    cond(g.require_drc_signoff, "DRC sign-off (Magic + KLayout)",
         (verdict == "PASS") if verdict else None,
         f"{verdict}: {signoff.get('reason','')}" if verdict and verdict != "PASS"
         else ("dual-engine DRC did not run" if not verdict else ""))
    cond(g.require_lvs_match, "LVS match",
         (layout.lvs == Outcome.PASS) if layout else None)
    cond(g.require_pex_extraction, "PEX extraction",
         (layout.pex_extraction == Outcome.PASS) if layout else None)
    cond(g.require_gds, "final GDS",
         bool(layout and layout.gds_path and os.path.isfile(layout.gds_path)))
    cond(g.require_pex_netlist, "final PEX netlist",
         bool(layout and layout.pex_netlist
              and os.path.isfile(layout.pex_netlist)))

    blocking = decision.blocking if decision else []
    cond(g.require_no_critical_findings, "no CRITICAL findings",
         (len(blocking) == 0) if decision else None,
         f"{len(blocking)} unresolved" if blocking else "")
    # `all([])` is True, so a run configured with no reviewers used to satisfy
    # both reviewer gates by never reviewing anything. An empty review set is
    # an absent review, not a clean one.
    reviews_ok = None
    detail = ""
    if decision:
        if not decision.reviews:
            reviews_ok, detail = None, "no reviewers ran"
        else:
            reviews_ok = all(r.status == "OK" for r in decision.reviews)
            detail = "" if reviews_ok else "a reviewer failed to run"
    cond(g.require_complete_reviews, "reviews complete", reviews_ok, detail)

    # Analyses that were never run are reported as such, never as passes.
    cond(g.require_corners, "PVT corners", None if g.require_corners else None,
         "not part of this flow")
    cond(g.require_monte_carlo, "Monte Carlo / mismatch",
         None if g.require_monte_carlo else None, "not part of this flow")
    # Checked, not asserted. This used to be a literal True, evaluated
    # before the report was even written.
    report_path = os.path.join(cfg.outdir, "final_design_report.md")
    cond(g.require_report, "design report",
         os.path.isfile(report_path) and os.path.getsize(report_path) > 0,
         "" if os.path.isfile(report_path) else "not written yet")

    s.passed = not s.failures and not s.not_run
    return s


def _classify(flow: FlowResult, gate: SignoffResult,
              decision: Optional[Decision]) -> tuple:
    if flow is None:
        return AutoStatus.CONFIGURATION_FAILURE, "the flow never ran"
    if flow.failure == Failure.TOOL_FAILURE:
        return AutoStatus.TOOL_FAILURE, flow.message
    if flow.failure == Failure.CONFIGURATION_FAILURE:
        return AutoStatus.CONFIGURATION_FAILURE, flow.message
    if decision and decision.verdict == Verdict.ESCALATE:
        # A reviewer did not complete. Silence is not approval.
        return AutoStatus.BLOCKED, decision.reason
    if flow.failure == Failure.VERIFICATION_FAILURE:
        return AutoStatus.VERIFICATION_FAILURE, flow.message
    # BLOCKED is reserved for a run the evidence would otherwise have passed:
    # when the design simply did not converge, NOT_CONVERGED is both true and
    # more actionable, and the critical findings are listed in the report
    # either way. Saying "blocked" here would hide the real reason.
    if (decision and decision.verdict == Verdict.BLOCK and decision.blocking
            and flow.status not in (Outcome.NOT_CONVERGED, Outcome.FAIL)):
        return (AutoStatus.BLOCKED,
                f"sign-off blocked by {len(decision.blocking)} unresolved "
                f"CRITICAL finding(s): {decision.blocking[0].finding}")
    if gate.passed and flow.status == Outcome.PASS:
        return AutoStatus.SUCCESS, "all sign-off conditions met"
    if flow.status in (Outcome.NOT_CONVERGED, Outcome.FAIL):
        return AutoStatus.NOT_CONVERGED, flow.message or "specifications not met"
    return (AutoStatus.NOT_CONVERGED,
            "sign-off gate not satisfied: "
            + ", ".join(c["condition"] for c in (gate.failures + gate.not_run)))


def _package(cfg: FullAutoConfig, flow: FlowResult,
             res: FullAutoResult) -> Dict[str, str]:
    """Collect the tapeout deliverables. Only files that actually exist."""
    final = os.path.join(cfg.outdir, "final")
    os.makedirs(final, exist_ok=True)
    out: Dict[str, str] = {}
    # Package the layout whose metrics are reported.
    layout = getattr(flow, "best_pex_layout", None) or flow.final_layout
    if layout:
        for key, src in (("gds", layout.gds_path),
                         ("pex_spice", layout.pex_netlist)):
            if src and os.path.isfile(src):
                dst = os.path.join(final, os.path.basename(src))
                shutil.copy2(src, dst)
                out[key] = dst
        raw = layout.raw or {}
        for key in ("drc", "lvs"):
            rp = (raw.get(key) or {}).get("report_path")
            if rp and os.path.isfile(rp):
                dst = os.path.join(final, os.path.basename(rp))
                shutil.copy2(rp, dst)
                out[f"{key}_report"] = dst
    hist = os.path.join(cfg.outdir, "history.json")
    if os.path.isfile(hist):
        dst = os.path.join(final, "iteration_history.json")
        shutil.copy2(hist, dst)
        out["iteration_history"] = dst
    return out


def _write_report(cfg: FullAutoConfig, res: FullAutoResult,
                  ledger: ReviewLedger) -> str:
    """Design report on success; non-convergence report otherwise."""
    os.makedirs(cfg.outdir, exist_ok=True)
    path = os.path.join(cfg.outdir, "final_design_report.md")
    flow, req, gate = res.flow, res.request, res.signoff
    L: List[str] = []
    ok = res.status == AutoStatus.SUCCESS

    L.append(f"# {'Design Report' if ok else 'Non-Convergence Report'}"
             f" — {req.cell if req else 'design'}")
    L.append("")
    L.append(f"**Status:** `{res.status}`  |  **Tapeout ready:** "
             f"{'YES' if ok else 'NO'}")
    if res.message:
        L.append(f"\n{res.message}")

    L.append("\n## 1. Design Request\n")
    L.append("```text\n" + (req.raw.strip() if req else "") + "\n```")

    L.append("\n## 2. Normalized Specifications\n")
    if req:
        for s in req.specs:
            L.append(f"- `{s.name}` {s.op} {s.target:g}{s.unit}")
        L.append("")
        L.append(f"- given: {', '.join(req.given) or 'none'}")
        L.append(f"- defaulted: {', '.join(req.defaulted) or 'none'}")
        L.append(f"- inferred: {', '.join(req.inferred) or 'none'}")
        L.append(f"- **missing: {', '.join(req.missing) or 'none'}**")

    if req and req.topology:
        L.append(f"\n## 3. Architecture\n\n{req.topology}")

    if flow:
        L.append("\n## 4. Pre-Layout Optimization\n")
        L.append(f"Iterations: {len(flow.pre_layout)}")
        for r in flow.pre_layout:
            L.append(f"- iteration {r.iteration}: "
                     f"{'PASS' if r.spec_pass else 'FAIL'} (score {r.score})")
        if flow.best_pre:
            L.append("\n```text\n" + format_spec_table(flow.best_pre) + "\n```")

        L.append("\n## 5. Physical Design and Verification\n")
        if flow.final_layout:
            L.append(f"- DRC: `{flow.final_layout.drc}`")
            L.append(f"- LVS: `{flow.final_layout.lvs}`")
            L.append(f"- PEX extraction: `{flow.final_layout.pex_extraction}`")

        L.append("\n## 6. Pre-layout vs PEX Degradation\n")
        if flow.degradation:
            for d in flow.degradation:
                L.append(f"- {d.describe()}")
        else:
            L.append("_no comparison available_")

        L.append("\n## 7. PEX-Aware Optimization\n")
        L.append(f"Iterations: {len(flow.pex)}")
        for r in flow.pex:
            L.append(f"- iteration {r.iteration}: DRC {r.drc} · LVS {r.lvs} · "
                     f"PEX {r.pex_extraction} · sim {r.pex_simulation} · "
                     f"specs {'PASS' if r.spec_pass else 'FAIL'} "
                     f"(score {r.score})")
        if flow.best_pex_iteration:
            L.append(f"\nBest iteration: **{flow.best_pex_iteration}**")
        if flow.best_pex:
            L.append("\n```text\n" + format_spec_table(flow.best_pex) + "\n```")

    L.append("\n## 8. Critical Review Summary\n")
    summ = ledger.summary()
    dv, an = summ["devil"], summ["angel"]
    L.append(f"**Devil Reviewer** — {dv['reviews']} review(s), "
             f"{dv['findings']} finding(s)")
    for sev, n in sorted(dv["by_severity"].items()):
        L.append(f"- {sev}: {n}")
    L.append(f"\n**Angel Reviewer** — {an['reviews']} review(s), "
             f"{an['recommendations']} recommendation(s), "
             f"{an['tested']} tested, {an['improved']} improved the score, "
             f"{an['degraded']} made it worse")
    unresolved = dv.get("unresolved_critical") or []
    L.append(f"\n**Unresolved CRITICAL findings:** "
             + ("None" if not unresolved else ""))
    for f in unresolved:
        L.append(f"- {f}")

    if summ["recommendations"]:
        L.append("\n### Recommendation trace\n")
        L.append("| recommendation | target | status | score before | after |")
        L.append("| --- | --- | --- | ---: | ---: |")
        for e in summ["recommendations"]:
            before = e["score_before"]
            after = e["score_after"]
            L.append(f"| {e['action']} | {e['target']} | {e['status']} | "
                     f"{before if before is None else round(before, 4)} | "
                     f"{after if after is None else round(after, 4)} |")
        L.append("")
        L.append("_Recommendations applied in the same iteration share one "
                 "before/after measurement, so the score change is attributed "
                 "to the batch, not to any single item. Isolating an "
                 "individual contribution needs one change per iteration._")

    L.append("\n## 9. Sign-Off Gate\n")
    if gate:
        L.append("```text\n" + gate.table() + "\n```")
        if gate.not_run:
            L.append("\nConditions reported `NOT RUN` were not evaluated. No "
                     "claim is made about them.")

    if not ok:
        L.append("\n## 10. What to do next\n")
        if flow and flow.best_pex:
            for f in flow.best_pex.failures:
                L.append(f"- `{f.name}` still misses: {f.value:.4g} vs "
                         f"{f.op} {f.target:.4g}{f.unit}")
        acted = [e for e in summ["recommendations"]
                 if e["status"] in ("IMPROVED", "DEGRADED")]
        if acted:
            L.append("\nWhat helped and what did not:\n")
            for e in acted:
                L.append(f"- {e['action']}: **{e['status']}**")
        L.append("\nRecommended manual intervention: review the unresolved "
                 "findings above, then either relax an infeasible target or "
                 "supply a stronger `tune_post` for the failing metric.")

    if res.package:
        L.append("\n## 11. Tapeout Files\n")
        for k, v in sorted(res.package.items()):
            L.append(f"- `{k}`: `{v}`")

    L.append("\n## 12. Reproduction\n")
    L.append("```text")
    L.append(f'{CANONICAL_COMMAND} "{(req.raw.strip() if req else "")[:200]}"')
    L.append("```")

    with open(path, "w") as f:
        f.write("\n".join(L) + "\n")
    return path


def _finalise(res: FullAutoResult, cfg: FullAutoConfig,
              ledger: ReviewLedger) -> None:
    try:
        ledger.write(os.path.join(cfg.outdir, "review_history.json"))
        with open(os.path.join(cfg.outdir, "full_auto_result.json"), "w") as f:
            json.dump(res.as_dict(), f, indent=2, default=str)
            f.write("\n")
    except OSError:
        pass
    if cfg.verbosity >= 1:
        print("\n[SIGNOFF]")
        if res.signoff:
            print(res.signoff.table())
        print(f"\nSTATUS: {res.status}"
              + ("  (TAPEOUT_READY)" if res.tapeout_ready else ""))
        if res.report_path:
            print(f"Report: {res.report_path}")
