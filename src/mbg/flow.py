"""The MBG design flow: two optimization loops, not one.

The methodology this implements:

    Specification
        -> pre-layout simulation -> evaluate -> tune -> repeat      (LOOP A)
        -> layout -> DRC -> LVS -> PEX extraction
        -> PEX simulation -> evaluate against the SAME specs
        -> tune circuit and/or layout -> regenerate -> repeat       (LOOP B)
        -> COMPLETE

The distinction that matters is between the two loops. A design that meets
its targets in pre-layout simulation is not finished: layout parasitics move
gain, bandwidth and phase margin, and the numbers that count are the ones
measured on the extracted netlist. Treating PEX as a final verification stamp
— "extraction completed, therefore success" — is what this module exists to
stop. PEX is feedback, and a PEX spec miss starts an optimization iteration
rather than ending the run.

Three separations are load-bearing:

* **PEX extraction is not PEX simulation.** Extraction can succeed while the
  design still misses every target; those are different statuses.
* **A tool failure is not a spec failure.** ngspice crashing does not mean the
  gain is too low, and the optimizer must not "tune" in response to it.
* **Verification gates extraction.** DRC or LVS failing means PEX and PEX
  simulation are SKIPPED, never run on a layout known to be wrong.

The driver takes its real work as injectable callables (:class:`FlowHooks`),
so the loop logic is testable without a PDK and the same code path runs in
production.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field, replace
from typing import Callable, Dict, List, Mapping, Optional, Sequence

from mbg.specs import (Spec, SpecReport, Degradation, evaluate_specs,
                       compare_degradation, format_spec_table)

__all__ = [
    "Stage", "Outcome", "Failure", "DesignPoint", "LayoutResult",
    "FlowHooks", "FlowConfig", "IterationRecord", "FlowResult", "DesignFlow",
    "run_flow",
]


class Stage:
    SPECIFICATION = "SPECIFICATION"
    PRE_SIMULATION = "PRE_SIMULATION"
    PRE_EVALUATION = "PRE_EVALUATION"
    PRE_OPTIMIZATION = "PRE_OPTIMIZATION"
    LAYOUT_GENERATION = "LAYOUT_GENERATION"
    DRC = "DRC"
    LVS = "LVS"
    PEX_EXTRACTION = "PEX_EXTRACTION"
    PEX_SIMULATION = "PEX_SIMULATION"
    PEX_EVALUATION = "PEX_EVALUATION"
    POST_LAYOUT_OPTIMIZATION = "POST_LAYOUT_OPTIMIZATION"
    FINAL_VERIFICATION = "FINAL_VERIFICATION"
    COMPLETE = "COMPLETE"


class Outcome:
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"
    ERROR = "ERROR"
    TIMEOUT = "TIMEOUT"
    NOT_CONVERGED = "NOT_CONVERGED"


class Failure:
    """Why a run stopped. Agents branch on this, so the categories are coarse
    and mutually exclusive rather than descriptive."""
    NONE = "NONE"
    TOOL_FAILURE = "TOOL_FAILURE"                    # Magic/netgen/ngspice broke
    DESIGN_FAILURE = "DESIGN_FAILURE"                # ran out of iterations
    SPEC_FAILURE = "SPEC_FAILURE"                    # simulated fine, missed target
    VERIFICATION_FAILURE = "VERIFICATION_FAILURE"    # DRC/LVS said no
    TIMEOUT = "TIMEOUT"
    CONFIGURATION_FAILURE = "CONFIGURATION_FAILURE"  # bad inputs, missing specs


@dataclass
class DesignPoint:
    """One candidate design: the netlist plus the knobs allowed to move.

    ``circuit`` and ``layout`` are kept apart on purpose. Post-layout tuning
    is not only transistor sizing — widening a parasitic-sensitive net or
    constraining a matched pair is a layout action, and an optimizer that can
    only resize devices cannot fix a routing-induced problem.
    """
    netlist: str = ""
    cell: str = ""
    circuit: Dict[str, object] = field(default_factory=dict)
    layout: Dict[str, object] = field(default_factory=dict)
    note: str = ""

    def evolve(self, **kw) -> "DesignPoint":
        return replace(self, **kw)


@dataclass
class LayoutResult:
    """Outcome of building and verifying one layout."""
    ok: bool = False
    gds_path: Optional[str] = None
    pex_netlist: Optional[str] = None
    drc: str = Outcome.SKIP
    lvs: str = Outcome.SKIP
    pex_extraction: str = Outcome.SKIP
    failure: str = Failure.NONE
    message: str = ""
    raw: Dict[str, object] = field(default_factory=dict)


@dataclass
class FlowHooks:
    """The real work, injected.

    Every hook may raise; the driver converts an exception into a
    TOOL_FAILURE rather than letting it look like a design problem.

    simulate_pre(design)            -> Mapping[str, float]   measured metrics
    build_layout(design)            -> LayoutResult
    simulate_pex(design, layout)    -> Mapping[str, float]
    tune_pre(design, report)        -> DesignPoint
    tune_post(design, report, degradation) -> DesignPoint
    """
    simulate_pre: Callable[[DesignPoint], Mapping[str, float]]
    build_layout: Callable[[DesignPoint], LayoutResult]
    simulate_pex: Callable[[DesignPoint, LayoutResult], Mapping[str, float]]
    tune_pre: Optional[Callable[[DesignPoint, SpecReport], DesignPoint]] = None
    tune_post: Optional[Callable[[DesignPoint, SpecReport, List[Degradation]],
                                 DesignPoint]] = None
    #: Optional. Given the current search state, return several candidate
    #: designs to evaluate independently. When present the flow branches:
    #: it measures each candidate, promotes the winner and archives the rest,
    #: instead of committing to a single guessed edit.
    propose_candidates: Optional[Callable[..., List[object]]] = None


@dataclass
class FlowConfig:
    specs: Sequence[Spec] = ()
    pex_specs: Optional[Sequence[Spec]] = None   # defaults to `specs`
    max_pre_iterations: int = 10
    max_pex_iterations: int = 8
    # Stop early when tuning stops helping. Counted on the spec score, so it
    # notices "no longer improving" even while individual metrics wobble.
    patience: int = 3
    min_improvement: float = 1e-9
    #: Candidates evaluated per PEX iteration. >1 turns the single-point
    #: hill-climb into branch-and-compare, which is what lets a step be
    #: chosen by measurement rather than by a fixed constant.
    candidates_per_iteration: int = 3
    outdir: Optional[str] = None
    verbosity: int = 1
    skip_layout: bool = False       # pre-layout only (diagnostic mode)

    def specs_for_pex(self) -> Sequence[Spec]:
        return self.pex_specs if self.pex_specs is not None else self.specs


@dataclass
class IterationRecord:
    phase: str                     # "pre_layout" | "pex"
    iteration: int
    spec_pass: bool = False
    score: Optional[float] = None
    status: str = Outcome.FAIL
    drc: Optional[str] = None
    lvs: Optional[str] = None
    pex_extraction: Optional[str] = None
    pex_simulation: Optional[str] = None
    failure: str = Failure.NONE
    message: str = ""
    metrics: Dict[str, object] = field(default_factory=dict)
    degradation: List[Dict[str, object]] = field(default_factory=list)
    elapsed: float = 0.0

    def as_dict(self) -> Dict[str, object]:
        d = {k: v for k, v in self.__dict__.items() if v is not None}
        d["elapsed"] = round(self.elapsed, 3)
        return d


@dataclass
class FlowResult:
    cell: str = ""
    status: str = Outcome.FAIL
    stage: str = Stage.SPECIFICATION
    failure: str = Failure.NONE
    message: str = ""
    pre_layout: List[IterationRecord] = field(default_factory=list)
    pex: List[IterationRecord] = field(default_factory=list)
    best_pre: Optional[SpecReport] = None
    best_pex: Optional[SpecReport] = None
    best_pre_design: Optional[DesignPoint] = None
    best_pex_design: Optional[DesignPoint] = None
    best_pex_iteration: Optional[int] = None
    # The layout belonging to the BEST iteration, not merely the last one.
    # Reporting best-iteration specs beside last-iteration DRC/LVS would join
    # two different designs; keeping both makes the mismatch impossible.
    best_pex_layout: Optional[LayoutResult] = None
    final_layout: Optional[LayoutResult] = None
    candidates: List[Dict[str, object]] = field(default_factory=list)
    rollbacks: List[Dict[str, object]] = field(default_factory=list)
    degradation: List[Degradation] = field(default_factory=list)
    elapsed: float = 0.0

    @property
    def converged(self) -> bool:
        return self.status == Outcome.PASS

    def as_dict(self) -> Dict[str, object]:
        return {
            "cell": self.cell,
            "status": self.status,
            "stage": self.stage,
            "failure": self.failure,
            "message": self.message,
            "elapsed": round(self.elapsed, 3),
            "pre_layout": [r.as_dict() for r in self.pre_layout],
            "pex": [r.as_dict() for r in self.pex],
            "best_pre": self.best_pre.as_dict() if self.best_pre else None,
            "best_pex": self.best_pex.as_dict() if self.best_pex else None,
            "best_pex_iteration": self.best_pex_iteration,
            "degradation": [d.__dict__ for d in self.degradation],
        }

    def write_history(self, path: str) -> str:
        os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.as_dict(), f, indent=2, sort_keys=False, default=str)
            f.write("\n")
        return path

    def summary(self) -> str:
        """The end-of-run report."""
        L = []
        L.append(f"Design: {self.cell or '(unnamed)'}")
        L.append("")
        L.append("Pre-layout")
        L.append("------------")
        L.append(f"Iterations: {len(self.pre_layout)}")
        L.append(f"Final status: "
                 f"{'PASS' if (self.best_pre and self.best_pre.passed) else 'FAIL'}")
        L.append("")
        L.append("Post-layout / PEX")
        L.append("-----------------")
        L.append(f"Iterations: {len(self.pex)}")
        L.append(f"Final status: "
                 f"{'PASS' if (self.best_pex and self.best_pex.passed) else 'FAIL'}")
        if self.best_pex_iteration:
            L.append(f"Best iteration: {self.best_pex_iteration}")

        if self.best_pre or self.best_pex:
            L.append("")
            L.append(self._metric_table())

        if self.final_layout:
            L.append("")
            L.append("Verification")
            L.append("------------")
            L.append(f"DRC: {self.final_layout.drc}")
            L.append(f"LVS: {self.final_layout.lvs}")
            L.append(f"PEX extraction: {self.final_layout.pex_extraction}")

        L.append("")
        L.append("Result:")
        L.append(f"  {self.status}"
                 + (f" ({self.failure})" if self.failure != Failure.NONE else ""))
        if self.message:
            L.append(f"  {self.message}")
        return "\n".join(L)

    def _metric_table(self) -> str:
        first_pex = self.pex[0].metrics if self.pex else {}
        names, rows = [], []
        for src in (self.best_pex, self.best_pre):
            if src:
                for r in src.results:
                    if r.name not in names:
                        names.append(r.name)
        for name in names:
            pre = self.best_pre.get(name) if self.best_pre else None
            fin = self.best_pex.get(name) if self.best_pex else None
            init = (first_pex.get("metrics", {}) or {}).get(name, {})
            rows.append((
                name,
                _v(pre.value if pre else None, pre.unit if pre else ""),
                _v(init.get("value"), fin.unit if fin else ""),
                _v(fin.value if fin else None, fin.unit if fin else ""),
                f"{fin.op} {fin.target:g}{fin.unit}" if fin else "-",
                (fin.status if fin else "-"),
            ))
        if not rows:
            return ""
        hdr = ("Metric", "Pre-layout", "PEX Initial", "PEX Final", "Target", "")
        w = [max(len(str(r[i])) for r in rows + [hdr]) for i in range(6)]
        out = ["  ".join(h.ljust(w[i]) for i, h in enumerate(hdr)).rstrip(),
               "-" * (sum(w) + 10)]
        for r in rows:
            out.append("  ".join(str(c).ljust(w[i]) for i, c in enumerate(r)).rstrip())
        return "\n".join(out)


def _v(value, unit=""):
    if value is None:
        return "-"
    return f"{value:.4g}{unit}"


class DesignFlow:
    """Drives the two optimization loops."""

    def __init__(self, hooks: FlowHooks, config: FlowConfig):
        self.hooks = hooks
        self.cfg = config

    # -- diagnostics --
    def log(self, level: int, msg: str) -> None:
        if self.cfg.verbosity >= level:
            print(msg)

    def _specs_block(self, report: SpecReport) -> None:
        if self.cfg.verbosity >= 1:
            print("\n[SPECS]")
            print(format_spec_table(report))
            print("")

    # -- entry point --
    def run(self, design: DesignPoint) -> FlowResult:
        started = time.time()
        res = FlowResult(cell=design.cell)

        if not self.cfg.specs:
            res.status = Outcome.ERROR
            res.failure = Failure.CONFIGURATION_FAILURE
            res.message = ("no target specifications were given, so there is "
                           "nothing to optimise against. Pass FlowConfig("
                           "specs=[Spec(...), ...]).")
            res.elapsed = time.time() - started
            return res

        design = self._loop_pre_layout(design, res)
        if res.status in (Outcome.ERROR, Outcome.TIMEOUT):
            res.elapsed = time.time() - started
            self._finish(res)
            return res
        if res.failure == Failure.DESIGN_FAILURE and not (
                res.best_pre and res.best_pre.passed):
            # Pre-layout never converged. Going to layout would burn EDA time
            # on a circuit already known to miss its targets.
            res.status = Outcome.NOT_CONVERGED
            res.stage = Stage.PRE_OPTIMIZATION
            res.elapsed = time.time() - started
            self._finish(res)
            return res

        if self.cfg.skip_layout:
            res.stage = Stage.PRE_EVALUATION
            res.status = Outcome.PASS if (res.best_pre and res.best_pre.passed) \
                else Outcome.FAIL
            res.message = "skip_layout=True: stopped after pre-layout evaluation"
            res.elapsed = time.time() - started
            self._finish(res)
            return res

        self._loop_pex(design, res)
        res.elapsed = time.time() - started
        self._finish(res)
        return res

    # -- LOOP A --
    def _loop_pre_layout(self, design: DesignPoint, res: FlowResult) -> DesignPoint:
        best_score = float("inf")
        stagnant = 0

        for i in range(1, self.cfg.max_pre_iterations + 1):
            t0 = time.time()
            res.stage = Stage.PRE_SIMULATION
            self.log(1, f"[FLOW] Stage: {Stage.PRE_SIMULATION}")
            self.log(1, f"[FLOW] Pre-layout iteration: {i}/{self.cfg.max_pre_iterations}")

            try:
                metrics = self.hooks.simulate_pre(design)
            except Exception as e:
                rec = IterationRecord(phase="pre_layout", iteration=i,
                                      status=Outcome.ERROR,
                                      failure=Failure.TOOL_FAILURE,
                                      message=f"{type(e).__name__}: {e}",
                                      elapsed=time.time() - t0)
                res.pre_layout.append(rec)
                res.status, res.failure = Outcome.ERROR, Failure.TOOL_FAILURE
                res.message = (f"pre-layout simulation failed to run: {e}. "
                               f"This is a tool problem, not a specification "
                               f"miss — no tuning was attempted.")
                self.log(1, f"[ERROR][SIMULATION] {res.message}")
                return design

            res.stage = Stage.PRE_EVALUATION
            report = evaluate_specs(metrics, self.cfg.specs, source="pre_layout")
            self._specs_block(report)

            rec = IterationRecord(
                phase="pre_layout", iteration=i, spec_pass=report.passed,
                score=round(report.score, 6),
                status=Outcome.PASS if report.passed else Outcome.FAIL,
                failure=Failure.NONE if report.passed else Failure.SPEC_FAILURE,
                metrics=report.as_dict(), elapsed=time.time() - t0)
            res.pre_layout.append(rec)

            if report.score < best_score - self.cfg.min_improvement:
                best_score, stagnant = report.score, 0
                res.best_pre, res.best_pre_design = report, design
            else:
                stagnant += 1
                if res.best_pre is None:
                    res.best_pre, res.best_pre_design = report, design

            if report.passed:
                self.log(1, "[FLOW] Pre-layout specifications satisfied.")
                self.log(1, "[FLOW] Starting layout generation.")
                res.failure = Failure.NONE
                return res.best_pre_design or design

            if i >= self.cfg.max_pre_iterations:
                res.failure = Failure.DESIGN_FAILURE
                res.message = (f"pre-layout optimisation did not converge in "
                               f"{self.cfg.max_pre_iterations} iterations")
                break
            if stagnant >= self.cfg.patience:
                res.failure = Failure.DESIGN_FAILURE
                res.message = (f"pre-layout optimisation stopped improving for "
                               f"{stagnant} iterations")
                break
            if self.hooks.tune_pre is None:
                res.failure = Failure.DESIGN_FAILURE
                res.message = ("pre-layout specs not met and no tune_pre hook "
                               "was supplied, so there is nothing to adjust")
                break

            res.stage = Stage.PRE_OPTIMIZATION
            self.log(1, f"[OPTIMIZE] Pre-layout fine-tuning iteration {i + 1}.")
            try:
                design = self.hooks.tune_pre(design, report)
            except Exception as e:
                res.status, res.failure = Outcome.ERROR, Failure.TOOL_FAILURE
                res.message = f"tune_pre raised {type(e).__name__}: {e}"
                return design

        return res.best_pre_design or design

    # -- LOOP B --
    def _loop_pex(self, design: DesignPoint, res: FlowResult) -> None:
        best_score = float("inf")
        stagnant = 0
        pre_report = res.best_pre

        for i in range(1, self.cfg.max_pex_iterations + 1):
            t0 = time.time()
            res.stage = Stage.LAYOUT_GENERATION
            self.log(1, f"[FLOW] Stage: {Stage.LAYOUT_GENERATION}")
            self.log(1, f"[FLOW] PEX iteration: {i}/{self.cfg.max_pex_iterations}")

            try:
                layout = self.hooks.build_layout(design)
            except Exception as e:
                layout = LayoutResult(ok=False, failure=Failure.TOOL_FAILURE,
                                      message=f"{type(e).__name__}: {e}")
            res.final_layout = layout

            rec = IterationRecord(
                phase="pex", iteration=i, drc=layout.drc, lvs=layout.lvs,
                pex_extraction=layout.pex_extraction,
                pex_simulation=Outcome.SKIP, elapsed=time.time() - t0)

            # Verification gates extraction and everything downstream.
            if not layout.ok:
                rec.status = Outcome.FAIL
                rec.failure = layout.failure or Failure.VERIFICATION_FAILURE
                rec.message = layout.message
                res.pex.append(rec)
                self._log_layout_block(layout)

                if rec.failure == Failure.TOOL_FAILURE:
                    res.status, res.failure = Outcome.ERROR, Failure.TOOL_FAILURE
                    res.message = layout.message
                    res.stage = Stage.PEX_EXTRACTION
                    return
                # A verification failure is a design/layout problem: retry via
                # the optimizer if we can, otherwise stop.
                if self.hooks.tune_post is None or i >= self.cfg.max_pex_iterations:
                    res.status = Outcome.FAIL
                    res.failure = rec.failure
                    res.message = layout.message or "layout verification failed"
                    res.stage = Stage.DRC if layout.drc != Outcome.PASS else Stage.LVS
                    return
                res.stage = Stage.POST_LAYOUT_OPTIMIZATION
                design = self._tune_post(design, res, pre_report, [], i)
                if res.status == Outcome.ERROR:
                    return
                continue

            self._log_layout_block(layout)

            # -- PEX SIMULATION: a separate stage from extraction --
            res.stage = Stage.PEX_SIMULATION
            self.log(1, f"[FLOW] Stage: {Stage.PEX_SIMULATION}")
            try:
                metrics = self.hooks.simulate_pex(design, layout)
                rec.pex_simulation = Outcome.PASS
            except Exception as e:
                rec.pex_simulation = Outcome.ERROR
                rec.status = Outcome.ERROR
                rec.failure = Failure.TOOL_FAILURE
                rec.message = f"{type(e).__name__}: {e}"
                res.pex.append(rec)
                res.status, res.failure = Outcome.ERROR, Failure.TOOL_FAILURE
                res.message = (f"PEX simulation failed to run: {e}. The "
                               f"extracted netlist exists but could not be "
                               f"simulated — this is a tool failure, not a "
                               f"specification miss, and no tuning was done.")
                self.log(1, f"[ERROR][PEX_SIMULATION] {res.message}")
                return

            res.stage = Stage.PEX_EVALUATION
            report = evaluate_specs(metrics, self.cfg.specs_for_pex(), source="pex")
            self._specs_block(report)

            degradation: List[Degradation] = []
            if pre_report is not None:
                degradation = compare_degradation(pre_report, report,
                                                  self.cfg.specs_for_pex())
                res.degradation = degradation
                if self.cfg.verbosity >= 1 and degradation:
                    print("[PEX] Pre-layout vs post-layout:")
                    for d in degradation:
                        print(f"  {d.describe()}")
                    print("")

            rec.spec_pass = report.passed
            rec.score = round(report.score, 6)
            rec.status = Outcome.PASS if report.passed else Outcome.FAIL
            rec.failure = Failure.NONE if report.passed else Failure.SPEC_FAILURE
            rec.metrics = report.as_dict()
            rec.degradation = [d.__dict__ for d in degradation]
            rec.elapsed = time.time() - t0
            res.pex.append(rec)

            # Best-design tracking: never lose a better earlier iteration.
            # A passing report is always the best, regardless of the
            # improvement threshold: score 0.0 is not "< best - 1e-9" when the
            # previous best already scored below 1e-9, which used to leave an
            # earlier FAILING report recorded as best on a run that passed —
            # reported to the user as NOT_CONVERGED for a design that met
            # every target.
            improved = report.score < best_score - self.cfg.min_improvement
            if improved or report.passed or res.best_pex is None:
                if improved or report.passed:
                    best_score, stagnant = report.score, 0
                res.best_pex = report
                res.best_pex_design = design
                res.best_pex_layout = layout
                res.best_pex_iteration = i
            else:
                stagnant += 1

            if report.passed:
                res.status = Outcome.PASS
                res.stage = Stage.COMPLETE
                res.failure = Failure.NONE
                res.message = "final design meets PEX-aware specifications"
                self.log(1, "[FLOW] Post-layout specifications satisfied.")
                return

            self.log(1, "[PEX] Post-layout specification target not met.")

            if i >= self.cfg.max_pex_iterations:
                res.status = Outcome.NOT_CONVERGED
                res.failure = Failure.DESIGN_FAILURE
                res.stage = Stage.POST_LAYOUT_OPTIMIZATION
                res.message = (f"PEX-aware optimisation did not converge in "
                               f"{self.cfg.max_pex_iterations} iterations; "
                               f"best result was iteration {res.best_pex_iteration}")
                return
            if stagnant >= self.cfg.patience:
                res.status = Outcome.NOT_CONVERGED
                res.failure = Failure.DESIGN_FAILURE
                res.stage = Stage.POST_LAYOUT_OPTIMIZATION
                res.message = (f"PEX-aware optimisation stopped improving for "
                               f"{stagnant} iterations; best result was "
                               f"iteration {res.best_pex_iteration}")
                return
            if self.hooks.tune_post is None:
                res.status = Outcome.FAIL
                res.failure = Failure.SPEC_FAILURE
                res.stage = Stage.PEX_EVALUATION
                res.message = ("PEX specifications not met and no tune_post "
                               "hook was supplied, so no fine-tuning was "
                               "attempted")
                return

            res.stage = Stage.POST_LAYOUT_OPTIMIZATION
            self.log(1, f"[OPTIMIZE] Entering PEX-aware fine-tuning iteration {i + 1}.")

            # Roll back before tuning again. Continuing from an iteration that
            # was worse than the incumbent accumulates harmful edits: the next
            # step compounds the regression instead of correcting it.
            if (res.best_pex_design is not None
                    and report.score > best_score + self.cfg.min_improvement):
                res.rollbacks.append({
                    "at_iteration": i, "from_score": round(report.score, 6),
                    "to_iteration": res.best_pex_iteration,
                    "to_score": round(best_score, 6)})
                self.log(1, f"[ROLLBACK] iteration {i} scored "
                            f"{report.score:.4g} > best {best_score:.4g}; "
                            f"resuming from iteration {res.best_pex_iteration}")
                design = res.best_pex_design

            design = self._advance(design, res, pre_report, degradation, i,
                                   report, best_score)
            if res.status == Outcome.ERROR:
                return

    def _advance(self, design, res, pre_report, degradation, i, report,
                 best_score):
        """Produce the next design, by branching when we can.

        With a ``propose_candidates`` hook the flow evaluates several distinct
        edits against the *same* baseline and keeps the measured winner. That
        is what makes credit assignment meaningful: each candidate is scored
        on its own, so an improvement is attributable to one change rather
        than shared out among everything applied that iteration.

        Without the hook it falls back to the single-edit tuner.
        """
        if self.hooks.propose_candidates is None:
            return self._tune_post(design, res, pre_report, degradation, i,
                                   current=report)
        try:
            picked, records = self.hooks.propose_candidates(
                design=design, report=report, degradation=degradation,
                iteration=i, baseline_score=report.score,
                budget=self.cfg.candidates_per_iteration)
        except Exception as e:
            res.status, res.failure = Outcome.ERROR, Failure.TOOL_FAILURE
            res.message = f"candidate proposal raised {type(e).__name__}: {e}"
            return design
        res.candidates.extend(records or [])
        if picked is not None:
            return picked
        # Nothing beat the incumbent: fall back to the tuner so the search
        # still moves rather than stalling on an exhausted candidate set.
        return self._tune_post(design, res, pre_report, degradation, i,
                               current=report)

    def _tune_post(self, design, res, pre_report, degradation, i,
                   current: Optional[SpecReport] = None) -> DesignPoint:
        try:
            # The tuner is deciding what to change about THIS design, so it
            # needs this iteration's measurement. Passing the best-so-far
            # report meant the failing-metric set could describe a different
            # iteration than the design being modified.
            report = current if current is not None else (
                res.best_pex or SpecReport())
            return self.hooks.tune_post(design, report, degradation)
        except Exception as e:
            res.status, res.failure = Outcome.ERROR, Failure.TOOL_FAILURE
            res.message = f"tune_post raised {type(e).__name__}: {e}"
            return design

    def _log_layout_block(self, layout: LayoutResult) -> None:
        if self.cfg.verbosity < 1:
            return
        print(f"[VERIFY] DRC {layout.drc}")
        print(f"[VERIFY] LVS {layout.lvs}")
        print(f"[PEX] Extraction {layout.pex_extraction}")
        if not layout.ok and layout.message:
            print(f"[PEX] downstream stages SKIPPED — {layout.message}")

    def _finish(self, res: FlowResult) -> None:
        if self.cfg.outdir:
            try:
                res.write_history(os.path.join(self.cfg.outdir, "history.json"))
            except OSError:
                pass
        if self.cfg.verbosity >= 1:
            print("")
            print(res.summary())


def run_flow(design: DesignPoint, hooks: FlowHooks,
             config: FlowConfig) -> FlowResult:
    """Convenience wrapper around :class:`DesignFlow`."""
    return DesignFlow(hooks, config).run(design)
