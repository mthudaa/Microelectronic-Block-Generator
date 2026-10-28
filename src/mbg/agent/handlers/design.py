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
    r = Result(tool="design.init")
    name = runio.safe_name(args["name"])
    from mbg.experiment_manifest import validate_experiment_id
    try:
        validate_experiment_id(name)
    except ValueError:
        from mbg.agent.cli import UsageError
        raise UsageError(f"design name {name!r}: use 3-128 lowercase letters, digits "
                         f"and '-' (it becomes the experiment id)")
    ws = runio.out_root() / name
    if ws.exists() and any(ws.iterdir()):
        r.set("FAIL", f"workspace {runio.rel(ws)} already exists; choose another name")
        r.issue("EXISTS", f"{runio.rel(ws)} is not empty", hint="previous results are "
                "never overwritten; use a new name, e.g. " + name + "_v2")
        return r
    ws.mkdir(parents=True, exist_ok=True)
    prof = pdk_profile.resolve(args.get("pdk"))
    if args.get("netlist"):
        src = Path(args["netlist"])
        if not src.is_file():
            raise FileNotFoundError(f"netlist {args['netlist']!r} not found")
        shutil.copy2(src, ws / "generated_netlist.spice")
    if args.get("prompt"):
        (ws / "prompt.txt").write_text(args["prompt"] + "\n")
    spec = args.get("spec")
    if spec is not None:
        spec_obj = spec if isinstance(spec, str) and not Path(spec).is_file() else load_obj(spec, "spec")
        (ws / "spec.json").write_text(json.dumps(spec_obj, indent=2))
    from mbg.experiment_manifest import ExperimentManifest, PromptLevel
    manifest = ExperimentManifest(
        experiment_id=name, model=args.get("model") or "NOT AVAILABLE",
        prompt_level=PromptLevel(args.get("prompt_level") or "detailed"),
        pdk=prof.name, metadata={"description": args.get("description", ""),
                                 "created_by": "mbg design init"})
    if (ws / "prompt.txt").is_file():
        manifest.set_artifact("prompt", "prompt.txt")
    if (ws / "generated_netlist.spice").is_file():
        manifest.set_artifact("netlist", "generated_netlist.spice")
    try:
        from mbg.config import repo_root
        manifest.write(ws, repository_root=repo_root())
    except ValueError:
        # outside the repository: same content, written directly
        (ws / "experiment.json").write_text(json.dumps(manifest.to_dict(), indent=2) + "\n")
    r.set("PASS", f"workspace {runio.rel(ws)} for {prof.name}")
    r.artifacts = {"workspace": runio.rel(ws), "experiment": runio.rel(ws / "experiment.json")}
    r.next = [f"mbg netlist check --design {name}",
              f"mbg measure vref --design {name}" ,
              f"mbg layout generate --design {name}"]
    if not args.get("netlist"):
        r.next.insert(0, f"write {runio.rel(ws / 'generated_netlist.spice')}")
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
