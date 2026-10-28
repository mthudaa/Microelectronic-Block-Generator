"""sim.run — one ngspice analysis in a generated testbench."""
from __future__ import annotations

import csv
import math

from mbg.agent import runio
from mbg.agent.envelope import Result
from mbg.agent.handlers import (ensure_pdk, profile_for, read_netlist,
                                subckt_name, subckt_ports)


def default_supplies(ports, prof):
    conv = prof.conventions
    sup = {n.upper() for n in conv.get("supply_names", ["VDD"])}
    gnd = {n.upper() for n in conv.get("ground_names", ["VSS"])}
    out = {}
    for p in ports:
        if p.upper() in sup:
            out[p] = prof.supply_v
        elif p.upper() in gnd:
            out[p] = 0.0
    return out


def _write_csv(path, x_name, x, signals, probes):
    cols = [p for p in probes if p in signals]
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow([x_name or "x"] + cols)
        for i, xv in enumerate(x):
            w.writerow([xv] + [signals[c][i] if i < len(signals[c]) else "" for c in cols])


def run(args, ctx) -> Result:
    from mbg.analysis import Testbench
    r = Result(tool="sim.run")
    text, path = read_netlist(args)
    prof = profile_for(args, text)
    if not ensure_pdk(prof, r):
        return r
    cell = subckt_name(text)
    ports = subckt_ports(text)
    supplies = args.get("supplies") or default_supplies(ports, prof)
    analysis = args["analysis"]
    wd = str(ctx.path("ngspice"))
    # Internal nets are probed by name: the DUT is instance `xdut`, so an
    # internal node VA is the ngspice vector v(xdut.va). Agents should not
    # have to know that.
    port_set = {p.upper() for p in ports}
    probe_names = {}
    probes = []
    for p in args.get("probes") or []:
        if "(" in p or p.upper() in port_set:
            probes.append(p)
        else:
            expr = f"v(xdut.{p.lower()})"
            probes.append(expr)
            probe_names[expr] = p
    tb = Testbench(text, cell, pdk=prof.name, corner=args.get("corner"),
                   supplies=supplies, sources=args.get("sources"),
                   isources=args.get("isources"), loads=args.get("loads"),
                   probes=probes or None, workdir=wd, temp=args.get("temp"))
    r.metrics["conditions"] = {"pdk": prof.name, "corner": tb.corner,
                               "temp": args.get("temp", 27), "supplies": supplies}
    ctx.stage(f"ngspice {analysis}")
    if analysis == "op":
        res = tb.op()
    elif analysis == "dc":
        sw = args.get("sweep") or {}
        if not {"source", "start", "stop", "step"} <= set(sw):
            from mbg.agent.cli import UsageError
            raise UsageError("dc needs --sweep '{\"source\": node|\"temp\", "
                             "\"start\": .., \"stop\": .., \"step\": ..}'")
        res = tb.dc(sw["source"], sw["start"], sw["stop"], sw["step"])
    elif analysis == "ac":
        a = args.get("ac") or {}
        res = tb.ac(a.get("fstart", 1), a.get("fstop", 1e9), points=a.get("points", 20),
                    ac_node=a.get("node"))
    else:
        t = args.get("tran") or {}
        if not {"step", "stop"} <= set(t):
            from mbg.agent.cli import UsageError
            raise UsageError("tran needs --tran '{\"step\": \"1n\", \"stop\": \"1u\"}'")
        res = tb.tran(str(t["step"]), str(t["stop"]))
    r.artifacts["deck"] = runio.rel(ctx.path("ngspice") / "input.spice")
    probes = list(tb.probes or tb.ports)
    if not res.ok:
        tail = "\n".join((res.stdout or "").splitlines()[-8:] + (res.stderr or "").splitlines()[-8:])
        r.set("FAIL", f"{analysis}: ngspice produced no data")
        r.issue("SIM_NO_DATA", "ngspice produced no data", log=tail,
                hint="read the deck and log; check models, node names and sources")
        return r
    vals = {}
    if analysis == "op":
        for p in probes:
            try:
                vals[p] = res.value(p if "(" in p else p)
            except KeyError:
                pass
        vals = {probe_names.get(k, k): v for k, v in vals.items()}
        r.metrics["op"] = vals
        r.summary = "op: " + ", ".join(f"{k}={v:.5g}" for k, v in list(vals.items())[:8])
    else:
        csv_path = ctx.path(f"{analysis}.csv")
        _write_csv(csv_path, res.x_name, res.x, res.signals, probes)
        r.artifacts["csv"] = runio.rel(csv_path)
        summ = {}
        for p in probes:
            try:
                y = res.get(p)
            except KeyError:
                continue
            s = {"min": min(y), "max": max(y), "first": y[0], "last": y[-1]}
            if analysis == "ac":
                db = [20 * math.log10(max(v, 1e-15)) for v in y]
                s = {"gain_db_low_f": db[0], "max_db": max(db)}
                bw = res.bandwidth_3db(p)
                if bw:
                    s["bw_3db_hz"] = bw
                for i in range(1, len(db)):
                    if db[i - 1] >= 0 > db[i]:
                        s["ugf_hz"] = res.x[i]
                        break
            summ[probe_names.get(p, p)] = s
        r.metrics[analysis] = summ
        r.metrics["points"] = len(res.x)
        r.summary = f"{analysis}: {len(res.x)} points; " + "; ".join(
            f"{k}: " + ", ".join(f"{a}={b:.4g}" for a, b in v.items()) for k, v in list(summ.items())[:3])
    r.set("PASS")
    r.next = [f"mbg measure vref {runio.rel(path)}" if any(p.upper() == "VREF" for p in ports)
              else f"mbg layout generate {runio.rel(path)}"]
    return r
