"""Independent critic reviewers, and the synthesis that decides what to do.

The design flow proposes; the reviewers criticise; the tools decide. That
ordering is the whole point of this module.

Roles are kept apart deliberately:

    Designer        proposes and modifies the design
    Devil Reviewer  tries to falsify it — risks, gaps, unsafe pass conditions
    Angel Reviewer  recommends the most productive next action
    Synthesizer     combines both with the *objective* evidence and decides

Reviewers never edit the design. They return structured findings and
recommendations, so the framework can record who proposed what, whether it
was tried, and whether it helped — and stop repeating advice that did not
work.

**Objective evidence outranks both reviewers.** A DRC failure is a failure
however optimistic the critics are, and no amount of reviewer approval can
turn an LVS mismatch into a sign-off. The reviewers can *block*; they cannot
*approve past* a hard gate.

The built-in reviewers here are deterministic and rule-based. That is on
purpose: the core flow has to run with no AI platform available (a CI box, an
offline machine), so the framework ships critics that reason over the same
measured evidence a model would be shown. Platform layers (Claude Code,
Codex, OpenCode) can register richer LLM-backed reviewers through
:func:`register_reviewer` without changing any of the control logic.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field, asdict
from typing import Callable, Dict, List, Optional, Sequence

__all__ = [
    "Severity", "Verdict", "ReviewStatus", "Finding", "Recommendation",
    "Review", "ReviewContext", "Decision", "ReviewLedger",
    "devil_review", "angel_review", "synthesize",
    "register_reviewer", "get_reviewer", "run_reviews", "REVIEW_STAGES",
]


class Severity:
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


_SEVERITY_ORDER = {Severity.INFO: 0, Severity.LOW: 1, Severity.MEDIUM: 2,
                   Severity.HIGH: 3, Severity.CRITICAL: 4}


class Verdict:
    ACCEPT = "ACCEPT"
    REVISE = "REVISE"
    RETRY = "RETRY"
    ROLLBACK = "ROLLBACK"
    ESCALATE = "ESCALATE"
    BLOCK = "BLOCK"


class ReviewStatus:
    OK = "OK"
    REVIEWER_FAILURE = "REVIEWER_FAILURE"
    REVIEW_INCOMPLETE = "REVIEW_INCOMPLETE"


# Reviews run at logical design stages, not after every subprocess call.
REVIEW_STAGES = (
    "SPECIFICATION", "INITIAL_CIRCUIT", "PRE_SIMULATION", "PRE_OPTIMIZATION",
    "LAYOUT_GENERATION", "DRC", "LVS", "PEX_EXTRACTION", "PEX_SIMULATION",
    "POST_LAYOUT_OPTIMIZATION", "FINAL_SIGNOFF",
)


@dataclass
class Finding:
    severity: str
    category: str
    finding: str
    evidence: Dict[str, object] = field(default_factory=dict)

    @property
    def blocking(self) -> bool:
        return self.severity == Severity.CRITICAL


@dataclass
class Recommendation:
    action: str
    rationale: str = ""
    target: str = "circuit"          # "circuit" | "layout" | "spec" | "process"
    expected_effect: str = ""
    id: str = ""

    def key(self) -> str:
        return self.id or f"{self.target}:{self.action}"


@dataclass
class Review:
    reviewer: str
    stage: str
    verdict: str = Verdict.ACCEPT
    confidence: float = 0.5
    findings: List[Finding] = field(default_factory=list)
    recommendations: List[Recommendation] = field(default_factory=list)
    status: str = ReviewStatus.OK
    error: str = ""
    elapsed: float = 0.0

    @property
    def worst_severity(self) -> Optional[str]:
        if not self.findings:
            return None
        return max((f.severity for f in self.findings),
                   key=lambda s: _SEVERITY_ORDER.get(s, 0))

    def blocking_findings(self) -> List[Finding]:
        return [f for f in self.findings if f.blocking]

    def as_dict(self) -> Dict[str, object]:
        return {
            "reviewer": self.reviewer, "stage": self.stage,
            "verdict": self.verdict, "confidence": round(self.confidence, 3),
            "status": self.status, "error": self.error,
            "elapsed": round(self.elapsed, 3),
            "findings": [asdict(f) for f in self.findings],
            "recommendations": [asdict(r) for r in self.recommendations],
        }


@dataclass
class ReviewContext:
    """Everything a reviewer is allowed to look at.

    Both reviewers get the same context. Their *roles* differ, not their
    evidence — a critic that sees less than the one it is meant to balance
    cannot meaningfully disagree with it.
    """
    stage: str
    iteration: int = 0
    design: object = None
    spec_report: object = None        # mbg.specs.SpecReport
    pre_report: object = None         # pre-layout SpecReport, for comparison
    degradation: Sequence = ()        # mbg.specs.Degradation
    layout: object = None             # mbg.flow.LayoutResult
    history: Sequence = ()            # IterationRecord list
    prior_reviews: Sequence["Review"] = ()
    ledger: Optional["ReviewLedger"] = None
    notes: Dict[str, object] = field(default_factory=dict)


@dataclass
class Decision:
    verdict: str
    reason: str = ""
    stage: str = ""
    blocking: List[Finding] = field(default_factory=list)
    accepted: List[Recommendation] = field(default_factory=list)
    evidence_pass: Optional[bool] = None
    reviews: List[Review] = field(default_factory=list)

    @property
    def may_proceed(self) -> bool:
        return self.verdict in (Verdict.ACCEPT,)

    def as_dict(self) -> Dict[str, object]:
        return {
            "stage": self.stage, "verdict": self.verdict,
            "reason": self.reason, "evidence_pass": self.evidence_pass,
            "blocking": [asdict(f) for f in self.blocking],
            "accepted": [asdict(r) for r in self.accepted],
            "reviews": [r.as_dict() for r in self.reviews],
        }


# ── the Devil: try to falsify the design ──────────────────────────────

def devil_review(ctx: ReviewContext) -> Review:
    """Adversarial review. Looks for reasons this result is *not* trustworthy.

    Deliberately not symmetric with the Angel: this one raises severity and
    withholds approval, and it treats missing evidence as a problem rather
    than as an absence of problems.
    """
    r = Review(reviewer="devil", stage=ctx.stage, confidence=0.8)
    sr = ctx.spec_report
    layout = ctx.layout

    # -- hard verification --
    if layout is not None:
        if getattr(layout, "drc", None) == "FAIL":
            r.findings.append(Finding(
                Severity.CRITICAL, "drc",
                "DRC reported violations; the layout is not manufacturable "
                "as drawn.",
                {"drc": layout.drc, "message": getattr(layout, "message", "")}))
        if getattr(layout, "lvs", None) == "FAIL":
            r.findings.append(Finding(
                Severity.CRITICAL, "lvs",
                "LVS mismatch: the layout does not implement the schematic. "
                "Every post-layout number measured from it describes a "
                "different circuit.",
                {"lvs": layout.lvs, "message": getattr(layout, "message", "")}))
        if getattr(layout, "pex_extraction", None) == "FAIL":
            r.findings.append(Finding(
                Severity.CRITICAL, "pex",
                "Parasitic extraction failed; there is no extracted netlist "
                "to judge the design by.",
                {"pex_extraction": layout.pex_extraction}))

    # -- specifications --
    if sr is not None and getattr(sr, "results", None):
        for res in sr.results:
            if res.status == "MISSING":
                r.findings.append(Finding(
                    Severity.HIGH, res.name,
                    f"{res.name} was never measured. An unmeasured target is "
                    f"not a met target.",
                    {"target": res.target, "measured": None}))
            elif res.status == "FAIL" and res.required:
                sev = Severity.HIGH
                if res.margin_pct is not None and abs(res.margin_pct) < 5:
                    sev = Severity.MEDIUM
                r.findings.append(Finding(
                    sev, res.name,
                    f"{res.name} misses its target "
                    f"({res.value:.4g} vs {res.op} {res.target:.4g}"
                    f"{res.unit}).",
                    {"target": res.target, "measured": res.value,
                     "margin_pct": res.margin_pct}))
            elif res.status == "PASS" and res.margin_pct is not None \
                    and 0 <= res.margin_pct < 5:
                r.findings.append(Finding(
                    Severity.MEDIUM, res.name,
                    f"{res.name} passes by only {res.margin_pct:.1f}% — that "
                    f"is inside the noise of corner and mismatch variation, "
                    f"which has not been simulated here.",
                    {"target": res.target, "measured": res.value,
                     "margin_pct": res.margin_pct}))

    # -- parasitic degradation --
    for d in (ctx.degradation or ()):
        if getattr(d, "worsened", False) and d.delta_pct is not None \
                and abs(d.delta_pct) >= 25:
            r.findings.append(Finding(
                Severity.HIGH, d.name,
                f"{d.name} degraded {d.delta_pct:+.1f}% from pre-layout to "
                f"extraction. A shift that large means the schematic result "
                f"was not predictive of silicon.",
                {"pre": d.pre, "post": d.post, "delta_pct": d.delta_pct}))

    # -- stagnation --
    hist = list(ctx.history or ())
    if len(hist) >= 3:
        scores = [h.score for h in hist[-3:] if getattr(h, "score", None) is not None]
        if len(scores) == 3 and scores[0] <= scores[-1]:
            r.findings.append(Finding(
                Severity.MEDIUM, "convergence",
                "The last three iterations did not improve. Continuing to "
                "tune the same parameters is unlikely to close the gap.",
                {"scores": scores}))

    if ctx.stage == "FINAL_SIGNOFF" and sr is not None and not getattr(sr, "passed", False):
        r.findings.append(Finding(
            Severity.CRITICAL, "signoff",
            "Sign-off requested while required specifications are unmet.",
            {"failures": [f.name for f in getattr(sr, "failures", [])]}))

    worst = r.worst_severity
    if worst == Severity.CRITICAL:
        r.verdict, r.confidence = Verdict.BLOCK, 0.95
    elif worst == Severity.HIGH:
        r.verdict, r.confidence = Verdict.REVISE, 0.9
    elif worst == Severity.MEDIUM:
        r.verdict, r.confidence = Verdict.REVISE, 0.6
    else:
        r.verdict, r.confidence = Verdict.ACCEPT, 0.55
        if not r.findings:
            r.findings.append(Finding(
                Severity.INFO, "scope",
                "No objection from the evidence provided. Note that corner "
                "and mismatch data were not part of this review.", {}))
    return r


# ── the Angel: find the most productive way forward ───────────────────

_ACTIONS = {
    "gain_db": [
        Recommendation("increase device width on the gain devices",
                       "transconductance scales with W/L at fixed current",
                       "circuit", "higher DC gain", "circuit:widen_gain"),
        Recommendation("increase channel length on the load devices",
                       "raises output resistance, and gain with it",
                       "circuit", "higher DC gain", "circuit:lengthen_load"),
    ],
    "bw_hz": [
        Recommendation("widen and shorten the critical net",
                       "bandwidth loss after extraction is dominated by "
                       "routing capacitance and series resistance",
                       "layout", "recover bandwidth", "layout:critical_net"),
        Recommendation("move the output net to a higher metal layer",
                       "lower capacitance per unit length to substrate",
                       "layout", "recover bandwidth", "layout:promote_metal"),
        Recommendation("reduce load device width",
                       "less self-loading at the dominant pole",
                       "circuit", "higher bandwidth", "circuit:shrink_load"),
    ],
    "ugf_hz": [
        Recommendation("widen and shorten the critical net",
                       "same dominant-pole loading that limits bandwidth",
                       "layout", "higher unity-gain frequency",
                       "layout:critical_net"),
    ],
    "pm_deg": [
        Recommendation("revisit compensation at the dominant-pole node",
                       "added load capacitance moves the second pole in",
                       "circuit", "restore phase margin", "circuit:compensation"),
    ],
}


def angel_review(ctx: ReviewContext) -> Review:
    """Constructive review: what is the cheapest change most likely to work.

    Not a cheerleader — it still records weaknesses — but its output is
    ranked *actions*, and it avoids re-proposing advice the ledger shows has
    already been tried and did not help.
    """
    r = Review(reviewer="angel", stage=ctx.stage, confidence=0.7)
    sr = ctx.spec_report
    ledger = ctx.ledger

    failing: List[str] = []
    if sr is not None and getattr(sr, "results", None):
        failing = [res.name for res in sr.results
                   if res.required and res.status != "PASS"]

    # Metrics that degraded across the layout boundary are the highest-value
    # target: the circuit already achieved them once.
    degraded = [d.name for d in (ctx.degradation or ())
                if getattr(d, "worsened", False) and d.status != "PASS"]
    ordered = degraded + [n for n in failing if n not in degraded]

    for name in ordered:
        for rec in _ACTIONS.get(name, []):
            if ledger is not None and ledger.is_exhausted(rec.key()):
                continue
            if rec not in r.recommendations:
                r.recommendations.append(rec)

    if degraded:
        r.findings.append(Finding(
            Severity.MEDIUM, "parasitics",
            f"{', '.join(degraded)} met target before layout and lost it "
            f"after extraction, so the circuit topology is adequate and the "
            f"problem is physical. Layout changes should be tried before "
            f"resizing.",
            {"degraded": degraded}))

    if ctx.layout is not None and getattr(ctx.layout, "drc", None) == "FAIL":
        r.recommendations.insert(0, Recommendation(
            "fix the DRC violations before tuning anything else",
            "performance measured from an illegal layout is not meaningful",
            "layout", "unblock the flow", "layout:fix_drc"))
    if ctx.layout is not None and getattr(ctx.layout, "lvs", None) == "FAIL":
        r.recommendations.insert(0, Recommendation(
            "resolve the LVS mismatch before tuning anything else",
            "the extracted netlist describes a different circuit",
            "layout", "unblock the flow", "layout:fix_lvs"))

    if not ordered and not r.recommendations:
        r.verdict, r.confidence = Verdict.ACCEPT, 0.8
        r.findings.append(Finding(
            Severity.INFO, "status",
            "All required targets are met on the evidence supplied; no "
            "change recommended.", {}))
    else:
        r.verdict = Verdict.REVISE
        r.confidence = 0.75 if r.recommendations else 0.4
        if not r.recommendations:
            r.findings.append(Finding(
                Severity.MEDIUM, "coverage",
                f"No catalogued action addresses {', '.join(ordered)}; this "
                f"needs a designer or a richer reviewer.", {"unmet": ordered}))
    return r


# ── synthesis: evidence first, reviewers second ───────────────────────

def synthesize(ctx: ReviewContext, reviews: Sequence[Review],
               evidence_pass: Optional[bool] = None,
               hard_gate_ok: Optional[bool] = None) -> Decision:
    """Combine critiques with measured evidence and decide the next action.

    Not an average of opinions. The order of precedence is fixed:

    1. a reviewer that failed to run leaves the review incomplete;
    2. a hard verification gate (DRC/LVS/PEX) outranks everything;
    3. an unresolved CRITICAL finding blocks acceptance;
    4. objective specification evidence outranks reviewer sentiment;
    5. only then do the reviewers' verdicts matter.
    """
    d = Decision(verdict=Verdict.ACCEPT, stage=ctx.stage,
                 reviews=list(reviews), evidence_pass=evidence_pass)

    failed = [r for r in reviews if r.status != ReviewStatus.OK]
    if failed:
        d.verdict = Verdict.ESCALATE
        d.reason = ("review incomplete: "
                    + ", ".join(f"{r.reviewer} ({r.status})" for r in failed)
                    + ". A missing review is not an approval.")
        return d

    blocking = [f for r in reviews for f in r.blocking_findings()]
    d.blocking = blocking

    if hard_gate_ok is False:
        d.verdict = Verdict.BLOCK
        d.reason = ("a hard verification gate failed; reviewer opinion cannot "
                    "override DRC/LVS/PEX evidence")
        return d

    if blocking:
        d.verdict = Verdict.BLOCK
        d.reason = (f"{len(blocking)} unresolved CRITICAL finding(s): "
                    + "; ".join(f.finding for f in blocking[:2]))
        return d

    # Rank the Angel's recommendations for the caller to act on.
    for r in reviews:
        if r.reviewer == "angel":
            d.accepted = list(r.recommendations)

    if evidence_pass is False:
        d.verdict = Verdict.REVISE
        d.reason = ("measured results do not meet the required "
                    "specifications")
        return d

    if any(r.verdict in (Verdict.BLOCK, Verdict.ROLLBACK) for r in reviews):
        d.verdict = Verdict.BLOCK
        d.reason = "a reviewer blocked on non-critical grounds"
        return d

    if evidence_pass is True:
        # Reviewers may still ask for revision, but they cannot veto measured
        # success outright — they downgrade it to a noted concern.
        concerns = [f for r in reviews for f in r.findings
                    if _SEVERITY_ORDER.get(f.severity, 0) >= _SEVERITY_ORDER[Severity.HIGH]]
        d.verdict = Verdict.ACCEPT
        d.reason = ("measured results meet the required specifications"
                    + (f"; {len(concerns)} HIGH concern(s) noted" if concerns else ""))
        return d

    if any(r.verdict == Verdict.REVISE for r in reviews):
        d.verdict = Verdict.REVISE
        d.reason = "reviewers recommend revision; no objective verdict available"
        return d

    d.reason = "no objection"
    return d


# ── ledger: did the advice actually help? ─────────────────────────────

@dataclass
class ReviewLedger:
    """Tracks recommendation -> change -> measured outcome.

    Without this the Angel re-proposes the same failed idea every iteration.
    A recommendation that has been tried twice without improving the score is
    treated as exhausted and withheld.
    """
    entries: List[Dict[str, object]] = field(default_factory=list)
    decisions: List[Dict[str, object]] = field(default_factory=list)
    max_attempts: int = 2

    def record_decision(self, decision: Decision, iteration: int) -> None:
        d = decision.as_dict()
        d["iteration"] = iteration
        self.decisions.append(d)

    def propose(self, rec: Recommendation, stage: str, iteration: int) -> None:
        self.entries.append({"key": rec.key(), "action": rec.action,
                             "target": rec.target, "stage": stage,
                             "iteration": iteration, "status": "PROPOSED",
                             "score_before": None, "score_after": None})

    def mark_applied(self, keys: Sequence[str], score_before: Optional[float]) -> None:
        for e in self.entries:
            if e["key"] in keys and e["status"] == "PROPOSED":
                e["status"] = "APPLIED"
                e["score_before"] = score_before

    def settle(self, score_after: Optional[float]) -> None:
        """Close out applied recommendations against the new measurement."""
        for e in self.entries:
            if e["status"] != "APPLIED":
                continue
            before, after = e.get("score_before"), score_after
            if before is None or after is None:
                e["status"] = "UNTESTED"
                continue
            e["score_after"] = after
            e["status"] = "IMPROVED" if after < before else (
                "NEUTRAL" if after == before else "DEGRADED")

    def attempts(self, key: str) -> int:
        return sum(1 for e in self.entries
                   if e["key"] == key and e["status"] in
                   ("APPLIED", "IMPROVED", "NEUTRAL", "DEGRADED", "UNTESTED"))

    def is_exhausted(self, key: str) -> bool:
        tried = [e for e in self.entries if e["key"] == key]
        helped = any(e["status"] == "IMPROVED" for e in tried)
        return (not helped) and self.attempts(key) >= self.max_attempts

    def summary(self) -> Dict[str, object]:
        devil = [r for d in self.decisions for r in d["reviews"]
                 if r["reviewer"] == "devil"]
        angel = [r for d in self.decisions for r in d["reviews"]
                 if r["reviewer"] == "angel"]
        findings = [f for r in devil for f in r["findings"]]
        by_sev: Dict[str, int] = {}
        for f in findings:
            by_sev[f["severity"]] = by_sev.get(f["severity"], 0) + 1
        return {
            "devil": {"reviews": len(devil), "findings": len(findings),
                      "by_severity": by_sev,
                      "unresolved_critical": [
                          f["finding"] for d in self.decisions[-1:]
                          for f in d["blocking"]]},
            "angel": {"reviews": len(angel),
                      "recommendations": len(self.entries),
                      "tested": sum(1 for e in self.entries
                                    if e["status"] in ("IMPROVED", "NEUTRAL",
                                                       "DEGRADED")),
                      "improved": sum(1 for e in self.entries
                                      if e["status"] == "IMPROVED"),
                      "degraded": sum(1 for e in self.entries
                                      if e["status"] == "DEGRADED")},
            "recommendations": self.entries,
        }

    def write(self, path: str) -> str:
        os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
        with open(path, "w") as f:
            json.dump({"summary": self.summary(), "decisions": self.decisions},
                      f, indent=2, default=str)
            f.write("\n")
        return path


# ── registry ──────────────────────────────────────────────────────────

_REGISTRY: Dict[str, Callable[[ReviewContext], Review]] = {
    "devil": devil_review,
    "angel": angel_review,
}


def register_reviewer(name: str, fn: Callable[[ReviewContext], Review]) -> None:
    """Replace or add a reviewer — how a platform plugs in an LLM critic."""
    _REGISTRY[name] = fn


def get_reviewer(name: str) -> Callable[[ReviewContext], Review]:
    if name not in _REGISTRY:
        raise KeyError(f"no reviewer named {name!r}; have {sorted(_REGISTRY)}")
    return _REGISTRY[name]


def run_reviews(ctx: ReviewContext, names: Sequence[str] = ("devil", "angel"),
                timeout: Optional[float] = None) -> List[Review]:
    """Run each reviewer independently, bounding failures to that reviewer.

    A critic that raises must not take the run down with it — that would make
    an advisory component a single point of failure. The failure is recorded
    as REVIEWER_FAILURE so sign-off can refuse to proceed on an incomplete
    review rather than mistaking silence for approval.
    """
    out: List[Review] = []
    for name in names:
        started = time.time()
        try:
            fn = get_reviewer(name)
            rv = fn(ctx)
            rv.elapsed = time.time() - started
            out.append(rv)
        except Exception as e:                       # noqa: BLE001
            out.append(Review(reviewer=name, stage=ctx.stage,
                              verdict=Verdict.ESCALATE,
                              status=ReviewStatus.REVIEWER_FAILURE,
                              error=f"{type(e).__name__}: {e}",
                              elapsed=time.time() - started))
    return out
