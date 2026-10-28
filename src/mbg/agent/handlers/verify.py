"""verify.drc, verify.lvs, verify.pex on an existing GDS."""
from __future__ import annotations

from pathlib import Path

from mbg.agent import runio
from mbg.agent.envelope import Result
from mbg.agent.handlers import ensure_pdk, profile_for, record


def _gds(args) -> Path:
    p = Path(args["gds"])
    if not p.is_file():
        raise FileNotFoundError(f"GDS {args['gds']!r} not found")
    return p


def _top_cell(gds: Path, given) -> str:
    if given:
        return given
    import gdstk
    tops = gdstk.read_rawcells(str(gds))
    lib = gdstk.read_gds(str(gds))
    top = lib.top_level()
    return top[0].name if top else next(iter(tops))


def drc(args, ctx) -> Result:
    r = Result(tool="verify.drc")
    prof = profile_for(args)
    if not ensure_pdk(prof, r):
        return r
    gds = _gds(args)
    cell = _top_cell(gds, args.get("cell"))
    from mbg.drc import run_dual_drc
    ctx.stage(f"DRC with {', '.join(prof.drc_engines)}")
    with prof.env():
        s = run_dual_drc(str(gds), cell_name=cell, workdir=str(ctx.run_dir),
                         engines=prof.drc_engines, primary=prof.drc_primary)
    d = s.as_dict()
    r.metrics = {"verdict": d.get("verdict"), "pdk": prof.name, "cell": cell,
                 "engines": {e.get("engine"): {"status": e.get("status"),
                                               "violations": e.get("violations")}
                             for e in d.get("results") or []}}
    for e in d.get("results") or []:
        for rule, n in sorted((e.get("rules") or {}).items(), key=lambda kv: -kv[1])[:10]:
            r.issue("DRC_RULE", f"{e.get('engine')}: {rule} x{n}", rule=rule,
                    engine=e.get("engine"))
        if e.get("status") in ("NOT_CONFIGURED", "ERROR"):
            r.issue("DRC_ENGINE_" + e.get("status"), f"{e.get('engine')}: {e.get('message')}",
                    hint="mbg doctor")
        if e.get("report_path"):
            r.artifacts[f"{e.get('engine')}_report"] = runio.rel(e["report_path"])
    r.artifacts["summary"] = runio.rel(ctx.run_dir / "verification" / "drc_summary.json")
    ok = d.get("verdict") == "PASS"
    r.set("PASS" if ok else "FAIL", f"{cell}: DRC sign-off {d.get('verdict')} — {d.get('reason', '')}"[:300])
    record(args.get("design"), stage="drc", status=r.status,
           artifact=ctx.run_dir / "verification" / "drc_summary.json")
    return r


def lvs(args, ctx) -> Result:
    r = Result(tool="verify.lvs")
    net_path = Path(args["netlist"])
    if not net_path.is_file():
        raise FileNotFoundError(f"netlist {args['netlist']!r} not found")
    text = net_path.read_text()
    prof = profile_for(args, text)
    if not ensure_pdk(prof, r):
        return r
    gds = _gds(args)
    from mbg.agent.handlers import subckt_name
    cell = args.get("cell") or subckt_name(text)
    from mbg.checks import run_lvs
    from mbg.pipeline import _canonical_passive_params
    sch = ctx.run_dir / f"{cell}.spice"
    sch.write_text(_canonical_passive_params(text))
    ctx.stage("extraction + netgen")
    with prof.env():
        res = run_lvs(str(gds), str(sch), cell_name=cell, workdir=str(ctx.run_dir))
    summ = res.get("summary") or {}
    r.metrics = {"match": bool(res.get("match")), "pdk": prof.name, "cell": cell,
                 "device_mismatch": summ.get("device_mismatch"),
                 "net_mismatch": summ.get("net_mismatch"),
                 "property_errors": summ.get("property_errors")}
    if res.get("report_path"):
        r.artifacts["report"] = runio.rel(res["report_path"])
    r.artifacts["schematic"] = runio.rel(sch)
    if res.get("match"):
        r.set("PASS", f"{cell}: LVS match ({summ.get('message', '')})")
    else:
        r.set("FAIL", f"{cell}: {summ.get('message', 'LVS mismatch')}")
        r.issue("LVS_MISMATCH", str(summ.get("message")),
                hint="see artifacts.report; missing devices or split nets are the usual causes")
    record(args.get("design"), stage="lvs", status=r.status, artifact=res.get("report_path"))
    return r


def pex(args, ctx) -> Result:
    r = Result(tool="verify.pex")
    prof = profile_for(args)
    if not ensure_pdk(prof, r):
        return r
    gds = _gds(args)
    cell = _top_cell(gds, args.get("cell"))
    from mbg.checks import run_pex
    ctx.stage("Magic PEX")
    with prof.env():
        res = run_pex(str(gds), cell_name=cell, mode=int(args.get("mode") or 2),
                      workdir=str(ctx.run_dir))
    path = res.get("pex_path")
    if path and Path(path).is_file():
        text = Path(path).read_text()
        caps = sum(1 for l in text.splitlines() if l[:1] in ("C", "c"))
        ress = sum(1 for l in text.splitlines() if l[:1] in ("R", "r"))
        r.metrics = {"pdk": prof.name, "cell": cell, "parasitic_caps": caps,
                     "parasitic_res": ress}
        r.artifacts["pex"] = runio.rel(path)
        r.set("PASS", f"{cell}: extracted {caps} C and {ress} R parasitics")
        r.next = [f"mbg sim run {runio.rel(path)} --analysis op --post-layout"]
    else:
        r.set("FAIL", f"{cell}: {res.get('summary')}")
        r.issue("PEX_FAILED", str(res.get("summary")), log=(res.get("log") or "")[-800:])
    record(args.get("design"), stage="pex", status=r.status,
           artifact=path if path and Path(path).is_file() else None)
    return r
