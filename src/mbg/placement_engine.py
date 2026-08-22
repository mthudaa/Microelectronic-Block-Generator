"""
@Owner: Huda (Lead Analog / Mixed-Signal Designer)
@Role: Analog Layout Strategist
@Responsibility: Analog-aware placement that produces a *routable* floorplan.

Replaces the "stack devices in rows and hope" behaviour with a placer that
knows what the router will need:

  * correct device geometry      — SPICE W is a TOTAL width; gLayout wants
                                   per-finger width (see Device.finger_width)
  * matching / symmetry          — diff pairs straddle the axis, mirrors sit
                                   adjacent, matched devices share orientation
  * routing channels             — explicit gaps are reserved between rows and
                                   between clusters, not left to chance
  * pin accessibility            — access points are read back from the
                                   *transformed* reference, never cached from
                                   before the move (§17)
  * real obstacles               — device geometry is exported per layer from
                                   the actual gdsfactory polygons (§58)
  * routability feedback         — trial routing can widen channels and rerun

The legacy ``mbg.placement.placement()`` entry point is untouched apart from
its device-width bug fix, so existing scripts keep working.
"""
import math
from typing import Dict, List, Optional, Tuple

import gdsfactory as gf
from gdsfactory import Component
from glayout import nmos, pmos, resistor, mimcap, mimcap_array
from mbg.passives import poly_resistor, mim_cap, RES_MIN_WIDTH, CAP_MIN_SIZE

from mbg.design_context import (
    BoundingBox, Device, Obstacle, PinAccessPoint, Placement, Zone,
)


class PlacementConfig:
    """Every placement weight and spacing, in one place (§20)."""

    def __init__(self, **kw):
        # channels
        self.channel_x: float = kw.get("channel_x", 3.0)      # gap between clusters in a row
        self.channel_y: float = kw.get("channel_y", 6.0)      # gap between rows
        self.intra_cluster_gap: float = kw.get("intra_cluster_gap", 1.0)
        self.max_channel_x: float = kw.get("max_channel_x", 14.0)
        self.max_channel_y: float = kw.get("max_channel_y", 24.0)

        # cost weights (§20)
        self.w_wirelength: float = kw.get("w_wirelength", 1.0)
        self.w_congestion: float = kw.get("w_congestion", 2.0)
        self.w_symmetry: float = kw.get("w_symmetry", 25.0)
        self.w_matching: float = kw.get("w_matching", 10.0)

        # refinement
        self.refine_passes: int = kw.get("refine_passes", 40)
        self.trial_route: bool = kw.get("trial_route", True)
        self.max_placement_attempts: int = kw.get("max_placement_attempts", 3)

        # device generation
        # with_dnwell puts EVERY nmos in a deep n-well; dnwell_devices names
        # individual instances. Per-device is the normal case — a blanket DNW
        # roughly triples each device's area.
        self.with_dnwell: bool = kw.get("with_dnwell", False)
        self.dnwell_devices: set = set(kw.get("dnwell_devices", ()) or ())
        # Accept glayout's pfet-based resistor for a netlist that asked for a
        # passive one. The layout will not LVS-match; off by default.
        self.allow_active_resistor: bool = kw.get("allow_active_resistor", False)
        self.with_dummy: bool = kw.get("with_dummy", False)
        self.with_tie: bool = kw.get("with_tie", True)

        self.verbosity: int = kw.get("verbosity", 1)

    def log(self, level, msg):
        if self.verbosity >= level:
            print(msg)


# ── device generation ──────────────────────────────────────────────────

_DEV_CACHE: Dict[tuple, object] = {}


def build_device(pdk, dev: Device, cfg: PlacementConfig):
    """Create the gLayout primitive for one logical device.

    THE WIDTH FIX: SPICE ``W=8u nf=2`` means a device 8um wide built from two
    4um fingers.  gLayout's ``width`` argument is *per finger*
    ("fingers: introduces additional fingers ... of width=width"), so passing
    the SPICE W straight through made every multi-finger device nf x m times
    too wide.  Device.finger_width carries the corrected value.
    """
    w = dev.finger_width if dev.finger_width else (dev.width or 3.0)
    l = dev.length or 0.5
    dnw = _wants_dnwell(dev, cfg)
    key = (dev.kind, round(w, 6), round(l, 6), dev.fingers, dev.multipliers,
           dnw, cfg.with_dummy, cfg.with_tie)
    if key in _DEV_CACHE:
        return _DEV_CACHE[key]

    if dev.kind == "pmos":
        c = pmos(pdk, width=w, length=l, fingers=dev.fingers,
                 multipliers=dev.multipliers, with_substrate_tap=False,
                 with_tie=cfg.with_tie, with_dummy=cfg.with_dummy)
    elif dev.kind == "nmos":
        # A deep n-well needs a PCOMP guard ring around it, tied to the
        # substrate (GF180 rule DN.3). The internal body tie that makes body
        # biasing possible sits *inside* the DNW and does not satisfy it —
        # the ring has to be outside. glayout's substrate tap is exactly that
        # ring, so it is switched on for DNW devices and left off otherwise,
        # where it would only cost area (roughly 2.3x on a single device).
        c = nmos(pdk, width=w, length=l, fingers=dev.fingers,
                 multipliers=dev.multipliers, with_substrate_tap=dnw,
                 with_dnwell=dnw, with_tie=cfg.with_tie,
                 with_dummy=cfg.with_dummy)
    elif dev.kind == "res":
        # A netlist asking for a real passive resistor (ppolyf_u, npolyf_u,
        # ...) gets one built from PDK layers by mbg.passives, which Magic
        # extracts as that primitive with the right r_width/r_length.
        # glayout's resistor() is, in its own words, "a diode connected pfet
        # which acts as a programmable resistor" — it extracts as pfet_03v3
        # and can never LVS-match a passive model, so it is used only when the
        # netlist actually asked for a pfet-based resistor.
        model = (dev.model or "").lower()
        if model in _PASSIVE_RESISTOR_MODELS:
            if model not in _NATIVE_RESISTOR_MODELS:
                raise UnsupportedDeviceError(
                    f"{dev.name}: model '{dev.model}' is a passive resistor, but "
                    f"only {sorted(_NATIVE_RESISTOR_MODELS)} have a native "
                    f"generator. Building it from another primitive would put a "
                    f"different device in the layout and fail LVS.")
            if w < RES_MIN_WIDTH:
                raise UnsupportedDeviceError(
                    f"{dev.name}: W={w} um is below the PRES.1 minimum "
                    f"{RES_MIN_WIDTH} um for a poly resistor.")
            c = poly_resistor(width=w, length=l)
        else:
            # with_tie=True is required, not optional: without the well tie the
            # generated resistor violates DF.7 (N-well overlap of P-Diffusion)
            # on its own, before any routing touches it.
            c = resistor(pdk, width=w, length=l, multipliers=dev.multipliers,
                         with_substrate_tap=False, with_tie=True,
                         with_dnwell=cfg.with_dnwell)
    elif dev.kind == "cap":
        # gf180mcuD's Magic tech defines the MIM as "mimcc mimcap metal5" over
        # metal4. glayout builds its MIM on met2/met3, so Magic recognises
        # nothing and the capacitor silently disappears from the extracted
        # netlist. mbg.passives builds the metal4/metal5 stack the PDK expects.
        size = max(w, l)
        if size < CAP_MIN_SIZE:
            raise UnsupportedDeviceError(
                f"{dev.name}: MIM top plate {size} um is below the MIMTM.8a "
                f"minimum {CAP_MIN_SIZE} um. gf180 has no smaller MIM.")
        c = mim_cap(size=size)
    else:
        raise ValueError(f"no generator for device kind {dev.kind!r} ({dev.name})")

    _DEV_CACHE[key] = c
    return c


# ── terminal → port mapping (§15) ──────────────────────────────────────

_MOS_PORT_TEMPLATES = {
    "drain": "multiplier_0_drain_{d}",
    "gate": "multiplier_0_gate_{d}",
    "source": "multiplier_0_source_{d}",
}
# Native passives (mbg.passives) expose "<terminal>_<N|E|S|W>" on met1 for the
# resistor and met5/met4 for the two capacitor plates. The glayout fallbacks
# name their terminals differently, so both sets are tried; the earlier
# templates ("multiplier_0_1_{d}") matched nothing at all, which is why
# passives used to harvest zero access points and could not be routed.
_RES_PORT_TEMPLATES = {"p": "p_{d}", "n": "n_{d}"}
_RES_PORT_FALLBACK = {"p": "pfet_drain_{d}", "n": "pfet_source_{d}"}

_CAP_PORT_TEMPLATES = {"p": "p_{d}", "n": "n_{d}"}
_CAP_PORT_FALLBACK = {"p": "top_met_{d}", "n": "bottom_met_{d}"}

_DIRECTIONS = ("N", "E", "S", "W")

# Real passive resistors in the GF180MCU model set. glayout has no generator
# for these; see build_device() for why that matters.
_PASSIVE_RESISTOR_MODELS = {
    "ppolyf_u", "npolyf_u", "ppolyf_u_1k", "nplus_u", "pplus_u",
    "rm1", "rm2", "rm3", "tm6k", "tm9k", "tm11k", "tm30k", "nwell",
}

# Of those, the ones mbg.passives can actually build and that Magic extracts
# with the correct r_width/r_length. The rest have no generator; building them
# from a different primitive would silently put the wrong device in the layout.
_NATIVE_RESISTOR_MODELS = {"ppolyf_u"}


class UnsupportedDeviceError(NotImplementedError):
    """A netlist device the available primitives cannot build faithfully."""


def _wants_dnwell(dev, cfg) -> bool:
    """Whether this device gets a deep n-well.

    Three ways to ask, in order of precedence: the device was named in
    ``PlacementConfig.dnwell_devices``; the config turned it on for every
    NMOS; or the netlist implies it, because the device's bulk is not on the
    global ground and therefore cannot share the substrate.
    """
    if dev.kind != "nmos":
        return False
    if dev.name in (cfg.dnwell_devices or ()):
        return True
    if cfg.with_dnwell:
        return True
    return bool(getattr(dev, "needs_dnwell", False))



def terminal_port_names(dev: Device) -> Dict[str, List[str]]:
    """Explicit, generator-aware mapping from a SPICE terminal to the
    physical port names gLayout emits.  Nothing is guessed later (§15)."""
    out: Dict[str, List[str]] = {}
    if dev.is_mos:
        for term, tmpl in _MOS_PORT_TEMPLATES.items():
            out[term] = [tmpl.format(d=d) for d in _DIRECTIONS]
        out["body"] = [f"tie_{d}_top_met_{d}" for d in _DIRECTIONS]
    elif dev.kind in ("res", "cap"):
        native, fallback = ((_RES_PORT_TEMPLATES, _RES_PORT_FALLBACK)
                            if dev.kind == "res"
                            else (_CAP_PORT_TEMPLATES, _CAP_PORT_FALLBACK))
        for term, tmpl in native.items():
            out[term] = ([tmpl.format(d=d) for d in _DIRECTIONS]
                         + [fallback[term].format(d=d) for d in _DIRECTIONS])
    return out


def _layer_name(rules, layer_spec) -> Optional[str]:
    try:
        lyr = layer_spec[0] if isinstance(layer_spec, (tuple, list)) else layer_spec
        return rules.name_of_gds(int(lyr))
    except Exception:
        return None


def harvest_access_points(ctx, dev: Device, ref, cfg: PlacementConfig) -> int:
    """Read access points back from the TRANSFORMED reference (§17/§26).

    Called strictly after the reference has been moved, and never cached
    across a later move — the placer re-harvests if it moves anything.
    """
    rules = ctx.rules
    n = 0
    names = terminal_port_names(dev)
    available = set(ref.ports)
    for term, candidates in names.items():
        net = dev.terminals.get(term)
        if not net:
            continue
        found = [p for p in candidates if p in available]
        if not found and term == "body":
            # some generators expose the tie only on one side
            found = [p for p in available if p.startswith("tie_") and "top_met" in p]
        for pname in found:
            port = ref.ports[pname]
            lname = _layer_name(rules, port.layer)
            if lname is None:
                continue
            ap = PinAccessPoint(
                instance=dev.name, terminal=term, net=net, layer=lname,
                x=float(port.center[0]), y=float(port.center[1]),
                orientation=float(port.orientation), port=port,
                direction=pname.rsplit("_", 1)[-1],
                width=float(getattr(port, "width", 0.0) or 0.0),
            )
            ctx.add_access_point(ap)
            n += 1
    return n


def harvest_obstacles(ctx, dev_name: str, ref, cfg: PlacementConfig) -> int:
    """Export real transformed device geometry as routing obstacles, and
    attribute each shape to a net (§58 + §40).

    Net attribution matters: a wire that merges with the drain's own metal is
    fine, the identical wire merging with the neighbouring source is a short,
    and a wire that neither merges nor clears either of them is a notch
    violation.  The router cannot tell those apart without ownership.

    Attribution works per (device, layer) by connected components: polygons
    that touch each other are one piece of metal, so a net discovered at any
    port in the component labels the whole component.  Testing only the
    polygon directly under a port attributed ~13% of the shapes; component
    propagation attributes essentially all of the connected metal.
    """
    rules = ctx.rules
    try:
        polys = ref.get_polygons(by_spec=True)
    except Exception:
        return 0

    dev_aps = [ap for aps in ctx.net_to_access.values() for ap in aps
               if ap.instance == dev_name]

    n = 0
    for spec, plist in polys.items():
        lname = _layer_name(rules, spec)
        if lname is None:
            continue
        try:
            tol = rules.manufacturing_grid()
        except Exception:
            tol = 0.005

        boxes = []
        for pts in plist:
            xs = [float(p[0]) for p in pts]
            ys = [float(p[1]) for p in pts]
            boxes.append(BoundingBox(min(xs), min(ys), max(xs), max(ys)))
        if not boxes:
            continue

        # connected components over touching polygons
        parent = list(range(len(boxes)))

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        def union(i, j):
            ri, rj = find(i), find(j)
            if ri != rj:
                parent[rj] = ri

        for i in range(len(boxes)):
            gi = boxes[i].inflate(tol)
            for j in range(i + 1, len(boxes)):
                if gi.overlaps(boxes[j]):
                    union(i, j)

        comp_net = {}
        ambiguous = set()
        aps_here = [ap for ap in dev_aps if ap.layer == lname]
        for i, bb in enumerate(boxes):
            grown = bb.inflate(tol)
            for ap in aps_here:
                if grown.contains_point(ap.x, ap.y):
                    r = find(i)
                    if r in comp_net and comp_net[r] != ap.net:
                        ambiguous.add(r)     # two nets on one piece of metal
                    comp_net.setdefault(r, ap.net)

        for i, bb in enumerate(boxes):
            r = find(i)
            net = None if r in ambiguous else comp_net.get(r)
            ctx.add_obstacle(Obstacle(layer=lname, bbox=bb, owner=dev_name,
                                      kind="device_geometry", net=net))
            n += 1
    return n


# ── floorplan ──────────────────────────────────────────────────────────

def _row_of(dev: Device) -> int:
    """PMOS on top, NMOS with a floating source in the middle, NMOS sitting
    on the rail at the bottom, passives below that."""
    if dev.kind == "pmos":
        return 0
    if dev.kind == "nmos":
        src = (dev.terminals.get("source") or "").lower()
        return 2 if src in ("vss", "gnd", "vgnd", "0") else 1
    return 3


def _cluster_devices(ctx) -> List[List[str]]:
    """Matching groups stay together; everything else is a singleton (§57)."""
    clustered = set()
    clusters: List[List[str]] = []
    for g in ctx.matching_groups.values():
        members = [d for d in g.devices if d in ctx.devices and d not in clustered]
        if len(members) >= 2:
            clusters.append(members)
            clustered.update(members)
    for name in ctx.devices:
        if name not in clustered:
            clusters.append([name])
    return clusters


def _cluster_row(ctx, cluster: List[str]) -> int:
    return min(_row_of(ctx.devices[d]) for d in cluster)


def _symmetric_order(ctx, cluster: List[str]) -> List[str]:
    """Order a matched cluster so the axis falls in its middle (§21)."""
    if len(cluster) != 2:
        return sorted(cluster)
    return sorted(cluster)


def _hpwl_of_order(ctx, positions: Dict[str, Tuple[float, float]]) -> float:
    """Weighted HPWL over device centres — the wirelength term of the
    placement cost (§19/§20)."""
    total = 0.0
    for net_name, net in ctx.nets.items():
        pts = [positions[d] for d, _t in net.terminals if d in positions]
        if len(pts) < 2:
            continue
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        total += ctx.net_weight(net_name) * ((max(xs) - min(xs)) + (max(ys) - min(ys)))
    return total


def plan_floorplan(ctx, sizes: Dict[str, Tuple[float, float]],
                   cfg: PlacementConfig) -> Dict[str, Placement]:
    """Decide (x, y, orientation) for every device.

    Rows are assigned by device role, clusters are kept intact, and cluster
    order inside a row is improved by swap moves against weighted HPWL so the
    placement is connectivity-aware rather than arbitrary.
    """
    clusters = _cluster_devices(ctx)
    rows: Dict[int, List[List[str]]] = {}
    for cl in clusters:
        rows.setdefault(_cluster_row(ctx, cl), []).append(cl)

    def cluster_width(cl):
        return (sum(sizes[d][0] for d in cl)
                + cfg.intra_cluster_gap * (len(cl) - 1))

    def layout(rows_map) -> Dict[str, Placement]:
        placements: Dict[str, Placement] = {}
        row_heights = {r: max(sizes[d][1] for cl in cls for d in cl)
                       for r, cls in rows_map.items()}
        row_widths = {r: (sum(cluster_width(cl) for cl in cls)
                          + cfg.channel_x * max(0, len(cls) - 1))
                      for r, cls in rows_map.items()}
        max_w = max(row_widths.values()) if row_widths else 0.0

        y = 0.0
        for r in sorted(rows_map, reverse=True):        # row 0 (PMOS) ends up on top
            x = -row_widths[r] / 2.0
            for cl in rows_map[r]:
                members = _symmetric_order(ctx, cl)
                for d in members:
                    w, h = sizes[d]
                    placements[d] = Placement(instance=d, x=x, y=y,
                                              orientation="R0", row=r)
                    x += w + cfg.intra_cluster_gap
                x += cfg.channel_x - cfg.intra_cluster_gap
            y += row_heights[r] + cfg.channel_y
        return placements

    # connectivity-aware ordering: greedy swaps inside each row (§19)
    best = layout(rows)
    best_cost = _hpwl_of_order(ctx, {d: (p.x + sizes[d][0] / 2.0,
                                         p.y + sizes[d][1] / 2.0)
                                     for d, p in best.items()})
    improved = True
    passes = 0
    while improved and passes < cfg.refine_passes:
        improved = False
        passes += 1
        for r, cls in rows.items():
            for i in range(len(cls)):
                for j in range(i + 1, len(cls)):
                    cls[i], cls[j] = cls[j], cls[i]
                    cand = layout(rows)
                    cost = _hpwl_of_order(ctx, {d: (p.x + sizes[d][0] / 2.0,
                                                    p.y + sizes[d][1] / 2.0)
                                                for d, p in cand.items()})
                    if cost < best_cost - 1e-9:
                        best, best_cost = cand, cost
                        improved = True
                    else:
                        cls[i], cls[j] = cls[j], cls[i]
    cfg.log(2, f"  [PLACEMENT] floorplan refined in {passes} passes, "
               f"weighted HPWL={best_cost:.2f}")
    ctx.metrics["placement_weighted_hpwl"] = round(best_cost, 3)
    return best


# ── the placer ─────────────────────────────────────────────────────────

def place(ctx, pdk, cfg: Optional[PlacementConfig] = None) -> Component:
    """Generate devices, place them, and fully populate the DesignContext."""
    cfg = cfg or PlacementConfig()
    if ctx.rules is None:
        from mbg.pdk_rules import get_rules
        ctx.rules = get_rules(pdk)
    ctx.pdk = pdk

    # Matched devices must share isolation. A differential pair with a deep
    # n-well on one side and not the other is not a matched pair at all — the
    # bulk conditions differ — so isolation propagates across the group.
    for g in ctx.matching_groups.values():
        members = [ctx.devices[d] for d in g.devices if d in ctx.devices]
        if any(_wants_dnwell(d, cfg) for d in members):
            for d in members:
                if d.kind == "nmos" and not _wants_dnwell(d, cfg):
                    d.needs_dnwell = True
                    ctx.deep_nwell_flags[d.name] = True
                    cfg.log(1, f"  [PLACEMENT] {d.name}: deep n-well added to match "
                               f"{g.name} ({g.kind})")

    # 1. build every device once so we know its true size
    comps: Dict[str, object] = {}
    sizes: Dict[str, Tuple[float, float]] = {}
    pads: Dict[str, float] = {}
    for name, dev in ctx.devices.items():
        try:
            c = build_device(pdk, dev, cfg)
        except UnsupportedDeviceError:
            # Never silently drop a device the netlist asked for — a layout
            # missing a device cannot match it, and the reason must reach the
            # caller rather than a log line.
            raise
        except Exception as e:
            cfg.log(1, f"  [PLACEMENT] cannot build {name} ({dev.model}): {e}")
            continue
        comps[name] = c
        bb = c.bbox
        w_dev = float(bb[1][0] - bb[0][0])
        h_dev = float(bb[1][1] - bb[0][1])
        # A deep n-well must stand clear of neighbouring wells (LPW.11 and
        # friends). The device bbox already contains the DNW, so the clearance
        # has to come from the floorplan: reserve it as padding around the slot.
        pad = ctx.rules.dnwell_spacing() if _wants_dnwell(dev, cfg) else 0.0
        pads[name] = pad
        sizes[name] = (w_dev + 2 * pad, h_dev + 2 * pad)
        cfg.log(2, f"  [PLACEMENT] {name}: W_total={dev.width} nf={dev.fingers} "
                   f"-> finger_w={dev.finger_width} size={sizes[name][0]:.2f}"
                   f"x{sizes[name][1]:.2f}um")

    if not comps:
        raise ValueError("no devices could be generated")

    # 2. floorplan
    placements = plan_floorplan(ctx, sizes, cfg)

    # 3. instantiate and harvest — ports are read AFTER the move (§17)
    top = Component(name=ctx.name)
    ctx.component = top
    ctx.references.clear()
    ctx.net_to_access.clear()
    ctx.terminal_to_ports.clear()
    ctx.obstacles.clear()
    ctx.reserved_zones.clear()
    ctx.device_bboxes.clear()
    ctx.placements.clear()

    n_ap = n_ob = 0
    for name, comp in comps.items():
        p = placements.get(name)
        if p is None:
            continue
        ref = top << comp
        ref.name = name
        local = comp.bbox
        pad = pads.get(name, 0.0)          # sit centred inside the padded slot
        ref.movex(p.x + pad - float(local[0][0]))
        ref.movey(p.y + pad - float(local[0][1]))
        ctx.references[name] = ref

        bb = BoundingBox.from_gf(ref.bbox)
        ctx.add_placement(p, bb)
        dev = ctx.devices[name]
        n_ap += harvest_access_points(ctx, dev, ref, cfg)
        n_ob += harvest_obstacles(ctx, name, ref, cfg)

        # device-local interconnect is reserved from general routing (§27)
        ctx.add_zone(Zone(kind="device_local", bbox=bb,
                          layers=["met1", "met2"], owner=name))
        ctx.deep_nwell_flags[name] = bool(cfg.with_dnwell and dev.kind == "nmos")
        cfg.log(1, f"  [PLACEMENT] {name} -> x={bb.xmin:.2f}, y={bb.ymin:.2f}, "
                   f"orientation={p.orientation}, row={p.row}")

    # symmetry report (§76) — measured, not asserted
    for sc in ctx.symmetry_constraints:
        a, b = ctx.device_bboxes.get(sc.device_a), ctx.device_bboxes.get(sc.device_b)
        if a and b:
            err = abs(a.height - b.height) + abs(a.width - b.width)
            cfg.log(1, f"  [PLACEMENT] matched pair {sc.device_a}/{sc.device_b} "
                       f"geometry mismatch = {err:.3f}um")
            ctx.metrics[f"symmetry_err_{sc.group}"] = round(err, 4)

    cfg.log(1, f"  [PLACEMENT] {len(ctx.references)} devices, {n_ap} access points, "
               f"{n_ob} obstacle shapes, {len(ctx.reserved_zones)} reserved zones")
    return top


def place_with_routability(ctx, pdk, cfg: Optional[PlacementConfig] = None,
                           router_cfg=None):
    """Placement with trial-routing feedback (§29/§30).

    Runs a trial route on the current floorplan; if nets cannot be attached,
    widens the channels and replaces, up to ``max_placement_attempts``.
    Returns (component, PlacementFeedback).
    """
    from mbg.design_context import PlacementFeedback
    from mbg.router import GridRouter, RouterConfig

    cfg = cfg or PlacementConfig()
    attempt = 0
    feedback = PlacementFeedback()
    top = None

    while attempt < cfg.max_placement_attempts:
        attempt += 1
        top = place(ctx, pdk, cfg)
        if not cfg.trial_route:
            return top, feedback

        trial_cfg = router_cfg or RouterConfig(verbosity=max(0, cfg.verbosity - 1))
        trial = GridRouter(ctx, trial_cfg)
        result = trial.run()

        feedback = PlacementFeedback(
            unrouted_nets=list(result["failed"]),
            congestion_regions=(ctx.routing_congestion.hotspots(1.0)
                                if ctx.routing_congestion else []),
            failures=list(ctx.failures),
            excessive_detours=[p.net for rn in ctx.routed_nets.values()
                               for p in rn.plans
                               if p.detour_factor > trial_cfg.detour_limit],
        )
        cfg.log(1, f"  [FEEDBACK] attempt {attempt}: "
                   f"{len(result['routed'])} routed, "
                   f"{len(feedback.unrouted_nets)} unroutable, "
                   f"{len(feedback.congestion_regions)} congested regions")

        if feedback.clean:
            return top, feedback

        for f in feedback.failures[:5]:
            cfg.log(1, f"  [FEEDBACK] net {f.net}: {f.cause} — {f.suggested_action}")

        if attempt >= cfg.max_placement_attempts:
            break
        # placement response: open the channels the router could not get through
        cfg.channel_x = min(cfg.max_channel_x, cfg.channel_x * 1.6)
        cfg.channel_y = min(cfg.max_channel_y, cfg.channel_y * 1.5)
        cfg.log(1, f"  [FEEDBACK] widening channels -> x={cfg.channel_x:.1f} "
                   f"y={cfg.channel_y:.1f} and replacing")
        ctx.clear_routing()

    return top, feedback
