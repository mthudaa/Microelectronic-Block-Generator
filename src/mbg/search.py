"""Evidence-driven design search: candidates, branching, selection, memory.

Why this module exists
----------------------
The previous optimizer was a single-point greedy hill-climb with fixed
multiplicative constants. On the regression inverter it went

    scale 1.00 -> PEX bandwidth  63.1 MHz   (target 100 MHz)
    scale 0.90 -> PEX bandwidth  89.1 MHz   improved, still short
    stop (iteration budget exhausted)

and reported NOT_CONVERGED. A measured sweep afterwards showed the answer
was one step further on:

    scale 0.80 -> PEX bandwidth 125.9 MHz, gain 31.3 dB   -- passes both

So the search direction was right and the step policy was wrong: one fixed
step, no continuation, no comparison of alternatives, no memory.

That same sweep also shows why "keep going" is not the fix either. At scale
0.70 bandwidth reaches 224 MHz but gain falls to 26.2 dB and the *gain*
constraint breaks; at 0.50 bandwidth is non-monotonic. The design space is
multi-objective and not smooth, so a step has to be **measured and compared**,
never extrapolated.

The model here is therefore branch-and-compare:

    best design
      +-- candidate A  (different hypothesis / step)
      +-- candidate B
      +-- candidate C
            |
      evaluate each independently, score against ALL specs
            |
      promote the winner, archive the rest, roll back if none helps

Candidates are evaluated in isolated state, so a bad branch cannot corrupt
the incumbent, and each candidate's effect is attributed to that candidate
alone — which is what makes the recommendation ledger meaningful.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from mbg.specs import Spec, SpecReport, evaluate_specs

__all__ = [
    "Candidate", "CandidateResult", "DesignMemory", "SearchState",
    "SearchStrategy", "HeuristicStrategy", "LineSearchStrategy",
    "SensitivityStrategy", "CompositeStrategy", "default_strategy",
    "score_report", "select_best", "ParetoArchive",
]


# ── scoring ───────────────────────────────────────────────────────────

def score_report(report: SpecReport, specs: Sequence[Spec] = ()) -> float:
    """Total normalised constraint violation. 0.0 means everything passes.

    Deliberately *not* "distance to the failing metric": optimising bandwidth
    while quietly breaking gain has to score worse, not better. Every required
    spec contributes, so a candidate that trades one violation for another is
    visible as such.
    """
    return report.score


def margin_of(report: SpecReport) -> float:
    """Smallest relative margin across passing required specs.

    Distinguishes a design that scrapes past its targets from one that clears
    them comfortably — which matters because PEX and PVT will eat margin.
    """
    ms = [r.margin_pct for r in report.results
          if r.required and r.status == "PASS" and r.margin_pct is not None]
    return min(ms) if ms else 0.0


# ── candidates ────────────────────────────────────────────────────────

@dataclass
class Candidate:
    """One proposed modification, with the reasoning that produced it.

    A candidate is a *hypothesis plus an edit*: it records what is expected to
    happen and what could go wrong, so the measurement afterwards either
    supports or refutes something specific.
    """
    id: str
    design: object                      # mbg.flow.DesignPoint
    hypothesis: str = ""
    change: str = ""
    rationale: str = ""
    expected_effect: str = ""
    risk: str = ""
    target: str = "circuit"             # "circuit" | "layout" | "both"
    params: Dict[str, object] = field(default_factory=dict)
    cost: float = 1.0                   # relative evaluation cost
    source: str = ""                    # which strategy proposed it

    def as_dict(self) -> Dict[str, object]:
        return {"id": self.id, "hypothesis": self.hypothesis,
                "change": self.change, "rationale": self.rationale,
                "expected_effect": self.expected_effect, "risk": self.risk,
                "target": self.target, "params": self.params,
                "source": self.source}


@dataclass
class CandidateResult:
    candidate: Candidate
    ok: bool = False
    metrics: Dict[str, float] = field(default_factory=dict)
    report: Optional[SpecReport] = None
    score: float = float("inf")
    margin: float = 0.0
    error: str = ""
    decision: str = "PENDING"           # ACCEPT | ARCHIVE | REJECT | ERROR
    artifacts: Dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, object]:
        return {**self.candidate.as_dict(),
                "ok": self.ok, "score": None if math.isinf(self.score)
                else round(self.score, 6),
                "margin_pct": round(self.margin, 3),
                "decision": self.decision, "error": self.error,
                "metrics": {k: v for k, v in self.metrics.items()}}


def select_best(results: Sequence[CandidateResult],
                baseline_score: float) -> Tuple[Optional[CandidateResult],
                                                List[CandidateResult]]:
    """Pick the winner and label the rest. Credit goes to one candidate only.

    A candidate is ACCEPTed only if it actually beats the incumbent. Ones that
    ran but did not improve are ARCHIVEd (they are still evidence, and may be
    useful later for a different objective); ones that made things worse are
    REJECTed. If nothing improves, the caller rolls back.
    """
    usable = [r for r in results if r.ok and r.report is not None]
    for r in results:
        if not r.ok:
            r.decision = "ERROR"
    if not usable:
        return None, list(results)

    # Passing everything wins outright; otherwise lowest violation, and use
    # margin to break ties so we prefer the more robust of two equals.
    def key(r: CandidateResult):
        return (0 if (r.report and r.report.passed) else 1, r.score, -r.margin)

    ranked = sorted(usable, key=key)
    winner = ranked[0]
    if winner.score >= baseline_score and not (winner.report
                                               and winner.report.passed):
        # Nothing beat the incumbent.
        for r in usable:
            r.decision = "REJECT" if r.score > baseline_score else "ARCHIVE"
        return None, list(results)

    winner.decision = "ACCEPT"
    for r in ranked[1:]:
        r.decision = "ARCHIVE" if r.score < baseline_score else "REJECT"
    return winner, list(results)


# ── memory ────────────────────────────────────────────────────────────

@dataclass
class DesignMemory:
    """What has been tried, and what it did.

    Two jobs: stop re-proposing moves that never help, and remember measured
    sensitivities so later steps can be sized instead of guessed.
    """
    trials: List[Dict[str, object]] = field(default_factory=list)
    sensitivities: Dict[str, Dict[str, float]] = field(default_factory=dict)
    max_failures: int = 2

    def record(self, result: CandidateResult, baseline_score: float,
               baseline_metrics: Mapping[str, float]) -> None:
        c = result.candidate
        deltas = {}
        for k, v in (result.metrics or {}).items():
            base = baseline_metrics.get(k)
            if base:
                deltas[k] = round(100.0 * (v - base) / abs(base), 3)
        self.trials.append({
            "id": c.id, "source": c.source, "target": c.target,
            "change": c.change, "params": dict(c.params),
            "score_before": round(baseline_score, 6),
            "score_after": None if math.isinf(result.score)
            else round(result.score, 6),
            "delta_pct": deltas, "decision": result.decision,
            "ok": result.ok, "error": result.error,
        })
        # A measured (param, metric) pair is a sensitivity sample.
        knob = c.params.get("knob")
        step = c.params.get("step")
        if knob and step and deltas:
            slot = self.sensitivities.setdefault(str(knob), {})
            for metric, dpct in deltas.items():
                try:
                    slot[metric] = round(dpct / float(step), 4)
                except (TypeError, ZeroDivisionError):
                    pass

    def failures(self, change: str) -> int:
        return sum(1 for t in self.trials
                   if t["change"] == change and t["decision"] in ("REJECT", "ERROR"))

    def exhausted(self, change: str) -> bool:
        helped = any(t["change"] == change and t["decision"] == "ACCEPT"
                     for t in self.trials)
        return (not helped) and self.failures(change) >= self.max_failures

    def sensitivity(self, knob: str, metric: str) -> Optional[float]:
        return self.sensitivities.get(knob, {}).get(metric)

    def as_dict(self) -> Dict[str, object]:
        return {"trials": self.trials, "sensitivities": self.sensitivities}


# ── search state ──────────────────────────────────────────────────────

@dataclass
class SearchState:
    design: object
    report: Optional[SpecReport] = None
    metrics: Dict[str, float] = field(default_factory=dict)
    specs: Sequence[Spec] = ()
    degradation: Sequence = ()
    memory: DesignMemory = field(default_factory=DesignMemory)
    iteration: int = 0
    phase: str = "pex"                  # "pre" | "pex"
    tier: int = 1                       # escalation tier

    @property
    def score(self) -> float:
        return self.report.score if self.report else float("inf")

    def failing(self) -> List[str]:
        if not self.report:
            return []
        return [r.name for r in self.report.results
                if r.required and r.status != "PASS"]


# ── strategies ────────────────────────────────────────────────────────

class SearchStrategy:
    """Proposes candidates for one iteration."""
    name = "base"

    def propose(self, state: SearchState, budget: int) -> List[Candidate]:
        raise NotImplementedError


# Which knob moves which metric, and in which direction. Derived from the
# measured sweep: shrinking device width raises bandwidth and lowers gain.
_KNOB_EFFECT = {
    "width": {"bw_hz": -1, "ugf_hz": -1, "gain_db": +1, "power_w": +1},
}


def _apply_width(design, factor: float, cid: str, hypothesis: str,
                 source: str, expected: str, risk: str) -> Candidate:
    from mbg.flow_runtime import scale_device_widths
    net = scale_device_widths(design.netlist, factor)
    circ = {**getattr(design, "circuit", {}),
            "width_scale": round(float(getattr(design, "circuit", {})
                                       .get("width_scale", 1.0)) * factor, 6)}
    return Candidate(
        id=cid, design=design.evolve(netlist=net, circuit=circ,
                                     note=f"{cid}:w x{factor:g}"),
        hypothesis=hypothesis, change=f"scale device widths x{factor:g}",
        rationale=("device width trades transconductance against parasitic "
                   "capacitance"),
        expected_effect=expected, risk=risk, target="circuit",
        params={"knob": "width", "factor": factor,
                "step": round((factor - 1.0) * 100, 4)},
        source=source)


class HeuristicStrategy(SearchStrategy):
    """First-move strategy: step in the direction the failing metric implies."""
    name = "heuristic"

    def propose(self, state: SearchState, budget: int) -> List[Candidate]:
        failing = set(state.failing())
        if not failing:
            return []
        out: List[Candidate] = []
        wants_smaller = bool({"bw_hz", "ugf_hz"} & failing)
        wants_bigger = "gain_db" in failing
        # When both fail, the two moves conflict; propose both and let the
        # measurement decide rather than picking by intuition.
        factors = []
        if wants_smaller:
            factors += [0.9, 0.8]
        if wants_bigger:
            factors += [1.15, 1.3]
        for i, f in enumerate(factors[:budget]):
            direction = "raise bandwidth" if f < 1 else "raise gain"
            out.append(_apply_width(
                state.design, f, f"H{state.iteration}.{i + 1}",
                hypothesis=(f"the failing metric is limited by device size; "
                            f"scaling widths x{f:g} should {direction}"),
                source=self.name,
                expected=direction,
                risk=("gain falls as widths shrink" if f < 1
                      else "bandwidth falls as widths grow")))
        return out


class LineSearchStrategy(SearchStrategy):
    """Continue along a direction that already produced an improvement.

    This is the move the old optimizer was missing. Once a step helps, the
    next iteration extends it *and* brackets it, so the search can overshoot
    and come back rather than stopping at the first improvement.
    """
    name = "line_search"

    def propose(self, state: SearchState, budget: int) -> List[Candidate]:
        accepted = [t for t in state.memory.trials
                    if t["decision"] == "ACCEPT" and t["params"].get("knob") == "width"]
        if not accepted:
            return []
        last = accepted[-1]
        f = float(last["params"].get("factor", 1.0))
        if f == 1.0:
            return []
        # Extend, repeat, and half-step: bracket the optimum instead of
        # assuming the trend continues. The measured sweep is non-monotonic,
        # so extrapolation alone would be wrong.
        step_sizes = [f * f, f, 1.0 - (1.0 - f) / 2.0] if f < 1 else [f * f, f,
                                                                     1.0 + (f - 1.0) / 2.0]
        out: List[Candidate] = []
        for i, nf in enumerate(step_sizes[:budget]):
            nf = round(nf, 4)
            if abs(nf - 1.0) < 1e-6:
                continue
            out.append(_apply_width(
                state.design, nf, f"L{state.iteration}.{i + 1}",
                hypothesis=("the previous step improved the objective, so the "
                            "optimum lies further along this direction"),
                source=self.name,
                expected="continue the measured improvement",
                risk="overshoot may break a currently passing spec"))
        return out


class SensitivityStrategy(SearchStrategy):
    """Size the next step from measured sensitivity instead of a fixed constant.

    Uses the recorded d(metric)/d(knob) to estimate the step that would close
    the largest remaining violation, then proposes that step plus a
    conservative half of it. Only fires once a sensitivity has been measured.
    """
    name = "sensitivity"

    def propose(self, state: SearchState, budget: int) -> List[Candidate]:
        if not state.report:
            return []
        worst = None
        for r in state.report.results:
            if r.required and r.status == "FAIL" and r.value and r.target:
                need = 100.0 * (r.target - r.value) / abs(r.value)
                if worst is None or abs(need) > abs(worst[1]):
                    worst = (r.name, need)
        if not worst:
            return []
        metric, need_pct = worst
        s = state.memory.sensitivity("width", metric)
        if not s:
            return []
        step_pct = need_pct / s                     # % change in width needed
        step_pct = max(-40.0, min(40.0, step_pct))  # stay in a sane range
        factor = round(1.0 + step_pct / 100.0, 4)
        if abs(factor - 1.0) < 1e-3:
            return []
        out = [_apply_width(
            state.design, factor, f"S{state.iteration}.1",
            hypothesis=(f"measured sensitivity d({metric})/d(width) = {s:.3g} "
                        f"%/% implies a {step_pct:+.1f}% width change closes "
                        f"the remaining {need_pct:+.1f}% gap"),
            source=self.name,
            expected=f"close the {metric} violation in one step",
            risk="the local linear model may not hold that far out")]
        if budget > 1:
            half = round(1.0 + step_pct / 200.0, 4)
            if abs(half - 1.0) > 1e-3:
                out.append(_apply_width(
                    state.design, half, f"S{state.iteration}.2",
                    hypothesis="half of the sensitivity-implied step, in case "
                               "the linear model overshoots",
                    source=self.name, expected=f"partially close {metric}",
                    risk="may not be enough"))
        return out


class CompositeStrategy(SearchStrategy):
    """Escalation: try cheap local moves first, widen the search on stagnation.

    Tier 1 continues a working direction or uses measured sensitivity.
    Tier 2 falls back to the heuristic directions.
    Tier 3 widens to a coarse bracket when local moves have stopped helping.
    """
    name = "composite"

    def __init__(self, strategies: Optional[Sequence[SearchStrategy]] = None):
        self.strategies = list(strategies or [
            SensitivityStrategy(), LineSearchStrategy(), HeuristicStrategy()])

    def propose(self, state: SearchState, budget: int) -> List[Candidate]:
        out: List[Candidate] = []
        seen: set = set()
        for strat in self.strategies:
            if len(out) >= budget:
                break
            for c in strat.propose(state, budget - len(out)):
                key = (c.params.get("knob"), c.params.get("factor"))
                if key in seen or state.memory.exhausted(c.change):
                    continue
                seen.add(key)
                out.append(c)
                if len(out) >= budget:
                    break

        if not out and state.tier >= 3:
            # Local search is stuck: bracket widely and let measurement pick.
            for i, f in enumerate((0.6, 0.75, 1.5)):
                key = ("width", f)
                if key in seen:
                    continue
                out.append(_apply_width(
                    state.design, f, f"W{state.iteration}.{i + 1}",
                    hypothesis="local steps stagnated; sample a wider bracket "
                               "to escape the local region",
                    source="wide_bracket",
                    expected="find a better region of the design space",
                    risk="large moves may break several specs at once"))
        return out[:budget]


def default_strategy() -> SearchStrategy:
    return CompositeStrategy()


# ── Pareto archive ────────────────────────────────────────────────────

@dataclass
class ParetoArchive:
    """A small set of non-dominated designs, for later trade-off decisions."""
    entries: List[Dict[str, object]] = field(default_factory=list)
    limit: int = 8

    def offer(self, result: CandidateResult) -> None:
        if not result.ok or result.report is None:
            return
        m = dict(result.metrics)
        entry = {"id": result.candidate.id, "score": result.score,
                 "margin_pct": result.margin, "metrics": m,
                 "change": result.candidate.change}
        for e in self.entries:
            if self._dominates(e["metrics"], m) and e["score"] <= result.score:
                return
        self.entries = [e for e in self.entries
                        if not (self._dominates(m, e["metrics"])
                                and result.score <= e["score"])]
        self.entries.append(entry)
        self.entries.sort(key=lambda e: e["score"])
        del self.entries[self.limit:]

    @staticmethod
    def _dominates(a: Mapping[str, float], b: Mapping[str, float]) -> bool:
        keys = set(a) & set(b)
        if not keys:
            return False
        return all(a[k] >= b[k] for k in keys) and any(a[k] > b[k] for k in keys)

    def as_list(self) -> List[Dict[str, object]]:
        return list(self.entries)
