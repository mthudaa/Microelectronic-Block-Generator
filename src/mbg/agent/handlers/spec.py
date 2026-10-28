"""spec.check."""
from __future__ import annotations

from mbg.agent.envelope import Result
from mbg.agent.handlers import load_obj


def resolve_specs(spec):
    from mbg.measure import SPEC_PRESETS, parse_spec
    if isinstance(spec, str) and spec in SPEC_PRESETS:
        return parse_spec(spec)
    return parse_spec(load_obj(spec, "spec"))


def apply(r: Result, metrics, spec, source: str = "") -> bool:
    """Evaluate ``spec`` on ``metrics`` into ``r``; return pass/fail."""
    from mbg.specs import evaluate_specs
    specs = resolve_specs(spec)
    rep = evaluate_specs({k: v for k, v in metrics.items()
                          if isinstance(v, (int, float)) and not isinstance(v, bool)},
                         specs, source=source)
    r.data.setdefault("spec", {})[source or "spec"] = rep.as_dict()
    for s in rep.results:
        if s.required and s.status != "PASS":
            val = "missing" if s.value is None else f"{s.value:.4g}"
            r.issue("SPEC_" + s.status, f"{s.name} = {val}{s.unit} does not meet "
                    f"{s.op} {s.target:g}{s.unit}" + (f" ({source})" if source else ""),
                    metric=s.name, value=s.value, target=s.target)
    return rep.passed


def check(args, ctx) -> Result:
    r = Result(tool="spec.check")
    metrics = load_obj(args["metrics"], "metrics")
    if isinstance(metrics, dict) and "metrics" in metrics and isinstance(metrics["metrics"], dict):
        metrics = metrics["metrics"]          # accept a whole envelope / result.json
    ok = apply(r, metrics, args["spec"])
    rep = r.data["spec"]["spec"]
    n = len(rep["metrics"])
    bad = [k for k, v in rep["metrics"].items() if v["status"] != "PASS"]
    if ok:
        r.set("PASS", f"all {n} specs met")
    else:
        r.set("FAIL", f"{len(bad)}/{n} specs not met: {', '.join(bad)}")
    return r
