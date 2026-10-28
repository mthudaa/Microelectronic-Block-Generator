"""flow.run — netlist to sign-off in one call, built from the other tools.

The stages are exactly the individual tools (netlist.check, measure.<recipe>,
layout.generate), each writing into its own sub-directory of the flow's run
directory, so a failed flow can be resumed stage by stage with the ordinary
commands. Pre- and post-layout metrics are compared with
:func:`mbg.specs.compare_degradation` — PEX is feedback, not a stamp.
"""
from __future__ import annotations

from mbg.agent import registry, runio
from mbg.agent.envelope import Result


def _sub(ctx, name):
    from mbg.agent.cli import Ctx
    d = ctx.run_dir / name
    d.mkdir(parents=True, exist_ok=True)
    return Ctx(tool=ctx.tool, run_dir=d, design=None, log=ctx.log, in_job=ctx.in_job)


def _call(tool_id, args, ctx, sub):
    t = registry.get(tool_id)
    c = _sub(ctx, sub)
    c.tool = t
    ctx.stage(f"{sub}: {tool_id}")
    try:
        r = registry.load_handler(t)(args, c)
    except Exception as e:                                   # noqa: BLE001
        r = Result(tool=tool_id).fail_tool("EXCEPTION", f"{type(e).__name__}: {e}")
    r.run_dir = runio.rel(c.run_dir)
    return r


def run(args, ctx) -> Result:
    r = Result(tool="flow.run")
    base = {k: args[k] for k in ("netlist", "pdk", "design") if args.get(k)}
    recipe = args.get("recipe") or "none"
    rargs = dict(args.get("recipe_args") or {})
    if args.get("spec") is not None:
        rargs.setdefault("spec", args["spec"])
    stages = {}

    chk = _call("netlist.check", dict(base), ctx, "1_netlist_check")
    stages["netlist_check"] = chk.status
    if chk.status == "FAIL" or not chk.ok:
        r.issues.extend(chk.issues)
        r.set("FAIL", f"stopped at netlist check: {chk.summary}")
        r.metrics["stages"] = stages
        return r

    pre = None
    if recipe != "none":
        pre = _call(f"measure.{recipe}", {**base, **rargs}, ctx, "2_pre_layout")
        stages["pre_layout"] = pre.status
        r.metrics["pre_layout"] = {k: v for k, v in pre.metrics.items() if k != "conditions"}
        r.issues.extend(dict(i, stage="pre_layout") for i in pre.issues)

    lay_args = dict(base)
    if args.get("hints") is not None:
        lay_args["hints"] = args["hints"]
    lay = _call("layout.generate", lay_args, ctx, "3_layout")
    stages["layout"] = lay.status
    r.metrics["layout"] = lay.metrics
    r.artifacts.update({f"layout_{k}": v for k, v in lay.artifacts.items()})
    r.issues.extend(dict(i, stage="layout") for i in lay.issues)

    post = None
    pex = lay.artifacts.get("pex")
    if recipe != "none" and pex:
        post_args = {**{k: v for k, v in base.items() if k != "design"},
                     **rargs, "netlist": pex, "post_layout": True}
        post = _call(f"measure.{recipe}", post_args, ctx, "4_post_layout")
        stages["post_layout"] = post.status
        r.metrics["post_layout"] = {k: v for k, v in post.metrics.items() if k != "conditions"}
        r.issues.extend(dict(i, stage="post_layout") for i in post.issues)
        if pre is not None:
            deltas = {}
            for k, v in r.metrics["post_layout"].items():
                pv = r.metrics["pre_layout"].get(k)
                if isinstance(v, (int, float)) and isinstance(pv, (int, float)) \
                        and not isinstance(v, bool):
                    deltas[k] = {"pre": pv, "post": v, "delta": v - pv}
            r.metrics["pre_vs_post"] = deltas
    elif recipe != "none":
        stages["post_layout"] = "NOT RUN"

    r.metrics["stages"] = stages
    signed_off = lay.status == "PASS"
    spec_ok = (post.status == "PASS") if post is not None else (recipe == "none")
    if signed_off and spec_ok:
        r.set("PASS", "layout signed off (DRC/LVS/PEX/internal) and post-layout "
                      "metrics meet the spec" if recipe != "none" else
                      "layout signed off; no measurement recipe requested")
    elif signed_off:
        r.set("PARTIAL", f"layout signed off, post-layout {stages.get('post_layout')}: "
                         f"{post.summary if post else 'not measured'}")
    else:
        r.set("FAIL", f"layout {lay.status}: {lay.summary}")
    r.next = [f"mbg layout view {lay.run_dir}"]
    return r
