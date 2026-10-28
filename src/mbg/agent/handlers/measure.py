"""measure.vref, measure.ota — standard characterisation recipes."""
from __future__ import annotations

import csv
import json

from mbg.agent import runio
from mbg.agent.envelope import Result
from mbg.agent.handlers import ensure_pdk, profile_for, read_netlist, record
from mbg.agent.handlers.spec import apply


def _record_stage(args):
    return "post_simulation" if args.get("post_layout") else "pre_simulation"


def _stage_name(args):
    return "post_layout" if args.get("post_layout") else "pre_layout"


def vref(args, ctx) -> Result:
    from mbg.measure import measure_vref
    r = Result(tool="measure.vref")
    text, path = read_netlist(args)
    prof = profile_for(args, text)
    if not ensure_pdk(prof, r):
        return r
    corners = args.get("corners")
    ctx.stage("characterising reference")
    out = measure_vref(text, pdk=prof.name, ports=args.get("ports"), vdd=args.get("vdd"),
                       vdd_range=args.get("vdd_range"),
                       temp_range=args.get("temp_range") or (-40.0, 125.0, 5.0),
                       ibias=args.get("ibias", 20e-6), ibias_dir=args.get("ibias_dir", "source"),
                       ibias_sweep=args.get("ibias_sweep") or (10e-6, 20e-6, 30e-6),
                       cl=args.get("cl", "1p"), corners=corners, quick=args.get("quick", False),
                       workdir=str(ctx.path("ngspice")))
    m = out["metrics"]
    r.metrics = dict(m)
    r.metrics["conditions"] = out["conditions"]
    r.data["per_corner"] = {c: {k: v for k, v in d.items() if not isinstance(v, dict)}
                            for c, d in out["per_corner"].items()}
    full = ctx.path("vref_metrics.json")
    full.write_text(json.dumps({k: v for k, v in out.items()}, indent=1, default=str))
    r.artifacts["metrics_json"] = runio.rel(full)
    for name, block in out["data"].items():
        if name in ("temp_sweep", "line_sweep"):
            p = ctx.path(f"{name}.csv")
            with open(p, "w", newline="") as f:
                w = csv.writer(f)
                w.writerow(["corner", "x", "vref"])
                for c, d in block.items():
                    xs = d.get("t") or d.get("vdd")
                    for x, y in zip(xs, d["vref"]):
                        w.writerow([c, x, y])
            r.artifacts[name] = runio.rel(p)
    for wmsg in out["warnings"]:
        r.issue("MEASURE_WARNING", wmsg, severity="warning")
    head = (f"VREF={m.get('vref_v', float('nan')):.4f} V, TC={m.get('tc_ppm_c', float('nan')):.1f} ppm/C, "
            f"line={m.get('line_reg_mv_v', float('nan')):.2f} mV/V, "
            f"IVDD={m.get('ivdd_ua', float('nan')):.1f} uA"
            + (f", PSRR={m['psrr_db']:.1f} dB" if m.get("psrr_db") is not None else "")
            + f" over {len(out['corners'])} corner(s)")
    spec = args.get("spec")
    if spec:
        ok = apply(r, m, spec, source=_stage_name(args))
        if args.get("spec") != "bandgap" and isinstance(spec, str) and spec == "vref_md":
            # always show how far the design is from the stretch targets too
            stretch = Result(tool="x")
            apply(stretch, m, "bandgap", source="stretch")
            r.data.setdefault("spec", {}).update(stretch.data.get("spec", {}))
        r.set("PASS" if ok else "FAIL", head + ("; spec met" if ok else "; spec NOT met"))
    else:
        r.set("PASS", head + "; no spec given")
    r.next = ["mbg spec check --metrics " + runio.rel(full) + " --spec vref_md",
              f"mbg layout generate {runio.rel(path)}"]
    record(args.get("design"), stage=_record_stage(args), status=r.status, artifact=full)
    return r


def ota(args, ctx) -> Result:
    from mbg.measure import measure_ota
    r = Result(tool="measure.ota")
    text, path = read_netlist(args)
    prof = profile_for(args, text)
    if not ensure_pdk(prof, r):
        return r
    out = measure_ota(text, out=args["out"], inp=args["inp"], inn=args.get("inn"),
                      supplies=args.get("supplies"), bias=args.get("bias"),
                      vcm=args.get("vcm"), cl=args.get("cl", "1p"), pdk=prof.name,
                      corner=args.get("corner"), workdir=str(ctx.path("ngspice")))
    m = out["metrics"]
    r.metrics = dict(m)
    r.metrics["conditions"] = out["conditions"]
    if "gain_db" not in m:
        r.set("FAIL", "AC analysis produced no data")
        r.issue("SIM_NO_DATA", "no AC data", hint="check bias nodes and supplies")
        return r
    head = (f"gain={m['gain_db']:.1f} dB, BW={m.get('bw_hz', float('nan')):.3g} Hz, "
            f"UGF={m.get('ugf_hz', float('nan')):.3g} Hz, PM={m.get('phase_margin_deg', float('nan')):.0f} deg")
    spec = args.get("spec")
    if spec:
        ok = apply(r, m, spec, source=_stage_name(args))
        r.set("PASS" if ok else "FAIL", head)
    else:
        r.set("PASS", head + "; no spec given")
    r.next = [f"mbg layout generate {runio.rel(path)}"]
    record(args.get("design"), stage=_record_stage(args), status=r.status)
    return r
