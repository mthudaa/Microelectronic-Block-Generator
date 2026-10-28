"""A layout as text: the floorplan an agent reads instead of a screenshot.

``snapshot(ctx)`` reduces a DesignContext after layout to plain data — device
slots, rows, per-device nets, nets that failed to route and why — written as
``layout.json`` beside the GDS. ``render_ascii(snapshot)`` draws it:

    +----------------------------------------------------------+  y=31.4
    | [XM3 pmos r0]        [XM4 pmos r0]                       |
    |                                                          |
    | [XM1 nmos r1]   [XM2 nmos r1]                            |
    | [XM5 nmos r2]                                            |
    +----------------------------------------------------------+  y=0.0
    x=-14.2                                               x=14.2

The coordinates are the ones placement hints use (``fixed: {dev: {x, y}}``
is the lower-left corner of a slot), so an agent can read a floorplan, decide
"move XQ2 next to XQ1", and write the hint without converting anything.
"""
from __future__ import annotations

from typing import Any, Dict, List


def snapshot(ctx, result: Dict[str, Any] = None) -> Dict[str, Any]:
    devs: Dict[str, Any] = {}
    for name, dev in ctx.devices.items():
        bb = ctx.device_bboxes.get(name)
        pl = ctx.placements.get(name)
        d = {"model": dev.model, "kind": dev.kind,
             "terminals": dict(dev.terminals)}
        if bb is not None:
            d.update({"x": round(bb.xmin, 3), "y": round(bb.ymin, 3),
                      "w": round(bb.width, 3), "h": round(bb.height, 3)})
        if pl is not None:
            d["row"] = pl.row
            d["orientation"] = pl.orientation
        d["access_points"] = sum(1 for aps in ctx.net_to_access.values()
                                 for ap in aps if ap.instance == name)
        devs[name] = d
    rows: Dict[str, List[str]] = {}
    for name, d in sorted(devs.items(), key=lambda kv: kv[1].get("x", 0.0)):
        if "row" in d:
            rows.setdefault(str(d["row"]), []).append(name)
    try:
        bb = ctx.design_bbox()
        bbox = [round(bb.xmin, 3), round(bb.ymin, 3), round(bb.xmax, 3), round(bb.ymax, 3)]
    except Exception:
        xs = [d["x"] for d in devs.values() if "x" in d] or [0.0]
        ys = [d["y"] for d in devs.values() if "y" in d] or [0.0]
        x1 = [d["x"] + d["w"] for d in devs.values() if "x" in d] or [0.0]
        y1 = [d["y"] + d["h"] for d in devs.values() if "y" in d] or [0.0]
        bbox = [min(xs), min(ys), max(x1), max(y1)]
    nets = {}
    for name, net in ctx.nets.items():
        rn = ctx.routed_nets.get(name)
        nets[name] = {"degree": net.degree,
                      "routed": bool(rn and rn.complete) if name in ctx.routable_nets() else None,
                      "power": net.is_power, "ground": net.is_ground}
    failures = [{"net": f.net, "cause": f.cause, "detail": f.detail,
                 "blocking": list(f.blocking_instances),
                 "suggested_action": f.suggested_action} for f in ctx.failures]
    groups = [{"name": g.name, "kind": g.kind, "devices": list(g.devices)}
              for g in ctx.matching_groups.values()]
    snap = {"cell": ctx.name, "bbox": bbox,
            "size_um": [round(bbox[2] - bbox[0], 3), round(bbox[3] - bbox[1], 3)],
            "devices": devs, "rows": rows, "nets": nets, "failures": failures,
            "matching_groups": groups,
            "hint_overlaps": ctx.metrics.get("hint_overlaps", [])}
    if result:
        snap["pdk"] = result.get("pdk")
    return snap


def render_ascii(snap: Dict[str, Any], width: int = 72, max_height: int = 24) -> str:
    x0, y0, x1, y1 = snap["bbox"]
    span_x = max(x1 - x0, 1e-6)
    span_y = max(y1 - y0, 1e-6)
    # One scale for both axes (a character is about twice as tall as wide),
    # chosen so the drawing fits in width x max_height — a tall, narrow cell
    # becomes a narrow picture instead of 60 lines of an agent's context.
    chars_per_um = min((width - 2) / span_x, 2.0 * max_height / span_y)
    inner_w = max(12, int(round(span_x * chars_per_um)))
    inner_h = max(4, int(round(span_y * chars_per_um / 2.0)))
    grid = [[" "] * inner_w for _ in range(inner_h)]

    def cx(x):
        return min(inner_w - 1, max(0, int((x - x0) / span_x * inner_w)))

    def cy(y):
        return min(inner_h - 1, max(0, inner_h - 1 - int((y - y0) / span_y * inner_h)))

    for name, d in snap["devices"].items():
        if "x" not in d:
            continue
        a, b = cx(d["x"]), cx(d["x"] + d["w"])
        top, bot = cy(d["y"] + d["h"]), cy(d["y"])
        for c in range(a, b + 1):
            grid[top][c] = "-"
            grid[bot][c] = "-"
        for r in range(top, bot + 1):
            grid[r][a] = "|"
            grid[r][b] = "|"
        label = f"{name}"
        if b - a - 1 >= len(label) + 5:
            label = f"{name} {d['kind']}"
        mid = (top + bot) // 2
        start = a + 1 + max(0, (b - a - 1 - len(label)) // 2)
        for i, ch in enumerate(label[:max(0, b - a - 1)]):
            if start + i < b:
                grid[mid][start + i] = ch
    border = "+" + "-" * inner_w + "+"
    lines = [border + f"  y={y1:.1f}"]
    lines += ["|" + "".join(r) + "|" for r in grid]
    lines += [border + f"  y={y0:.1f}"]
    lines.append(f"x={x0:.1f}".ljust(max(inner_w - 6, 10)) + f"x={x1:.1f}")
    lines.append("")
    lines.append(f"{snap['cell']}: {snap['size_um'][0]:.2f} x {snap['size_um'][1]:.2f} um, "
                 f"{len(snap['devices'])} devices")
    lines.append(f"{'device':<10}{'kind':<6}{'row':>4}{'x':>9}{'y':>9}{'w':>8}{'h':>8}  nets")
    for name, d in sorted(snap["devices"].items(), key=lambda kv: (kv[1].get("row", 9), kv[1].get("x", 0))):
        nets = " ".join(f"{t}={n}" for t, n in d["terminals"].items())
        lines.append(f"{name:<10}{(d['kind'] or '?'):<6}{d.get('row', '-'):>4}"
                     f"{d.get('x', 0):>9.2f}{d.get('y', 0):>9.2f}{d.get('w', 0):>8.2f}"
                     f"{d.get('h', 0):>8.2f}  {nets}")
    unrouted = [n for n, v in snap["nets"].items() if v.get("routed") is False]
    if unrouted:
        lines.append(f"UNROUTED: {', '.join(unrouted)}")
    for f in snap["failures"][:8]:
        lines.append(f"FAILURE {f['net']}: {f['cause']} {f['detail']} -> {f['suggested_action']}")
    if snap.get("hint_overlaps"):
        lines.append(f"HINT OVERLAPS: {snap['hint_overlaps']}")
    return "\n".join(lines) + "\n"
