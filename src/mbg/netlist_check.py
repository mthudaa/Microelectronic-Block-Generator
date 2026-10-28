"""Static netlist checks — everything that can be wrong before any tool runs.

An agent that writes a netlist gets its first feedback here, in well under a
second and without ngspice, Magic or gLayout. Every finding has a stable
``code``, a severity and, where there is one, the fix:

    UNKNOWN_MODEL        model is not in the PDK catalogue
    LAYOUT_UNSUPPORTED   model simulates but the layout engine cannot draw it
    TERMINAL_COUNT       wrong number of nodes for the model
    SIZE_RANGE           W or L outside the profile limits
    UNIT_MISSING         gf180 W/L written without a unit (W=2 means 2 m)
    UNIT_SUFFIX          sky130 W/L written with 'u' (sky130 is unitless um)
    BODY_TIE             PMOS body not on the supply / NMOS body not on ground
    INSTANCE_PREFIX      MOSFET named M1 instead of XM1
    MULTIPLIER           m=N on a MOSFET; nf=N matches and packs better
    BJT_NOT_SUBCKT       gf180 BJTs are subcircuits: write XQ1 c b e <model>
    FLOATING_NET         an internal net touches only one device terminal
    NO_SUBCKT / MULTIPLE_SUBCKT / NESTED_INSTANCE / PARAM_UNSUPPORTED
    ABOVE_TESTED_CEILING more devices / nets / net degree than the regression covers
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from mbg.spice_parser import _logical_lines

_SI = {"t": 1e12, "g": 1e9, "meg": 1e6, "k": 1e3, "m": 1e-3, "u": 1e-6,
       "n": 1e-9, "p": 1e-12, "f": 1e-15}
_VAL = re.compile(r"^([-+]?(?:\d+\.?\d*|\.\d+)(?:e[-+]?\d+)?)(meg|[tgkmunpf])?$", re.I)


def _length_um(text: str, unitless_um: bool) -> Tuple[Optional[float], bool]:
    """(value in um, had a unit suffix)."""
    m = _VAL.match(text.strip())
    if not m:
        return None, False
    v = float(m.group(1))
    suf = (m.group(2) or "").lower()
    if not suf:
        return (v if unitless_um else v * 1e6), False
    return v * _SI[suf] * 1e6, True


def _params(tokens: List[str]) -> Dict[str, str]:
    out = {}
    for t in tokens:
        if "=" in t:
            k, _, v = t.partition("=")
            out[k.strip().lower()] = v.strip()
    return out


def check_netlist(text: str, profile) -> Dict[str, Any]:
    """Run every check. Returns ``{"issues": [...], "metrics": {...}, "devices": [...]}``."""
    issues: List[Dict[str, Any]] = []

    def add(code, msg, sev="error", hint=None, **kw):
        d = {"code": code, "severity": sev, "message": msg}
        if hint:
            d["hint"] = hint
        d.update({k: v for k, v in kw.items() if v is not None})
        issues.append(d)

    lines = _logical_lines(text)
    subckts = [l for l in lines if l.lower().startswith(".subckt")]
    if not subckts:
        add("NO_SUBCKT", "no .subckt definition", hint="wrap the circuit in "
            ".subckt <name> <ports...> ... .ends")
        return {"issues": issues, "metrics": {}, "devices": []}
    if len(subckts) > 1:
        add("MULTIPLE_SUBCKT", f"{len(subckts)} .subckt blocks; MBG lays out one "
            "flat subcircuit (nested .subckt are parsed but not flattened)",
            hint="flatten the hierarchy into one .subckt")
    head = subckts[0].split()
    cell = head[1] if len(head) > 1 else "?"
    ports = [p for p in head[2:] if "=" not in p]
    unitless = "unitless" in (profile.data.get("units", "") or "")
    conv = profile.conventions
    grounds = {n.upper() for n in conv.get("ground_names", ["VSS", "GND", "0"])}
    supplies = {n.upper() for n in conv.get("supply_names", ["VDD"])}

    devices: List[Dict[str, Any]] = []
    in_body = False
    net_terms: Dict[str, List[str]] = defaultdict(list)
    for line in lines:
        low = line.lower()
        if low.startswith(".subckt"):
            in_body = True
            continue
        if low.startswith(".ends"):
            in_body = False
            continue
        if low.startswith(".param"):
            add("PARAM_UNSUPPORTED", ".param is not expanded by the layout flow; "
                "write literal values", sev="warning")
            continue
        if line.startswith(".") or not in_body:
            continue
        toks = line.split()
        name = toks[0]
        letter = name[0].upper()
        pre = [t for t in toks[1:] if "=" not in t]
        prm = _params(toks[1:])
        if letter == "M":
            nodes, model = pre[:4], (pre[4] if len(pre) > 4 else "")
        elif letter == "Q":
            nodes, model = pre[:-1], (pre[-1] if pre else "")
            add("BJT_NOT_SUBCKT", f"{name}: BJTs in {profile.name} are subcircuits",
                hint=f"rename to X{name} and keep the node order "
                     f"{' '.join(profile.device(model).terminals) if profile.device(model) else 'c b e'}",
                device=name)
        elif letter in ("X", "R", "C"):
            nodes, model = pre[:-1], (pre[-1] if pre else "")
        else:
            add("UNSUPPORTED_ELEMENT", f"{name}: element type {letter!r} is not "
                "laid out by MBG", sev="warning", device=name)
            continue
        spec = profile.device(model)
        dev = {"name": name, "model": model, "nodes": nodes,
               "kind": spec.kind if spec else None,
               "layout": bool(spec and spec.layout), "params": prm}
        devices.append(dev)
        for i, n in enumerate(nodes):
            term = spec.terminals[i] if spec and i < len(spec.terminals) else f"pin{i + 1}"
            net_terms[n].append(f"{name}.{term}")
        if spec is None:
            other = profile.family
            add("UNKNOWN_MODEL", f"{name}: model {model!r} is not a {profile.name} device",
                hint="known models: " + ", ".join(profile.devices), device=name)
            if letter == "X" and len(nodes) > 0 and model.lower().startswith(("x", "sub")):
                add("NESTED_INSTANCE", f"{name}: instance of a subcircuit; "
                    "hierarchy is not flattened", device=name)
            continue
        if not spec.layout:
            add("LAYOUT_UNSUPPORTED", f"{name}: {model} can be simulated but the "
                f"layout engine cannot draw it ({spec.note or 'not supported'})",
                sev="warning", device=name,
                hint="layout devices: " + ", ".join(profile.models(layout_only=True)))
        if len(nodes) != len(spec.terminals):
            if len(nodes) == len(spec.terminals) - 1 and spec.terminals[-1] == "body":
                # a passive written without its bulk: the substrate is implied
                add("TERMINAL_COUNT", f"{name}: {model} written with {len(nodes)} of its "
                    f"{len(spec.terminals)} terminals; the body is taken as the substrate",
                    sev="warning", hint=f"write all of: {' '.join(spec.terminals)} "
                    f"(body on ground)", device=name)
            else:
                add("TERMINAL_COUNT", f"{name}: {model} has {len(spec.terminals)} terminals "
                    f"({' '.join(spec.terminals)}), the line gives {len(nodes)}",
                    device=name)
        if spec.kind in ("nmos", "pmos"):
            if letter == "M":
                add("INSTANCE_PREFIX", f"{name}: write MOSFETs as X{name} "
                    f"(subcircuit instance) for {profile.name}", sev="warning",
                    device=name)
            for key, lo, hi in (("w", spec.w_min_um, spec.w_max_um),
                                ("l", spec.l_min_um, spec.l_max_um)):
                raw = prm.get(key)
                if raw is None:
                    add("SIZE_MISSING", f"{name}: no {key.upper()}=", device=name)
                    continue
                val, had_unit = _length_um(raw, unitless)
                if val is None:
                    add("SIZE_UNPARSED", f"{name}: cannot read {key.upper()}={raw}",
                        device=name)
                    continue
                if unitless and had_unit:
                    add("UNIT_SUFFIX", f"{name}: {key.upper()}={raw} — {profile.name} "
                        "sizes are unitless microns", hint=f"write {key.upper()}="
                        f"{raw.rstrip('uU')}", device=name)
                    val = float(_VAL.match(raw).group(1))
                elif not unitless and not had_unit:
                    add("UNIT_MISSING", f"{name}: {key.upper()}={raw} has no unit "
                        f"and means {raw} m", hint=f"write {key.upper()}={raw}u",
                        device=name)
                    continue
                if key == "w":
                    # SPICE W is the total width; the limits are per finger
                    try:
                        nf = max(1, int(float(prm.get("nf", "1"))))
                    except ValueError:
                        nf = 1
                    val = val / nf
                label = f"{key.upper()}" + ("/nf" if key == "w" and prm.get("nf") not in (None, "1") else "")
                if lo is not None and val < lo - 1e-9:
                    add("SIZE_RANGE", f"{name}: {label}={val:g}um is below the "
                        f"minimum {lo:g}um", device=name)
                if hi is not None and val > hi + 1e-9:
                    add("SIZE_RANGE", f"{name}: {label}={val:g}um exceeds "
                        f"{hi:g}um" + (" per finger; raise nf" if key == "w" else ""),
                        sev="error", device=name)
            if prm.get("m") not in (None, "1"):
                add("MULTIPLIER", f"{name}: m={prm['m']}; prefer nf=N (fingers) for "
                    "matching and compactness", sev="info", device=name)
            if len(nodes) == 4:
                body = nodes[3].upper()
                want = spec.body_net
                if want == "ground" and body not in grounds:
                    add("BODY_TIE", f"{name}: NMOS body on {nodes[3]}, not ground "
                        f"({'/'.join(sorted(grounds))})", sev="warning", device=name,
                        hint="intentional body bias is supported: the layout puts this "
                             "device in a deep n-well (larger area); otherwise tie it to ground")
                if want == "supply" and body not in supplies:
                    add("BODY_TIE", f"{name}: PMOS body on {nodes[3]}, not the supply "
                        f"({'/'.join(sorted(supplies))})", sev="warning", device=name,
                        hint="project rule (AGENTS.md): pfet body to VDD unless the "
                             "n-well is meant to float or be biased")
        if spec.kind == "bjt" and letter == "X":
            sub = [t for t, n in zip(spec.terminals, nodes) if t in spec.substrate_terminals]
            for t in sub:
                n = nodes[spec.terminals.index(t)]
                if n.upper() not in grounds:
                    add("SUBSTRATE_TERMINAL", f"{name}: terminal {t} is the substrate "
                        f"and must be on ground, not {n}", device=name)

    # connectivity
    port_set = {p.upper() for p in ports}
    for net, terms in net_terms.items():
        if net.upper() in port_set or net == "0":
            continue
        if len(terms) == 1:
            add("FLOATING_NET", f"net {net} touches only {terms[0]}", sev="warning",
                net=net)
    for p in ports:
        if p not in net_terms and p.upper() not in {n.upper() for n in net_terms}:
            add("UNUSED_PORT", f"port {p} connects to nothing", sev="warning", net=p)

    mos = [d for d in devices if d["kind"] in ("nmos", "pmos")]
    degree = {n: len(t) for n, t in net_terms.items()}
    rails = grounds | supplies
    sig_deg = [d for n, d in degree.items() if n.upper() not in rails]
    kinds = defaultdict(int)
    for d in devices:
        kinds[d["kind"] or "unknown"] += 1
    metrics = {"cell": cell, "ports": ports, "devices": len(devices),
               "by_kind": dict(kinds), "mos": len(mos), "nets": len(net_terms),
               "max_net_degree": max(degree.values()) if degree else 0,
               "max_signal_net_degree": max(sig_deg) if sig_deg else 0,
               "layout_supported": all(d["layout"] for d in devices) and bool(devices)}
    ceil = profile.tested_ceiling
    over = []
    if ceil:
        if len(mos) > ceil.get("mos", 1e9):
            over.append(f"{len(mos)} MOS > {ceil['mos']}")
        if len(net_terms) > ceil.get("nets", 1e9):
            over.append(f"{len(net_terms)} nets > {ceil['nets']}")
        if metrics["max_net_degree"] > ceil.get("max_net_degree", 1e9):
            over.append(f"max net degree {metrics['max_net_degree']} > "
                        f"{ceil['max_net_degree']}")
    if over:
        add("ABOVE_TESTED_CEILING", "beyond what the layout regression covers: "
            + "; ".join(over), sev="warning",
            hint="layout may still succeed; if routing fails, use placement hints "
                 "or split the block")
    return {"issues": issues, "metrics": metrics, "devices": devices}
