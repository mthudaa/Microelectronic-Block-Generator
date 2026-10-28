"""doctor, pdk.list, pdk.info."""
from __future__ import annotations

import importlib.metadata as _md
import platform

from mbg.agent.envelope import Result


def _pkg(name: str) -> str:
    try:
        return _md.version(name)
    except _md.PackageNotFoundError:
        return ""


def doctor(args, ctx) -> Result:
    from mbg import config, pdk_profile
    r = Result(tool="doctor")
    prof = pdk_profile.resolve(args.get("pdk"))
    with prof.env():
        cfg = config.pdk_config()
        config.clear_tool_cache() if hasattr(config, "clear_tool_cache") else None
        tools = {
            "magic": config.resolve_magic(cfg, probe=prof.installed()),
            "netgen": config.resolve_netgen(),
            "klayout": config.resolve_klayout(),
            "ngspice": config.resolve_ngspice(),
        }
    py = {"python": platform.python_version(),
          "glayout": _pkg("glayout"), "gdsfactory": _pkg("gdsfactory"),
          "numpy": _pkg("numpy"), "gdstk": _pkg("gdstk")}
    r.metrics["python"] = py
    r.metrics["tools"] = {n: {"ok": t.ok, "version": t.version_string,
                              "path": t.path or ""} for n, t in tools.items()}
    r.metrics["pdks"] = {p.name: {"installed": p.installed(), "path": str(p.path())}
                         for p in pdk_profile.all_profiles()}
    r.metrics["active_pdk"] = prof.name

    stages = {
        "netlist_check": True,
        "simulation": tools["ngspice"].ok and prof.installed(),
        "layout": bool(py["glayout"] and py["gdsfactory"]),
        "drc_magic": tools["magic"].ok and prof.installed(),
        "drc_klayout": ("klayout" not in prof.drc_engines)
                       or (tools["klayout"].ok and _klayout_new_enough(tools["klayout"])),
        "lvs": tools["netgen"].ok and tools["magic"].ok and prof.installed(),
        "pex": tools["magic"].ok and prof.installed(),
    }
    r.metrics["stages"] = stages

    if not py["glayout"]:
        r.issue("NO_GLAYOUT", "gLayout is not installed; layout tools cannot run",
                hint="./install.sh --stage python")
    if not prof.installed():
        r.issue("PDK_MISSING", f"{prof.name} not installed at {prof.path()}",
                hint="./install.sh --stage pdk (or set PDK_ROOT)")
    for name, t in tools.items():
        if not t.ok:
            sev = "warning" if name in ("ngspice", "klayout") and not (
                name == "klayout" and "klayout" in prof.drc_engines) else "error"
            r.issue(f"NO_{name.upper()}", (t.reason or f"{name} unusable").splitlines()[0],
                    severity=sev, hint="./install.sh --stage eda")
    if tools["klayout"].ok and "klayout" in prof.drc_engines \
            and not _klayout_new_enough(tools["klayout"]):
        r.issue("KLAYOUT_TOO_OLD",
                f"KLayout {tools['klayout'].version_string} is older than the "
                f"0.30.9 the {prof.name} deck needs for sign-off",
                hint="./install.sh --stage eda")

    ready = [s for s, ok in stages.items() if ok]
    blocked = [s for s, ok in stages.items() if not ok]
    if not blocked:
        r.set("PASS", f"every stage can run on {prof.name}")
    elif "netlist_check" in ready and len(ready) > 1:
        r.set("PARTIAL", f"{prof.name}: ready {ready}; blocked {blocked}")
    else:
        r.set("NOT AVAILABLE", f"{prof.name}: only {ready} can run")
    r.next = ["mbg pdk info --section devices", "mbg tools"]
    return r


def _klayout_new_enough(info) -> bool:
    try:
        from mbg.drc import MIN_KLAYOUT_VERSION
    except Exception:
        MIN_KLAYOUT_VERSION = (0, 30, 9)
    v = tuple(x for x in (info.version or ()) if x is not None)
    return bool(v) and v >= MIN_KLAYOUT_VERSION


def pdk_list(args, ctx) -> Result:
    from mbg import pdk_profile
    r = Result(tool="pdk.list", status="PASS")
    default = pdk_profile.resolve()
    rows = []
    for p in pdk_profile.all_profiles():
        rows.append({"name": p.name, "family": p.family, "installed": p.installed(),
                     "supply_v": p.supply_v, "default": p.name == default.name,
                     "layout_devices": p.models(layout_only=True),
                     "description": p.description})
    r.data = {"pdks": rows}
    r.summary = ", ".join(f"{x['name']}{' (default)' if x['default'] else ''}"
                          f"{'' if x['installed'] else ' [not installed]'}" for x in rows)
    r.next = [f"mbg pdk info --pdk {default.name} --section devices"]
    return r


def pdk_info(args, ctx) -> Result:
    from mbg import pdk_profile
    prof = pdk_profile.resolve(args.get("pdk"))
    r = Result(tool="pdk.info", status="PASS")
    model = args.get("model")
    if model:
        spec = prof.device(model)
        if spec is None:
            r.set("FAIL", f"{model!r} is not a {prof.name} device")
            r.issue("UNKNOWN_MODEL", f"{model!r} is not in the {prof.name} catalogue",
                    hint="known models: " + ", ".join(prof.devices))
            return r
        r.data = {"pdk": prof.name, "device": spec.as_dict(),
                  "sim_sections_typical": prof.lib_sections({spec.sim}, None)}
        r.summary = (f"{spec.model}: {spec.kind}, terminals {' '.join(spec.terminals)}, "
                     f"layout {'supported' if spec.layout else 'NOT supported'}")
        return r
    r.data = prof.summary(args.get("section"))
    lay = prof.models(layout_only=True)
    r.summary = (f"{prof.name}: {prof.supply_v} V; layout devices: {', '.join(lay)}; "
                 f"{'installed' if prof.installed() else 'NOT installed'}")
    if not prof.installed():
        r.issue("PDK_MISSING", f"{prof.name} is not installed at {prof.path()}",
                severity="warning", hint="./install.sh --stage pdk")
    return r
