"""The result envelope every agent tool returns.

    {
      "schema":  "mbg.result/1",
      "tool":    "layout.generate",
      "ok":      true,                # false only when the TOOL broke
      "status":  "PASS",              # PASS | FAIL | PARTIAL | NOT RUN | NOT AVAILABLE
      "summary": "one line a human or an agent can act on",
      "metrics": {...},               # small, flat-ish numbers
      "artifacts": {"gds": "outputs/.../cell.gds", ...},
      "issues": [{"code", "severity", "message", "hint"}],   # at most 20
      "next":    ["mbg verify lvs --gds ...", ...],          # suggested calls
      "run_dir": "outputs/runs/...",
      "elapsed_s": 1.2
    }

``ok`` and ``status`` answer different questions. ``status`` is the verdict
on the *design* using the project's five labels (AGENTS.md); ``ok=false``
means the tool itself could not do its job (bad input, a crash), and then
``error`` says why. A design that fails LVS is ``ok=true, status=FAIL``.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

SCHEMA = "mbg.result/1"
STATUSES = ("PASS", "FAIL", "PARTIAL", "NOT RUN", "NOT AVAILABLE")
SEVERITIES = ("error", "warning", "info")
MAX_ISSUES = 20

#: Process exit codes, so a shell-only agent can branch without parsing JSON.
EXIT = {"PASS": 0, "FAIL": 1, "PARTIAL": 1, "NOT RUN": 3, "NOT AVAILABLE": 3}
EXIT_USAGE = 2
EXIT_RUNNING = 4


@dataclass
class Result:
    tool: str
    status: str = "NOT RUN"
    summary: str = ""
    ok: bool = True
    metrics: Dict[str, Any] = field(default_factory=dict)
    artifacts: Dict[str, str] = field(default_factory=dict)
    issues: List[Dict[str, Any]] = field(default_factory=list)
    next: List[str] = field(default_factory=list)
    run_dir: Optional[str] = None
    elapsed_s: Optional[float] = None
    error: Optional[Dict[str, Any]] = None
    job: Optional[Dict[str, Any]] = None
    data: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.status not in STATUSES:
            raise ValueError(f"status {self.status!r} is not one of {STATUSES}")

    # ── building ──────────────────────────────────────────────────────
    def issue(self, code: str, message: str, *, severity: str = "error",
              hint: Optional[str] = None, **extra) -> "Result":
        if severity not in SEVERITIES:
            raise ValueError(f"severity {severity!r} not in {SEVERITIES}")
        d = {"code": code, "severity": severity, "message": message}
        if hint:
            d["hint"] = hint
        d.update({k: v for k, v in extra.items() if v is not None})
        self.issues.append(d)
        return self

    def set(self, status: str, summary: Optional[str] = None) -> "Result":
        if status not in STATUSES:
            raise ValueError(f"status {status!r} is not one of {STATUSES}")
        self.status = status
        if summary is not None:
            self.summary = summary
        return self

    def fail_tool(self, code: str, message: str, *, log: Optional[str] = None,
                  hint: Optional[str] = None) -> "Result":
        """The tool could not run (as opposed to: the design failed)."""
        self.ok = False
        self.status = "NOT RUN"
        self.error = {"code": code, "message": message}
        if log:
            self.error["log"] = log
        if hint:
            self.error["hint"] = hint
        self.summary = self.summary or f"{code}: {message}"
        return self

    @property
    def errors(self) -> List[Dict[str, Any]]:
        return [i for i in self.issues if i.get("severity") == "error"]

    # ── output ────────────────────────────────────────────────────────
    def to_dict(self, max_issues: int = MAX_ISSUES) -> Dict[str, Any]:
        issues = sorted(self.issues, key=lambda i: SEVERITIES.index(i.get("severity", "info")))
        d: Dict[str, Any] = {
            "schema": SCHEMA, "tool": self.tool, "ok": self.ok,
            "status": self.status, "summary": self.summary,
            "metrics": _jsonable(self.metrics),
            "artifacts": {k: str(v) for k, v in self.artifacts.items() if v},
            "issues": _jsonable(issues[:max_issues]),
            "next": list(self.next),
        }
        if len(issues) > max_issues:
            d["issues_truncated"] = len(issues) - max_issues
        if self.data:
            d["data"] = _jsonable(self.data)
        if self.job:
            d["job"] = self.job
        if self.error:
            d["error"] = self.error
        if self.run_dir:
            d["run_dir"] = str(self.run_dir)
        if self.elapsed_s is not None:
            d["elapsed_s"] = round(self.elapsed_s, 3)
        return d

    def to_json(self, pretty: bool = False) -> str:
        return json.dumps(self.to_dict(), indent=2 if pretty else None,
                          separators=None if pretty else (",", ":"))

    def exit_code(self) -> int:
        if self.job and self.job.get("state") in ("queued", "running"):
            return EXIT_RUNNING
        if not self.ok:
            return EXIT_USAGE if (self.error or {}).get("code") == "USAGE" else 3
        return EXIT.get(self.status, 1)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Result":
        r = cls(tool=d.get("tool", "?"), status=d.get("status", "NOT RUN"),
                summary=d.get("summary", ""), ok=d.get("ok", True))
        r.metrics = d.get("metrics", {}) or {}
        r.artifacts = d.get("artifacts", {}) or {}
        r.issues = d.get("issues", []) or []
        r.next = d.get("next", []) or []
        r.run_dir = d.get("run_dir")
        r.elapsed_s = d.get("elapsed_s")
        r.error = d.get("error")
        r.job = d.get("job")
        r.data = d.get("data", {}) or {}
        return r


def _jsonable(obj: Any) -> Any:
    """Make numbers, paths, tuples and dataclasses safe for json.dumps."""
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return float(f"{obj:.6g}")
    if isinstance(obj, (str, int, bool)) or obj is None:
        return obj
    if hasattr(obj, "as_dict"):
        return _jsonable(obj.as_dict())
    if hasattr(obj, "__dataclass_fields__"):
        from dataclasses import asdict
        return _jsonable(asdict(obj))
    try:
        import numpy as np  # noqa: F401
        if hasattr(obj, "item"):
            return _jsonable(obj.item())
    except Exception:
        pass
    return str(obj)
