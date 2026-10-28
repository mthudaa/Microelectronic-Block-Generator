"""netlist.check."""
from __future__ import annotations

from mbg.agent import runio
from mbg.agent.envelope import Result
from mbg.agent.handlers import profile_for, read_netlist, record


def check(args, ctx) -> Result:
    from mbg.netlist_check import check_netlist
    r = Result(tool="netlist.check")
    text, path = read_netlist(args)
    try:
        prof = profile_for(args, text)
    except ValueError as e:
        r.set("FAIL", str(e))
        r.issue("PDK_UNKNOWN", str(e), hint="pass --pdk gf180mcuD or --pdk sky130A")
        return r
    out = check_netlist(text, prof)
    for i in out["issues"]:
        r.issues.append(i)
    r.metrics = out["metrics"]
    r.metrics["pdk"] = prof.name
    r.data = {"devices": [{k: d[k] for k in ("name", "model", "kind", "nodes", "layout")}
                          for d in out["devices"]]}
    n_err = len(r.errors)
    n_warn = sum(1 for i in r.issues if i["severity"] == "warning")
    unsupported = [i for i in r.issues if i["code"] == "LAYOUT_UNSUPPORTED"]
    m = out["metrics"]
    shape = (f"{m.get('devices', 0)} devices ({m.get('mos', 0)} MOS), "
             f"{m.get('nets', 0)} nets, max degree {m.get('max_net_degree', 0)}")
    if n_err:
        r.set("FAIL", f"{n_err} error(s), {n_warn} warning(s) in {path.name}: {shape}")
        r.next = ["fix the errors listed in issues, then re-run mbg netlist check"]
    elif unsupported:
        r.set("PARTIAL", f"simulation-ready, but {len(unsupported)} device(s) cannot be "
                         f"laid out on {prof.name}: {shape}")
        r.next = [f"mbg sim run {runio.rel(path)} --analysis op"]
    else:
        r.set("PASS", f"{path.name} OK on {prof.name}: {shape}"
                      + (f"; {n_warn} warning(s)" if n_warn else ""))
        nl = runio.rel(path)
        r.next = [f"mbg sim run {nl} --analysis op", f"mbg layout generate {nl}"]
    record(args.get("design"), netlist_valid=(n_err == 0))
    return r
