"""layout.generate, layout.view."""
from __future__ import annotations

import json
from pathlib import Path

from mbg.agent import runio
from mbg.agent.envelope import Result
from mbg.agent.handlers import (ensure_pdk, load_obj, profile_for, read_netlist,
                                record, subckt_name)


def _drc_issues(r: Result, res: dict) -> None:
    drc = res.get("drc") or {}
    rules = drc.get("rules_violated") or []
    if drc and not drc.get("clean"):
        r.issue("DRC_MAGIC", f"Magic DRC: {drc.get('summary')}",
                hint="open the report in artifacts.magic_drc; most layout DRC "
                     "errors come from spacing between devices — try a larger "
                     "placement channel_x/channel_y",
                rules=rules[:10] or None)
    s = res.get("drc_signoff") or {}
    verdict = s.get("verdict")
    if verdict and verdict != "PASS":
        code = "DRC_ENGINE_UNAVAILABLE" if verdict == "CONFIGURATION_FAILURE" else "DRC_SIGNOFF"
        r.issue(code, f"DRC sign-off {verdict}: {s.get('reason', '')}"[:400],
                hint=("run `mbg doctor`; a sign-off engine that did not run is a "
                      "failure, not a pass" if code == "DRC_ENGINE_UNAVAILABLE" else None))
        for eng in s.get("results") or []:
            for rule, n in sorted((eng.get("rules") or {}).items(), key=lambda kv: -kv[1])[:6]:
                r.issue("DRC_RULE", f"{eng.get('engine')}: {rule} x{n}", severity="error",
                        rule=rule, engine=eng.get("engine"))


def _lvs_issues(r: Result, res: dict) -> None:
    lvs = res.get("lvs") or {}
    if lvs.get("match"):
        return
    summ = lvs.get("summary") or {}
    msg = summ.get("message") if isinstance(summ, dict) else str(summ)
    r.issue("LVS_MISMATCH", f"LVS: {msg}",
            hint="compare the extracted netlist (artifacts.extracted) with the "
                 "schematic; missing devices usually mean a device could not be "
                 "built, extra nets usually mean an open route",
            devices=summ.get("device_mismatch") if isinstance(summ, dict) else None,
            nets=summ.get("net_mismatch") if isinstance(summ, dict) else None)


def _connectivity_issues(r: Result, ver: dict) -> None:
    if not ver or ver.get("clean"):
        return
    for kind, key in (("OPEN", "open_details"), ("SHORT", "short_details"),
                      ("NO_ACCESS", "missing_access_details"), ("INTERNAL_DRC", "drc_details")):
        for d in (ver.get(key) or [])[:5]:
            r.issue(kind, str(d), hint={
                "OPEN": "a net did not fully route; see layout view failures",
                "SHORT": "two nets touch; move the devices apart with hints",
                "NO_ACCESS": "a device terminal has no reachable port",
            }.get(kind))


def generate(args, ctx) -> Result:
    r = Result(tool="layout.generate")
    text, path = read_netlist(args)
    prof = profile_for(args, text)
    if not ensure_pdk(prof, r):
        return r
    from mbg.netlist_check import check_netlist
    pre = check_netlist(text, prof)
    blocking = [i for i in pre["issues"] if i["severity"] == "error"
                or i["code"] == "LAYOUT_UNSUPPORTED"]
    if blocking:
        for i in blocking:
            r.issues.append(i)
        r.set("FAIL", f"netlist not layout-ready: {len(blocking)} blocking issue(s)")
        r.next = [f"mbg netlist check {runio.rel(path)}"]
        return r
    hints = load_obj(args.get("hints"), "hints") or {}
    from mbg.placement_engine import PlacementConfig
    from mbg.router import RouterConfig
    from mbg.pipeline import spice_to_gds_with_checks, spice_to_gds_ctx, write_gds_foundry
    pcfg = PlacementConfig(verbosity=1, hints=hints, **(args.get("placement") or {}))
    rcfg = RouterConfig(verbosity=1, **(args.get("router") or {}))
    cell = subckt_name(text)
    outdir = ctx.run_dir
    ctx.stage("placement + routing" + (" + sign-off" if args.get("verify", True) else ""))
    if args.get("verify", True):
        res = spice_to_gds_with_checks(text, gds_path=str(outdir / f"{cell}.gds"),
                                       pdk=prof.name, outdir=str(outdir),
                                       placement_config=pcfg, router_config=rcfg,
                                       verbosity=1)
    else:
        with prof.env():
            res = spice_to_gds_ctx(text, pdk=prof.name, placement_config=pcfg,
                                   router_config=rcfg, verbosity=1)
            gds = outdir / f"{cell}.gds"
            write_gds_foundry(res["component"], str(gds))
            res["gds_path"] = str(gds)
    lctx = res["context"]
    from mbg.layout_view import render_ascii, snapshot
    snap = snapshot(lctx, res)
    (outdir / "layout.json").write_text(json.dumps(snap, indent=1, default=str))
    (outdir / "layout.txt").write_text(render_ascii(snap))

    m = res.get("metrics") or {}
    ver = res.get("verification") or {}
    r.metrics = {
        "pdk": prof.name, "cell": cell, "size_um": snap["size_um"],
        "area_um2": round(snap["size_um"][0] * snap["size_um"][1], 2),
        "devices": len(snap["devices"]),
        "routed_nets": m.get("routed_nets"), "total_nets": m.get("total_nets"),
        "wire_length_um": m.get("wire_length"), "vias": m.get("via_count"),
        "internal_clean": bool(ver.get("clean")),
    }
    arts = {"gds": res.get("gds_path"), "layout_txt": outdir / "layout.txt",
            "layout_json": outdir / "layout.json", "svg": res.get("svg_path")}
    if args.get("verify", True):
        drc = res.get("drc") or {}
        s = res.get("drc_signoff") or {}
        lvs = res.get("lvs") or {}
        pex = res.get("pex") or {}
        r.metrics.update({
            "drc_magic": drc.get("summary"), "drc_signoff": s.get("verdict"),
            "drc_engines": [e.get("engine") for e in (s.get("results") or [])],
            "lvs_match": bool(lvs.get("match")),
            "pex": bool(pex.get("pex_path")), "all_pass": bool(res.get("all_pass")),
        })
        arts.update({"schematic": outdir / f"{cell}.spice",
                     "magic_drc": drc.get("report_path"),
                     "drc_summary": outdir / "verification" / "drc_summary.json",
                     "lvs_report": lvs.get("report_path"),
                     "extracted": outdir / f"{cell}_extracted.spice",
                     "pex": pex.get("pex_path")})
        _drc_issues(r, res)
        _lvs_issues(r, res)
        if not pex.get("pex_path"):
            r.issue("PEX_FAILED", f"PEX: {pex.get('summary')}")
    _connectivity_issues(r, ver)
    for f in snap["failures"][:8]:
        r.issue("ROUTE_" + f["cause"], f"net {f['net']}: {f['detail'] or f['cause']}",
                hint=f["suggested_action"] or "add placement hints to open a channel",
                net=f["net"], blocking=f["blocking"] or None)
    if snap.get("hint_overlaps"):
        r.issue("HINT_OVERLAP", f"hinted devices overlap: {snap['hint_overlaps']}",
                hint="change fixed x/y or array gap")
    r.artifacts = {k: runio.rel(v) for k, v in arts.items() if v and Path(v).exists()}
    design = args.get("design")
    record(design, gds=res.get("gds_path"))
    if args.get("verify", True):
        record(design, stage="drc", status="PASS" if (res.get("drc") or {}).get("clean")
               and (res.get("drc_signoff") or {}).get("verdict") == "PASS" else "FAIL",
               artifact=outdir / "verification" / "drc_summary.json")
        record(design, stage="lvs", status="PASS" if (res.get("lvs") or {}).get("match")
               else "FAIL", artifact=(res.get("lvs") or {}).get("report_path"))
        pexp = (res.get("pex") or {}).get("pex_path")
        record(design, stage="pex", status="PASS" if pexp else "FAIL", artifact=pexp)

    size = f"{snap['size_um'][0]:.1f} x {snap['size_um'][1]:.1f} um"
    if not args.get("verify", True):
        ok = bool(ver.get("clean"))
        r.set("PASS" if ok else "FAIL",
              f"{cell}: {size}, routed {m.get('routed_nets')}/{m.get('total_nets')} nets, "
              f"internal {'clean' if ok else 'ISSUES'} (sign-off not run)")
        r.next = [f"mbg verify drc {r.artifacts.get('gds', '')}",
                  f"mbg layout view {runio.rel(outdir)}"]
        return r
    legs = (f"DRC magic={r.metrics['drc_magic']}, sign-off={r.metrics['drc_signoff']}, "
            f"LVS={'match' if r.metrics['lvs_match'] else 'MISMATCH'}, "
            f"PEX={'ok' if r.metrics['pex'] else 'none'}, "
            f"internal={'clean' if r.metrics['internal_clean'] else 'ISSUES'}")
    if res.get("all_pass"):
        r.set("PASS", f"{cell}: {size}; all four legs pass ({legs})")
        rel_pex = r.artifacts.get("pex", "")
        from mbg.agent.handlers import subckt_ports
        is_ref = any(p.upper() == "VREF" for p in subckt_ports(text))
        r.next = [f"mbg measure vref {rel_pex} --post-layout" if is_ref
                  else f"mbg sim run {rel_pex} --analysis op --post-layout",
                  f"mbg layout view {runio.rel(outdir)}"]
    else:
        r.set("FAIL", f"{cell}: {size}; {legs}")
        r.next = [f"mbg layout view {runio.rel(outdir)}",
                  "adjust placement with --hints (rows/order/array/fixed) and re-run"]
    return r


def view(args, ctx) -> Result:
    r = Result(tool="layout.view", status="PASS")
    target = args.get("run")
    if not target and args.get("design"):
        base = runio.out_root() / runio.safe_name(args["design"])
        cands = sorted(base.glob("layout*/layout.json"), key=lambda p: p.stat().st_mtime)
        if not cands:
            raise FileNotFoundError(f"no layout run in workspace {args['design']}")
        target = str(cands[-1])
    if not target:
        from mbg.agent.cli import UsageError
        raise UsageError("pass the run directory of a layout.generate call")
    p = Path(target)
    if p.is_dir():
        p = p / "layout.json"
    if not p.is_file():
        raise FileNotFoundError(f"{p} not found (is this a layout.generate run directory?)")
    snap = json.loads(p.read_text())
    if args.get("format") == "json":
        r.data = {"layout": snap}
        r.summary = f"{snap['cell']}: {snap['size_um'][0]} x {snap['size_um'][1]} um"
        return r
    from mbg.layout_view import render_ascii
    text = render_ascii(snap, width=int(args.get("width") or 72))
    r.data = {"ascii": text}
    r.summary = (f"{snap['cell']}: {snap['size_um'][0]:.1f} x {snap['size_um'][1]:.1f} um, "
                 f"{len(snap['devices'])} devices, {len(snap['failures'])} routing failure(s)")
    r.next = ["edit placement with --hints '{\"order\": {\"0\": [...]}, \"fixed\": {...}}' "
              "and re-run mbg layout generate"]
    return r
