"""Foundry fixed-layout primitives (vertical BJTs) as routable gdsfactory cells.

gf180's vertical PNPs are not parameterised devices: the PDK ships one fixed
layout per size (``libs.ref/gf180mcu_fd_pr/gds/pnp_10p00x10p00.gds``) and
Magic's own device generator does nothing but instance that cell. Drawing a
PNP from scratch would only be correct if it reproduced that cell exactly, so
this module imports the foundry cell instead and makes it routable:

1. **Labels are stripped.** The cell carries ``E``/``B``/``C`` text on metal1.
   Flattened into a layout with several PNPs, identical labels in one cell
   would name — and so merge — every emitter into one net.
2. **Rings are split into rectangles.** The base and collector contacts are
   square rings. The router models device metal by bounding box, and a
   ring's bounding box covers everything inside it: the emitter would sit
   "inside" the base metal and every access attempt would look like a short.
3. **Each terminal gets a via-1 landing on metal2**, centred on the ring's
   centre-line at each side's midpoint (the label positions), and ports named
   ``<terminal>_<N|E|S|W>`` like every other MBG device. The rings are only
   0.42 um wide; a router via dropped there by search could clip a
   neighbouring ring, so the landing is placed here, where the geometry is
   known.

The result is cached per PDK path and model, and :func:`self_check` extracts a
lone instance with Magic to confirm the device and its terminal order.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Dict, List, Tuple

# gf180 GDS layers (gf180mcuD.tech calma statements)
MET1 = (34, 0)
VIA1 = (35, 0)
MET2 = (36, 0)
_VIA1_SIZE = 0.26
_M1_VIA_ENC = 0.06          # V1.3: metal1 overlap of via1 (one direction 0.06)
_M2_PAD = 0.38              # metal2 landing (via 0.26 + 2 x 0.06)
_DIRS = {"N": 90.0, "E": 0.0, "S": 270.0, "W": 180.0}

_CACHE: Dict[Tuple[str, str], object] = {}


def _cache_dir() -> Path:
    d = Path(os.environ.get("MBG_CACHE", Path.home() / ".cache" / "mbg")) / "fixed"
    d.mkdir(parents=True, exist_ok=True)
    return d


def pdk_cell_gds(profile, model: str) -> Path:
    """The foundry GDS for a fixed device, e.g. ``.../gds/pnp_10p00x10p00.gds``."""
    lib = "gf180mcu_fd_pr" if profile.family == "gf180" else "sky130_fd_pr"
    p = profile.path() / "libs.ref" / lib / "gds" / f"{model}.gds"
    if not p.is_file():
        raise FileNotFoundError(f"fixed cell for {model} not found at {p}")
    return p


# ── geometry helpers (pure Python) ────────────────────────────────────

def rect_decompose(points: List[Tuple[float, float]]) -> List[Tuple[float, float, float, float]]:
    """Split a rectilinear polygon into rectangles (xmin, ymin, xmax, ymax).

    Horizontal slab decomposition: between consecutive distinct vertex y's,
    the polygon's cross-section is a set of x-intervals (even-odd rule over
    the vertical edges); vertically adjacent slabs with the same interval are
    merged. Exact for rectilinear input, including rings (holes are
    represented in a single boundary with a cut, as GDS stores them).
    """
    pts = [(round(x, 4), round(y, 4)) for x, y in points]
    n = len(pts)
    vedges = []
    for i in range(n):
        (x1, y1), (x2, y2) = pts[i], pts[(i + 1) % n]
        if x1 == x2 and y1 != y2:
            vedges.append((x1, min(y1, y2), max(y1, y2)))
    ys = sorted({y for _, y in pts})
    out: List[Tuple[float, float, float, float]] = []
    open_: Dict[Tuple[float, float], float] = {}
    for y0, y1 in zip(ys, ys[1:]):
        ym = (y0 + y1) / 2.0
        xs = sorted(x for x, lo, hi in vedges if lo < ym < hi)
        intervals = set()
        for k in range(0, len(xs) - 1, 2):
            if xs[k + 1] > xs[k]:
                intervals.add((xs[k], xs[k + 1]))
        for iv in list(open_):
            if iv not in intervals:
                out.append((iv[0], open_.pop(iv), iv[1], y0))
        for iv in intervals:
            open_.setdefault(iv, y0)
    for iv, ystart in open_.items():
        out.append((iv[0], ystart, iv[1], ys[-1]))
    return out


def _is_rect(points) -> bool:
    if len(points) != 4:
        return False
    xs = {round(p[0], 4) for p in points}
    ys = {round(p[1], 4) for p in points}
    return len(xs) == 2 and len(ys) == 2


# ── building the routable cell ────────────────────────────────────────

def build_fixed_device(profile, model: str):
    """A gdsfactory Component for a fixed foundry device, with MBG ports."""
    import gdstk
    import gdsfactory as gf

    src = pdk_cell_gds(profile, model)
    key = (str(src), model)
    if key in _CACHE:
        return _CACHE[key]
    lib = gdstk.read_gds(str(src))
    top = next((c for c in lib.top_level() if c.name == model), lib.top_level()[0])
    flat = top.copy(f"{model}_flat")
    flat.flatten()

    spec = profile.device(model)
    terms = [t.upper() for t in spec.terminals]
    # terminal label positions on metal1 (texttype 0 = the pin labels)
    label_pts: Dict[str, List[Tuple[float, float]]] = {t: [] for t in terms}
    for lab in flat.labels:
        if (lab.layer, lab.texttype) == MET1 and lab.text.upper() in label_pts:
            label_pts[lab.text.upper()].append(tuple(lab.origin))
    missing = [t for t, v in label_pts.items() if not v]
    if missing:
        raise ValueError(f"{model}: no metal1 label for terminal(s) {missing} in {src}")

    c = gf.Component(f"mbg_fx_{model}")
    met1_rects: List[Tuple[float, float, float, float]] = []
    for poly in flat.polygons:
        layer = (poly.layer, poly.datatype)
        pts = [tuple(p) for p in poly.points]
        rects = [(min(p[0] for p in pts), min(p[1] for p in pts),
                  max(p[0] for p in pts), max(p[1] for p in pts))] if _is_rect(pts) \
            else rect_decompose(pts)
        for (x0, y0, x1, y1) in rects:
            if x1 - x0 <= 1e-6 or y1 - y0 <= 1e-6:
                continue
            c.add_polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], layer=layer)
            if layer == MET1:
                met1_rects.append((x0, y0, x1, y1))

    # one via-1 landing per terminal label, centred on its strip
    for term, pts in label_pts.items():
        for (lx, ly) in _distinct(pts):
            strip = _strip_at(met1_rects, lx, ly)
            if strip is None:
                raise ValueError(f"{model}: label {term} at ({lx}, {ly}) is not on metal1")
            x0, y0, x1, y1 = strip
            w, h = x1 - x0, y1 - y0
            if min(w, h) < _VIA1_SIZE + 2 * _M1_VIA_ENC - 1e-6 and not (
                    min(w, h) >= _VIA1_SIZE + 1e-6):
                raise ValueError(f"{model}: {term} strip {min(w, h):.3f} um is too "
                                 f"narrow for a via-1 landing")
            # centre on the strip's centre-line along its narrow dimension
            cx = (x0 + x1) / 2.0 if w < h else _snap(lx)
            cy = (y0 + y1) / 2.0 if h <= w else _snap(ly)
            if w >= 2.0 and h >= 2.0:           # a plate (the emitter): its centre
                cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
            cx, cy = _snap(cx), _snap(cy)
            hv = _VIA1_SIZE / 2.0
            c.add_polygon([(cx - hv, cy - hv), (cx + hv, cy - hv),
                           (cx + hv, cy + hv), (cx - hv, cy + hv)], layer=VIA1)
            hp = _M2_PAD / 2.0
            c.add_polygon([(cx - hp, cy - hp), (cx + hp, cy - hp),
                           (cx + hp, cy + hp), (cx - hp, cy + hp)], layer=MET2)
            side = _side_of(flat, cx, cy)
            dirs = [side] if side else list(_DIRS)
            for d in dirs:
                name = f"{term.lower()}_{d}"
                if name in c.ports:
                    continue
                c.add_port(name=name, center=(cx, cy), width=_M2_PAD,
                           orientation=_DIRS[d], layer=MET2)
    # a plate terminal (emitter) exposes all four directions at its centre
    for term in terms:
        for d in _DIRS:
            name = f"{term.lower()}_{d}"
            if name not in c.ports:
                any_port = next((p for n, p in c.ports.items()
                                 if n.startswith(term.lower() + "_")), None)
                if any_port is not None:
                    c.add_port(name=name, center=tuple(any_port.center), width=_M2_PAD,
                               orientation=_DIRS[d], layer=MET2)
    _CACHE[key] = c
    return c


def _snap(v: float, grid: float = 0.005) -> float:
    return round(round(v / grid) * grid, 4)


def _distinct(pts):
    seen, out = set(), []
    for p in pts:
        k = (round(p[0], 3), round(p[1], 3))
        if k not in seen:
            seen.add(k)
            out.append(p)
    return out


def _strip_at(rects, x, y):
    """The smallest metal1 rectangle containing (x, y)."""
    hits = [r for r in rects if r[0] - 1e-6 <= x <= r[2] + 1e-6 and r[1] - 1e-6 <= y <= r[3] + 1e-6]
    if not hits:
        return None
    return min(hits, key=lambda r: (r[2] - r[0]) * (r[3] - r[1]))


def _side_of(cell, x, y):
    """Which side of the cell a point is nearest: N/E/S/W, or None for the centre."""
    (x0, y0), (x1, y1) = cell.bounding_box()
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    dx, dy = x - cx, y - cy
    if abs(dx) < 0.25 * (x1 - x0) and abs(dy) < 0.25 * (y1 - y0):
        return None
    if abs(dx) >= abs(dy):
        return "E" if dx > 0 else "W"
    return "N" if dy > 0 else "S"


# ── verification of the primitive itself ─────────────────────────────

def self_check(profile, model: str, workdir: os.PathLike) -> Dict[str, object]:
    """Extract one instance with Magic and report the device line it produces.

    Confirms that the imported, relabelled cell is still recognised as
    ``model`` and records Magic's terminal order, which LVS depends on.
    """
    from mbg.checks import extract_layout_netlist
    import gdsfactory as gf
    wd = Path(workdir)
    wd.mkdir(parents=True, exist_ok=True)
    cell = build_fixed_device(profile, model)
    top = gf.Component(f"chk_{model}")
    top << cell
    gds = wd / f"chk_{model}.gds"
    top.write_gds(str(gds))
    with profile.env():
        res = extract_layout_netlist(str(gds), cell_name=top.name, workdir=str(wd))
    text = ""
    path = res.get("netlist_path") if isinstance(res, dict) else res
    if path and Path(path).is_file():
        text = Path(path).read_text()
    lines = [l for l in text.splitlines() if model in l and not l.startswith("*")]
    return {"model": model, "extracted": bool(lines), "device_lines": lines[:4],
            "digest": hashlib.sha256(gds.read_bytes()).hexdigest()[:16]}
