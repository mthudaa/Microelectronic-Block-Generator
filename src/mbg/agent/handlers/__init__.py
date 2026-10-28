"""Handlers behind the agent tools. Each takes ``(args, ctx)`` and returns a
:class:`mbg.agent.envelope.Result`; see :mod:`mbg.agent.registry` for the
input schemas. Shared helpers live here."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from mbg.agent import runio


def load_obj(value: Any, what: str) -> Any:
    """An inline object, or the JSON file a string names."""
    if value is None or isinstance(value, (dict, list)):
        return value
    p = Path(str(value))
    if p.is_file():
        return json.loads(p.read_text())
    raise FileNotFoundError(f"{what}: {value!r} is neither an object nor a JSON file")


def workspace_netlist(design: Optional[str]) -> Optional[Path]:
    if not design:
        return None
    p = runio.out_root() / runio.safe_name(design) / "generated_netlist.spice"
    return p if p.is_file() else None


def read_netlist(args: Dict[str, Any]) -> Tuple[str, Path]:
    """The netlist text and its path, from --netlist or the design workspace."""
    path = args.get("netlist")
    if path:
        p = Path(path)
        if not p.is_file():
            raise FileNotFoundError(f"netlist {path!r} not found")
        return p.read_text(), p
    ws = workspace_netlist(args.get("design"))
    if ws:
        return ws.read_text(), ws
    from mbg.agent.cli import UsageError
    raise UsageError("no netlist: pass a SPICE file, or --design <name> for a "
                     "workspace that has generated_netlist.spice")


def subckt_name(text: str) -> str:
    m = re.search(r"^\s*\.subckt\s+(\S+)", text, re.IGNORECASE | re.MULTILINE)
    if not m:
        from mbg.agent.cli import UsageError
        raise UsageError("the netlist has no .subckt line")
    return m.group(1)


def subckt_ports(text: str) -> list:
    m = re.search(r"^\s*\.subckt\s+\S+\s+(.*)$", text, re.IGNORECASE | re.MULTILINE)
    return [p for p in (m.group(1).split() if m else []) if "=" not in p]


def profile_for(args: Dict[str, Any], text: Optional[str] = None):
    from mbg import pdk_profile
    if text is not None:
        return pdk_profile.for_netlist(text, args.get("pdk"))
    return pdk_profile.resolve(args.get("pdk"))


def ensure_pdk(profile, result) -> bool:
    """Record NOT AVAILABLE on the result when the PDK is not installed."""
    if profile.installed():
        return True
    result.set("NOT AVAILABLE", f"PDK {profile.name} is not installed at "
                                f"{profile.path()}")
    result.issue("PDK_MISSING", f"{profile.name} not found at {profile.path()}",
                 hint="./install.sh --stage pdk, or set PDK_ROOT to a directory "
                      f"containing {profile.name}/")
    return False


def env_note() -> Dict[str, str]:
    return {k: os.environ.get(k, "") for k in ("PDK", "PDK_ROOT")}


# ── experiment.json bookkeeping ───────────────────────────────────────

_STAGE_MAP = {"pre_simulation": "pre_simulation", "post_simulation": "post_simulation",
              "drc": "drc", "lvs": "lvs", "pex": "pex"}


def record(design: Optional[str], *, stage: Optional[str] = None,
           status: Optional[str] = None, artifact: Any = None,
           netlist_valid: Optional[bool] = None, gds: Any = None) -> None:
    """Update ``outputs/<design>/experiment.json`` if this run belongs to one.

    Uses :class:`mbg.experiment_manifest.ExperimentManifest`, so the record
    keeps the project's schema and its PASS rules. Best effort: a workspace
    outside the repository, or an older hand-written record, is left alone.
    """
    if not design:
        return
    try:
        from mbg.config import repo_root
        from mbg.experiment_manifest import ExperimentManifest
        ws = runio.out_root() / runio.safe_name(design)
        path = ws / "experiment.json"
        if not path.is_file():
            return
        m = ExperimentManifest.load(path, repository_root=repo_root())

        def relp(p):
            return Path(p).resolve().relative_to(ws.resolve()).as_posix()

        if netlist_valid is not None:
            m.mark_netlist(valid=netlist_valid)
        if gds is not None:
            m.mark_gds(generated=bool(gds), artifact_path=relp(gds) if gds else None)
        if stage in _STAGE_MAP and status:
            m.set_stage(_STAGE_MAP[stage], status,
                        artifact_path=relp(artifact) if artifact else None)
        final = m.infer_final_status()
        if final.value == "PASS" and m.api_calls < 1:
            # ExperimentManifest reserves PASS for LLM experiments with a
            # recorded API call. A run driven interactively by an agent has
            # none on record, so it stays PARTIAL and says why.
            from mbg.experiment_manifest import ExperimentStatus
            final = ExperimentStatus.PARTIAL
            m.metadata["final_status_note"] = (
                "every stage PASS; final PASS also needs >= 1 recorded API "
                "call (api_calls), which an agent-driven run does not log")
        m.final_status = final
        m.write(ws, repository_root=repo_root())
    except Exception as e:                                  # noqa: BLE001
        print(f"[WORKSPACE] experiment.json not updated: {type(e).__name__}: {e}")
