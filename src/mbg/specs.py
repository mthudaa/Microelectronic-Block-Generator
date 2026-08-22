"""Target specifications, evaluation, and pre-layout vs post-layout degradation.

One evaluator, used by both optimization loops. That is the point: a metric
that "passes" before layout and "fails" after it must be judged by exactly
the same rule, or the comparison means nothing. The same :class:`Spec` list
is handed to the pre-layout evaluation and to the PEX evaluation unless the
caller deliberately overrides it.

    specs = [Spec("gain_db", ">=", 60), Spec("bw_hz", ">=", 15e6)]
    pre  = evaluate_specs({"gain_db": 64.5, "bw_hz": 18.2e6}, specs)
    post = evaluate_specs({"gain_db": 57.8, "bw_hz": 13.4e6}, specs)
    for d in compare_degradation(pre, post):
        print(d.describe())
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Mapping, Optional, Sequence

__all__ = [
    "Spec", "SpecResult", "SpecReport", "Degradation",
    "evaluate_specs", "compare_degradation", "format_spec_table",
]

_OPS = {
    ">=": lambda v, t, tol: v >= t,
    ">":  lambda v, t, tol: v > t,
    "<=": lambda v, t, tol: v <= t,
    "<":  lambda v, t, tol: v < t,
    "==": lambda v, t, tol: abs(v - t) <= (tol if tol is not None else 0.0),
    "~=": lambda v, t, tol: abs(v - t) <= abs(t) * (tol if tol is not None else 0.1),
}


@dataclass(frozen=True)
class Spec:
    """One target the design has to meet.

    ``tol`` applies only to ``==`` (absolute) and ``~=`` (fractional, default
    10%). ``higher_is_better`` is inferred from the operator and is what lets
    degradation analysis report a *direction* rather than just a delta.
    """
    name: str
    op: str
    target: float
    unit: str = ""
    tol: Optional[float] = None
    weight: float = 1.0
    required: bool = True

    def __post_init__(self):
        if self.op not in _OPS:
            raise ValueError(f"unknown comparison {self.op!r}; "
                             f"expected one of {sorted(_OPS)}")

    @property
    def higher_is_better(self) -> Optional[bool]:
        if self.op in (">=", ">"):
            return True
        if self.op in ("<=", "<"):
            return False
        return None

    def check(self, value: float) -> bool:
        return bool(_OPS[self.op](value, self.target, self.tol))

    def describe(self) -> str:
        return f"{self.name} {self.op} {_fmt(self.target)}{self.unit}"


@dataclass
class SpecResult:
    name: str
    value: Optional[float]
    target: float
    op: str
    unit: str = ""
    status: str = "FAIL"          # PASS | FAIL | MISSING
    required: bool = True
    margin: Optional[float] = None       # signed slack, +ve = passing
    margin_pct: Optional[float] = None


@dataclass
class SpecReport:
    """Outcome of checking one set of measurements against the targets."""
    results: List[SpecResult] = field(default_factory=list)
    source: str = ""              # "pre_layout" | "pex" | ...

    @property
    def passed(self) -> bool:
        """True only if every *required* spec passed.

        A missing measurement is never a pass: an absent metric means the
        simulation did not produce it, which is a reason to investigate, not
        to assume the target was met.
        """
        req = [r for r in self.results if r.required]
        return bool(req) and all(r.status == "PASS" for r in req)

    @property
    def failures(self) -> List[SpecResult]:
        return [r for r in self.results if r.required and r.status != "PASS"]

    @property
    def score(self) -> float:
        """How close this design is to meeting everything, lower is better.

        Sum of relative shortfalls over the failing required specs; 0.0 means
        every target is met. Used to decide whether iteration N is better
        than iteration N-1 without needing a single headline metric.
        """
        total = 0.0
        for r in self.results:
            if not r.required or r.status == "PASS":
                continue
            if r.value is None or r.status == "MISSING":
                total += 1.0
                continue
            denom = abs(r.target) if r.target else 1.0
            total += abs(r.target - r.value) / denom
        return total

    def get(self, name: str) -> Optional[SpecResult]:
        for r in self.results:
            if r.name == name:
                return r
        return None

    def as_dict(self) -> Dict[str, object]:
        return {
            "source": self.source,
            "pass": self.passed,
            "score": round(self.score, 6),
            "metrics": {
                r.name: {"value": r.value, "target": r.target, "op": r.op,
                         "unit": r.unit, "status": r.status,
                         "margin": r.margin, "margin_pct": r.margin_pct}
                for r in self.results
            },
        }


def evaluate_specs(metrics: Mapping[str, Optional[float]],
                   specs: Sequence[Spec],
                   source: str = "") -> SpecReport:
    """Check measured values against targets.

    ``metrics`` maps spec name to measured value. A name with no measurement
    (absent, ``None``, or NaN) is reported ``MISSING`` rather than silently
    skipped — that distinction is what stops a broken simulation from looking
    like a passing design.
    """
    report = SpecReport(source=source)
    for spec in specs:
        raw = metrics.get(spec.name)
        value = None
        if raw is not None:
            try:
                value = float(raw)
                if math.isnan(value) or math.isinf(value):
                    value = None
            except (TypeError, ValueError):
                value = None

        if value is None:
            report.results.append(SpecResult(
                name=spec.name, value=None, target=spec.target, op=spec.op,
                unit=spec.unit, status="MISSING", required=spec.required))
            continue

        ok = spec.check(value)
        margin = None
        if spec.higher_is_better is True:
            margin = value - spec.target
        elif spec.higher_is_better is False:
            margin = spec.target - value
        margin_pct = (100.0 * margin / abs(spec.target)
                      if margin is not None and spec.target else None)

        report.results.append(SpecResult(
            name=spec.name, value=value, target=spec.target, op=spec.op,
            unit=spec.unit, status="PASS" if ok else "FAIL",
            required=spec.required,
            margin=margin,
            margin_pct=round(margin_pct, 3) if margin_pct is not None else None))
    return report


@dataclass
class Degradation:
    """What layout parasitics did to one metric."""
    name: str
    pre: Optional[float]
    post: Optional[float]
    unit: str = ""
    delta: Optional[float] = None
    delta_pct: Optional[float] = None
    status: str = "FAIL"            # status of the POST value against target
    worsened: bool = False

    def describe(self) -> str:
        if self.pre is None or self.post is None:
            return f"{self.name}: incomparable (pre={self.pre}, post={self.post})"
        arrow = "worse" if self.worsened else "better/equal"
        pct = f" ({self.delta_pct:+.1f}%)" if self.delta_pct is not None else ""
        return (f"{self.name}: {_fmt(self.pre)}{self.unit} -> "
                f"{_fmt(self.post)}{self.unit}  "
                f"delta {_fmt(self.delta)}{self.unit}{pct}  {arrow}  [{self.status}]")


def compare_degradation(pre: SpecReport, post: SpecReport,
                        specs: Optional[Sequence[Spec]] = None
                        ) -> List[Degradation]:
    """Quantify what changed between pre-layout and post-layout.

    Answers the question a bare "PEX FAIL" leaves open: *which* metrics moved,
    by how much, and in the direction that hurts. Metrics that got worse are
    listed first and are the ones worth spending an optimization iteration on.
    """
    by_name = {s.name: s for s in (specs or [])}
    out: List[Degradation] = []
    for post_r in post.results:
        pre_r = pre.get(post_r.name)
        spec = by_name.get(post_r.name)
        hib = spec.higher_is_better if spec else None

        pre_v = pre_r.value if pre_r else None
        post_v = post_r.value
        delta = pct = None
        worsened = False
        if pre_v is not None and post_v is not None:
            delta = post_v - pre_v
            if pre_v:
                pct = round(100.0 * delta / abs(pre_v), 3)
            if hib is True:
                worsened = delta < 0
            elif hib is False:
                worsened = delta > 0
            else:
                worsened = abs(post_v - (spec.target if spec else 0)) > \
                           abs(pre_v - (spec.target if spec else 0))

        out.append(Degradation(
            name=post_r.name, pre=pre_v, post=post_v, unit=post_r.unit,
            delta=delta, delta_pct=pct, status=post_r.status,
            worsened=worsened))

    # Worst offenders first: failing-and-worsened, then worsened, then the rest.
    out.sort(key=lambda d: (
        not (d.worsened and d.status != "PASS"),
        not d.worsened,
        -(abs(d.delta_pct) if d.delta_pct is not None else 0.0)))
    return out


def _fmt(v: Optional[float]) -> str:
    if v is None:
        return "-"
    a = abs(v)
    if a and (a >= 1e6 or a < 1e-3):
        return f"{v:.4g}"
    return f"{v:.4g}"


def format_spec_table(report: SpecReport, indent: str = "  ") -> str:
    """The ``[SPECS]`` block printed by the flow driver."""
    if not report.results:
        return f"{indent}(no specifications defined)"
    w = max(len(r.name) for r in report.results)
    lines = []
    for r in report.results:
        val = f"{_fmt(r.value)}{r.unit}" if r.value is not None else "not measured"
        tgt = f"{r.op} {_fmt(r.target)}{r.unit}"
        lines.append(f"{indent}{r.name:<{w}}  {val:>14}  {tgt:>14}  {r.status}")
    return "\n".join(lines)
