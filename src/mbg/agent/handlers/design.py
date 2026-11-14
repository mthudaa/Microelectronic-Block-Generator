"""design.init, design.status — the AGENTS.md experiment workspace."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from mbg.agent import runio
from mbg.agent.envelope import Result
from mbg.agent.handlers import load_obj

STAGES = ("netlist_check", "pre_simulation", "layout", "drc", "lvs", "pex",
          "post_simulation", "flow")


def init(args, ctx) -> Result:
    from mbg import pdk_profile
    from mbg.output_paths import checked_path, input_path
    r = Result(tool="design.init")
    name = runio.safe_name(args["name"])
    import re
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,127}", name):
        from mbg.agent.cli import UsageError
        raise UsageError("Workspace names use 3-128 lowercase letters, digits and hyphens")
    root = runio.out_root()
    ws = checked_path(root, root / name)
    if ws.exists() and any(ws.iterdir()):
        return r.set("FAIL", "Workspace exists; choose a new name")
    source = input_path(args["netlist"]) if args.get("netlist") else None
    specification = load_obj(args["spec"], "spec") if args.get("spec") else None
    profile = pdk_profile.resolve(args.get("pdk"))
    ws.mkdir(parents=True, exist_ok=True)
    if source:
        shutil.copy2(source, ws / "generated_netlist.spice")
    if args.get("prompt"):
        (ws / "prompt.txt").write_text(args["prompt"] + "\n")
    if specification is not None:
        (ws / "spec.json").write_text(json.dumps(specification, indent=2) + "\n")
    manifest = {"schema": "mbg.workspace/1", "experiment_id": name,
                "pdk": profile.name, "model": args.get("model") or "manual",
                "description": args.get("description", ""), "stages": {}, "artifacts": {}}
    (ws / "experiment.json").write_text(json.dumps(manifest, indent=2) + "\n")
    r.set("PASS", f"workspace {runio.rel(ws)} for {profile.name}")
    r.artifacts = {"workspace": runio.rel(ws), "experiment": runio.rel(ws / "experiment.json")}
    r.next = [f"mbg netlist check --design {name}"]
    return r


def status(args, ctx) -> Result:
    r = Result(tool="design.status")
    name = runio.safe_name(args["name"])
    ws = runio.out_root() / name
    if not ws.is_dir():
        raise FileNotFoundError(f"no workspace {name!r} under {runio.rel(runio.out_root())}")
    stages = {}
    for d in sorted(ws.iterdir()):
        if not d.is_dir():
            continue
        res = runio.read_json(d / runio.RESULT_FILE)
        if res is None:
            job = runio.read_json(d / runio.JOB_FILE)
            stages[d.name] = {"status": "NOT RUN",
                              "job": (job or {}).get("state")}
            continue
        stages[d.name] = {"status": res.get("status"), "summary": res.get("summary"),
                          "elapsed_s": res.get("elapsed_s")}
    r.metrics = {"stages": stages}
    r.artifacts = {"workspace": runio.rel(ws)}
    for f in ("generated_netlist.spice", "spec.json", "experiment.json", "prompt.txt"):
        if (ws / f).is_file():
            r.artifacts[f.split(".")[0]] = runio.rel(ws / f)
    done = [k for k, v in stages.items() if v["status"] == "PASS"]
    bad = [k for k, v in stages.items() if v["status"] in ("FAIL", "PARTIAL")]
    r.set("PASS" if stages and not bad else ("FAIL" if bad else "NOT RUN"),
          f"{name}: passed {done or '-'}; failing {bad or '-'}")
    return r
