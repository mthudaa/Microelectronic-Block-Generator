"""Dual-engine DRC: KLayout as sign-off, Magic as an independent check.

Two engines look at the *same* GDS and their results are reconciled, because
they do not check the same things. Magic's checks come from the
``.magicrc``/techfile rules it happens to implement; KLayout runs the GF180
rule deck the PDK ships (``libs.tech/klayout/tech/drc/gf180mcu.drc``), which
is the foundry-authored deck. Where that deck is available it is the
sign-off authority; Magic remains valuable precisely because it is a
*different* implementation and catches different mistakes.

Three rules the reconciliation exists to enforce:

**A tool error is never zero violations.** A KLayout run that could not read
the layout, or a deck that is missing, reports ``ERROR`` /
``NOT_CONFIGURED`` — never ``CLEAN``. Silence from a checker is not a pass.

**Disagreement is a result, not noise.** Magic failing while KLayout is clean
is reported as ``DRC_DISAGREEMENT`` and blocks sign-off. The two decks差
differ, so a disagreement means somebody has to look — not that the
convenient answer wins.

**Counts are not comparable.** The engines implement different rule sets, so
the reconciliation compares *statuses* and preserves each engine's rule
breakdown separately. It never subtracts one violation count from the other.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from mbg import config as _config

__all__ = [
    "DRCStatus", "SignoffVerdict", "DRCResult", "DRCSignoff",
    "MagicDRC", "KLayoutDRC", "get_engine", "reconcile", "run_dual_drc",
    "klayout_deck", "MIN_KLAYOUT_VERSION",
]

#: The GF180 deck warns that parallel workers before this release are unsafe
#: (KLayout issue #2339), so this is the floor for a sign-off run.
MIN_KLAYOUT_VERSION = (0, 30, 9)

#: Rule groups that are properties of a finished *die*, not of a leaf cell.
#: "Metal1 coverage over the entire die shall be >30%" is satisfied by fill
#: insertion during chip assembly; a standalone 11x30um analog block cannot
#: meet it and is not defective for failing it. Excluding them for cell-level
#: sign-off is a scope decision, not a relaxation — run CHIP_DECKS on the
#: assembled top level, where the rules genuinely apply.
CELL_DECKS = "all,-density,-dummy"
CHIP_DECKS = "all"

#: PDK variant -> deck `variant` switch. gf180mcuD is the project target.
_VARIANTS = {"gf180mcua": "A", "gf180mcub": "B", "gf180mcuc": "C",
             "gf180mcud": "D", "gf180mcue": "E", "gf180mcuf": "F"}


class DRCStatus:
    CLEAN = "CLEAN"
    FAIL = "FAIL"
    ERROR = "ERROR"            # the tool ran but could not produce a verdict
    SKIP = "SKIP"
    NOT_CONFIGURED = "NOT_CONFIGURED"   # no engine / no rule deck


class SignoffVerdict:
    PASS = "PASS"
    FAIL = "FAIL"
    DISAGREEMENT = "DRC_DISAGREEMENT"
    ERROR = "ERROR"
    NOT_CONFIGURED = "CONFIGURATION_FAILURE"


@dataclass
class DRCResult:
    """One engine's verdict on one GDS, with the provenance to prove it."""
    engine: str
    status: str = DRCStatus.NOT_CONFIGURED
    violations: int = -1
    rules: Dict[str, int] = field(default_factory=dict)
    report_path: Optional[str] = None
    log_path: Optional[str] = None
    tool: str = ""
    tool_version: str = ""
    deck: str = ""
    gds_path: str = ""
    gds_sha256: str = ""
    elapsed: float = 0.0
    message: str = ""
    raw: Dict[str, object] = field(default_factory=dict)

    @property
    def clean(self) -> bool:
        return self.status == DRCStatus.CLEAN

    @property
    def conclusive(self) -> bool:
        """Did this engine actually reach a verdict?"""
        return self.status in (DRCStatus.CLEAN, DRCStatus.FAIL)

    def as_dict(self) -> Dict[str, object]:
        return {
            "engine": self.engine, "status": self.status,
            "violations": self.violations, "rules": self.rules,
            "report_path": self.report_path, "log_path": self.log_path,
            "tool": self.tool, "tool_version": self.tool_version,
            "deck": self.deck, "gds": self.gds_path,
            "gds_sha256": self.gds_sha256,
            "elapsed": round(self.elapsed, 3), "message": self.message,
        }

    def summary(self) -> str:
        if self.status == DRCStatus.CLEAN:
            return f"{self.engine}: CLEAN"
        if self.status == DRCStatus.FAIL:
            top = sorted(self.rules.items(), key=lambda kv: -kv[1])[:3]
            detail = ", ".join(f"{r} x{n}" for r, n in top)
            return (f"{self.engine}: FAIL ({self.violations} violation(s))"
                    + (f" — {detail}" if detail else ""))
        return f"{self.engine}: {self.status} — {self.message}"


@dataclass
class DRCSignoff:
    """The reconciled result of every engine that ran."""
    verdict: str = SignoffVerdict.NOT_CONFIGURED
    primary: Optional[DRCResult] = None       # the sign-off authority
    results: List[DRCResult] = field(default_factory=list)
    reason: str = ""
    gds_sha256: str = ""

    @property
    def passed(self) -> bool:
        return self.verdict == SignoffVerdict.PASS

    def get(self, engine: str) -> Optional[DRCResult]:
        for r in self.results:
            if r.engine == engine:
                return r
        return None

    def as_dict(self) -> Dict[str, object]:
        return {"verdict": self.verdict, "reason": self.reason,
                "primary": self.primary.engine if self.primary else None,
                "gds_sha256": self.gds_sha256,
                "results": [r.as_dict() for r in self.results]}

    def report(self) -> str:
        L = ["DRC Verification", "================", ""]
        for r in self.results:
            L.append(f"{r.engine}:")
            L.append(f"  Status      {r.status}")
            if r.violations >= 0:
                L.append(f"  Violations  {r.violations}")
            if r.tool_version:
                L.append(f"  Tool        {r.tool} ({r.tool_version})")
            if r.deck:
                L.append(f"  Deck        {r.deck}")
            if r.message:
                L.append(f"  Note        {r.message}")
            for rule, n in sorted(r.rules.items(), key=lambda kv: -kv[1])[:8]:
                L.append(f"    {rule:<24} {n}")
            L.append("")
        L.append("Final:")
        L.append(f"  {self.verdict}")
        if self.reason:
            L.append(f"  Reason: {self.reason}")
        return "\n".join(L)


# ── deck discovery ────────────────────────────────────────────────────

def klayout_deck(cfg=None) -> Optional[str]:
    """Path to the GF180 KLayout DRC deck shipped with the PDK, if present.

    ``MBG_KLAYOUT_DECK`` overrides it, so a user can point at a newer deck
    without reinstalling the PDK.
    """
    override = os.environ.get("MBG_KLAYOUT_DECK")
    if override:
        return override if os.path.isfile(override) else None
    cfg = cfg or _config.pdk_config()
    cand = cfg.path / "libs.tech" / "klayout" / "tech" / "drc" / "gf180mcu.drc"
    return str(cand) if cand.is_file() else None


def _variant_for(pdk: str) -> Optional[str]:
    return _VARIANTS.get((pdk or "").lower())


def _digest(path: str) -> str:
    from mbg.flow_runtime import file_digest
    return file_digest(path)


# ── engines ───────────────────────────────────────────────────────────

class DRCEngine:
    name = "base"

    def available(self) -> tuple:
        """(ok, reason)."""
        raise NotImplementedError

    def run(self, gds_path: str, cell_name: str, workdir: str,
            timeout: Optional[int] = None) -> DRCResult:
        raise NotImplementedError


class MagicDRC(DRCEngine):
    """Magic's techfile-driven DRC — the independent complementary check."""
    name = "magic"

    def available(self) -> tuple:
        info = _config.resolve_magic()
        return (info.ok, "" if info.ok else info.reason)

    def run(self, gds_path, cell_name, workdir, timeout=None) -> DRCResult:
        from mbg.checks import run_drc as _magic_drc
        cfg = _config.pdk_config()
        res = DRCResult(engine=self.name, gds_path=gds_path,
                        gds_sha256=_digest(gds_path),
                        deck=str(cfg.magic_techfile))
        info = _config.resolve_magic(cfg)
        if not info.ok:
            res.status, res.message = DRCStatus.NOT_CONFIGURED, info.reason
            return res
        res.tool, res.tool_version = info.path or "", info.version_string
        t0 = time.time()
        try:
            raw = _magic_drc(gds_path, cell_name=cell_name, workdir=workdir,
                             timeout=timeout or _config.tool_timeout("magic"))
        except Exception as e:                              # noqa: BLE001
            res.status = DRCStatus.ERROR
            res.message = f"{type(e).__name__}: {e}"
            res.elapsed = time.time() - t0
            return res
        res.elapsed = time.time() - t0
        res.report_path = raw.get("report_path")
        res.log_path = raw.get("log_path")
        res.raw = raw
        status = raw.get("status")
        count = raw.get("error_count", -1)
        if raw.get("layout_load_errors"):
            res.status = DRCStatus.ERROR
            res.message = "; ".join(raw["layout_load_errors"])
        elif status in ("TIMEOUT", "ERROR") or count is None or count < 0:
            res.status = DRCStatus.ERROR
            res.message = raw.get("summary", "Magic DRC did not produce a count")
        else:
            res.violations = int(count)
            res.status = DRCStatus.CLEAN if count == 0 else DRCStatus.FAIL
            for rule in raw.get("rules_violated") or []:
                res.rules[rule] = res.rules.get(rule, 0) + 1
        return res


class KLayoutDRC(DRCEngine):
    """The GF180 foundry rule deck, run headlessly — the sign-off authority.

    Invocation follows the deck's own documented contract:

        klayout -b -r gf180mcu.drc -rd input=<gds> -rd report=<out.lyrdb>
                -rd topcell=<cell> -rd variant=<A..F> -rd run_mode=deep

    The result is a KLayout RDB (``.lyrdb``) database, which is preserved
    alongside the parsed summary — it is what a human opens in KLayout to see
    the markers, and throwing it away would make the failure unactionable.
    """
    name = "klayout"

    def available(self) -> tuple:
        info = _config.resolve_klayout()
        if not info.ok:
            return (False, info.reason)
        if info.version and tuple(info.version[:3]) < MIN_KLAYOUT_VERSION:
            return (False,
                    f"KLayout {info.version_string} is older than "
                    f"{'.'.join(map(str, MIN_KLAYOUT_VERSION))}, which the "
                    f"GF180 deck requires for parallel runs "
                    f"(KLayout issue #2339).")
        deck = klayout_deck()
        if not deck:
            return (False,
                    "the GF180 KLayout DRC deck was not found under "
                    "$PDKPATH/libs.tech/klayout/tech/drc/gf180mcu.drc. "
                    "Set MBG_KLAYOUT_DECK, or reinstall the PDK with "
                    "./scripts/setup_env.sh --pdk.")
        return (True, "")

    def __init__(self, decks: Optional[str] = None):
        #: Which rule groups to run. Defaults to cell scope; override with
        #: MBG_KLAYOUT_DECKS or by passing decks="all" for a full die.
        self.decks = decks or os.environ.get("MBG_KLAYOUT_DECKS", CELL_DECKS)

    def run(self, gds_path, cell_name, workdir, timeout=None) -> DRCResult:
        from mbg.checks import run_tool
        cfg = _config.pdk_config()
        deck = klayout_deck(cfg)
        res = DRCResult(engine=self.name, gds_path=gds_path,
                        gds_sha256=_digest(gds_path), deck=deck or "")
        ok, why = self.available()
        if not ok:
            res.status, res.message = DRCStatus.NOT_CONFIGURED, why
            return res

        info = _config.resolve_klayout()
        res.tool, res.tool_version = info.path or "", info.version_string
        res.raw["decks"] = self.decks
        variant = _variant_for(cfg.pdk)
        if not variant:
            res.status = DRCStatus.NOT_CONFIGURED
            res.message = (f"no GF180 deck variant is defined for PDK "
                           f"{cfg.pdk!r}; expected one of {sorted(_VARIANTS)}")
            return res

        os.makedirs(workdir, exist_ok=True)
        report = os.path.join(workdir, f"{cell_name}.klayout.lyrdb")
        argv = [info.path, "-b", "-r", deck,
                "-rd", f"input={os.path.abspath(gds_path)}",
                "-rd", f"report={report}",
                "-rd", f"topcell={cell_name}",
                "-rd", f"variant={variant}",
                "-rd", "run_mode=deep",
                "-rd", f"decks={self.decks}",
                "-rd", f"threads={os.environ.get('MBG_KLAYOUT_THREADS', 'max')}",
                # workers=1: the deck warns that parallel runners below
                # KLayout 0.30.9 hit issue #2339, and one worker is safe on
                # every supported version.
                "-rd", "workers=1"]

        t0 = time.time()
        st = run_tool("klayout", argv, stage="klayout_drc", workdir=workdir,
                      timeout=timeout or _config.tool_timeout("klayout"))
        res.elapsed = time.time() - t0
        res.log_path = st.get("log")
        blob = st.get("output", "")

        if st["status"] == "TIMEOUT":
            res.status = DRCStatus.ERROR
            res.message = st.get("message", "KLayout DRC timed out")
            return res
        if st["status"] == "ERROR":
            res.status = DRCStatus.ERROR
            res.message = st.get("message", "KLayout could not be launched")
            return res

        # A missing or unparsable database is an ERROR, never a clean run.
        # This is the specific failure mode that must not look like zero
        # violations: KLayout exits 0 on some input errors.
        if not os.path.isfile(report):
            res.status = DRCStatus.ERROR
            res.message = ("KLayout produced no report database — the layout "
                           "was probably not read. "
                           + _first_error(blob))
            return res
        try:
            violations, rules = parse_lyrdb(report)
        except Exception as e:                              # noqa: BLE001
            res.status = DRCStatus.ERROR
            res.message = f"could not parse {os.path.basename(report)}: {e}"
            return res

        res.report_path = report
        res.violations = violations
        res.rules = rules
        res.status = DRCStatus.CLEAN if violations == 0 else DRCStatus.FAIL
        # The GF180 deck deliberately exits 0 even with violations (the
        # exit() call is commented out for LibreLane), so the database is the
        # only trustworthy verdict. A non-zero exit therefore means something
        # went wrong, not that DRC failed.
        if st.get("returncode") not in (0, None) and violations == 0:
            # Non-zero exit with an empty database is not a clean result.
            res.status = DRCStatus.ERROR
            res.message = (f"KLayout exited {st.get('returncode')} with an "
                           f"empty database. " + _first_error(blob))
        return res


def _first_error(blob: str) -> str:
    for line in (blob or "").splitlines():
        low = line.lower()
        if any(k in low for k in ("error", "cannot", "unable", "no such",
                                  "not found", "abort")):
            return line.strip()[:180]
    return ""


def parse_lyrdb(path: str) -> tuple:
    """Read a KLayout RDB. Returns (violation_count, {rule: count}).

    The RDB groups items by category; the category name is the rule. Parsed
    with the stdlib so no KLayout Python module is required to read a result
    produced by the executable.
    """
    rules: Dict[str, int] = {}
    total = 0
    # Categories can nest (parent/child); the leaf carries the rule name.
    tree = ET.parse(path)
    root = tree.getroot()
    for item in root.iter("item"):
        cat = item.findtext("category") or ""
        cat = cat.strip().strip("'\"")
        if "/" in cat:
            cat = cat.rsplit("/", 1)[-1]
        rules[cat or "unnamed"] = rules.get(cat or "unnamed", 0) + 1
        total += 1
    return total, rules


_ENGINES = {"magic": MagicDRC, "klayout": KLayoutDRC}


def get_engine(name: str, **kw) -> DRCEngine:
    try:
        return _ENGINES[name](**kw)
    except KeyError:
        raise ValueError(f"unknown DRC engine {name!r}; "
                         f"expected one of {sorted(_ENGINES)}")


# ── reconciliation ────────────────────────────────────────────────────

def reconcile(results: Sequence[DRCResult], *,
              primary: str = "klayout",
              require: Sequence[str] = ("magic", "klayout")) -> DRCSignoff:
    """Combine engine results into one sign-off verdict.

    Policy, in order:

    ==============================  ==========================
    Any required engine ERROR        ``ERROR``
    Any required engine missing      ``CONFIGURATION_FAILURE``
    Primary (KLayout) FAIL           ``FAIL``
    Secondary FAIL, primary CLEAN    ``DRC_DISAGREEMENT``
    All CLEAN                        ``PASS``
    ==============================  ==========================

    A disagreement is *not* a pass. The two decks are different
    implementations, so Magic finding something KLayout did not is a reason to
    investigate, not to overrule Magic with the more convenient answer.
    """
    s = DRCSignoff(results=list(results))
    by = {r.engine: r for r in results}
    s.primary = by.get(primary)
    for r in results:
        if r.gds_sha256:
            s.gds_sha256 = r.gds_sha256
            break

    # All engines must have looked at the same layout.
    shas = {r.gds_sha256 for r in results if r.gds_sha256}
    if len(shas) > 1:
        s.verdict = SignoffVerdict.ERROR
        s.reason = ("the engines ran on different GDS revisions "
                    f"({', '.join(sorted(shas))}) — results are not comparable")
        return s

    missing = [e for e in require if e not in by]
    unconfigured = [r.engine for r in results
                    if r.status == DRCStatus.NOT_CONFIGURED and r.engine in require]
    if missing or unconfigured:
        s.verdict = SignoffVerdict.NOT_CONFIGURED
        names = missing + unconfigured
        detail = "; ".join(by[e].message for e in unconfigured if by.get(e)
                           and by[e].message)
        s.reason = (f"required DRC engine(s) unavailable: {', '.join(names)}."
                    + (f" {detail}" if detail else "")
                    + " Full sign-off needs every configured engine.")
        return s

    errored = [r for r in results if r.status == DRCStatus.ERROR
               and r.engine in require]
    if errored:
        s.verdict = SignoffVerdict.ERROR
        s.reason = ("; ".join(f"{r.engine}: {r.message}" for r in errored)
                    + " — an engine that could not reach a verdict is not a pass")
        return s

    prim = by.get(primary)
    if prim is not None and prim.status == DRCStatus.FAIL:
        s.verdict = SignoffVerdict.FAIL
        s.reason = (f"{primary} sign-off DRC failed with {prim.violations} "
                    f"violation(s)")
        return s

    others_failed = [r for r in results
                     if r.engine != primary and r.status == DRCStatus.FAIL]
    if others_failed:
        s.verdict = SignoffVerdict.DISAGREEMENT
        names = ", ".join(r.engine for r in others_failed)
        s.reason = (f"{names} reported violations while {primary} did not. "
                    f"The decks are different implementations, so this needs "
                    f"investigation — it is not a pass.")
        return s

    if all(r.status == DRCStatus.CLEAN for r in results if r.engine in require):
        s.verdict = SignoffVerdict.PASS
        s.reason = "all configured DRC engines report clean"
        return s

    s.verdict = SignoffVerdict.ERROR
    s.reason = "inconclusive DRC result"
    return s


def run_dual_drc(gds_path: str, cell_name: Optional[str] = None,
                 workdir: Optional[str] = None, *,
                 engines: Sequence[str] = ("magic", "klayout"),
                 primary: str = "klayout",
                 require: Optional[Sequence[str]] = None,
                 timeout: Optional[int] = None,
                 decks: Optional[str] = None,
                 verbosity: int = 1) -> DRCSignoff:
    """Run every engine on the same GDS and reconcile the verdicts.

    ``decks`` selects the KLayout rule scope; the default is cell-level
    (:data:`CELL_DECKS`). Pass ``decks=CHIP_DECKS`` for an assembled die.
    """
    gds_path = os.path.abspath(gds_path)
    cell = cell_name or os.path.splitext(os.path.basename(gds_path))[0]
    wd = os.path.abspath(workdir or os.path.dirname(gds_path) or ".")
    ver_dir = os.path.join(wd, "verification")
    os.makedirs(ver_dir, exist_ok=True)

    results = []
    for name in engines:
        eng = get_engine(name, decks=decks) if name == "klayout" else get_engine(name)
        r = eng.run(gds_path, cell, ver_dir, timeout=timeout)
        results.append(r)
        if verbosity >= 1:
            print(f"  [DRC] {r.summary()}")

    s = reconcile(results, primary=primary,
                  require=require if require is not None else engines)
    if verbosity >= 1:
        print(f"  [DRC] sign-off: {s.verdict} — {s.reason}")
    try:
        import json
        with open(os.path.join(ver_dir, "drc_summary.json"), "w") as f:
            json.dump(s.as_dict(), f, indent=2, default=str)
            f.write("\n")
    except OSError:
        pass
    return s
