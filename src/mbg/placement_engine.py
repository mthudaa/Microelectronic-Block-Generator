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
from mbg.passives import HRES_MIN_WIDTH, poly_resistor, mim_cap, RES_MIN_WIDTH, CAP_MIN_SIZE

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

        # ── n-well separation between PFETs ───────────────────────────
        # Every gLayout PMOS carries its own n-well, so two adjacent PFETs
        # are two wells. The GF180 deck checks well spacing by EXTRACTED
        # CONNECTIVITY (rule_decks/nwell.rb, conn_space(nwell, 0.6, 1.4)):
        # wells that are electrically joined get 0.6um (NW.2a_LV), wells
        # that are not get 1.4um (NW.2b_LV). Placement cannot know whether
        # the supply will actually reach a well tap, so it assumes the
        # conservative case.
        #
        # intra_cluster_gap alone is 1.0um -- BELOW the 1.4um the deck
        # requires -- which is precisely how a matched PFET pair lands in
        # NW.2b_LV. This gap is applied between horizontally adjacent PMOS
        # devices, on top of the ordinary cluster/channel gap.
        #
        # 1.5um rather than the deck's 1.4um is a deliberate 0.1um guard
        # band: the device bounding box and its n-well edge are not the
        # same line, and grid snapping moves both.
        # This is a HARD FLOOR between any two n-well islands, not a target.
        # There is deliberately no "they share a well" exemption: nothing in
        # this flow merges n-wells, so every PFET is its own island and an
        # exemption could only ever promise a merge that does not happen —
        # which produced two islands at the bare 1.0um cluster gap and a
        # guaranteed NW.2b_LV. If a device generator that genuinely merges
        # wells is added later, the post-placement measurement below will
        # report a single island and this spacing simply stops applying.
        self.nwell_spacing: float = kw.get("nwell_spacing", 1.5)
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

        # Placement hints — how an agent moves devices without a mouse. All
        # optional; with none given the floorplan is exactly the automatic one.
        #   rows   {dev: row}            row 0 is the top row
        #   order  {row: [dev, ...]}     left-to-right order; that row is not
        #                                reshuffled by the HPWL refinement
        #   groups [{kind, devices}]     keep these together as a matched set
        #   array  [{devices, cols, gap}] grid in row-major order (e.g. a 3x3
        #                                common-centroid PNP block)
        #   fixed  {dev: {x, y}}         lower-left corner of the device slot
        self.hints: dict = dict(kw.get("hints") or {})
        #: PDK profile; set from the DesignContext by place()
        self.profile = kw.get("profile")

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
    # The model and PDK are part of the identity: a ppolyf_u and a
    # ppolyf_u_1k of the same size are different drawings, and a process
    # switch must never reuse the other PDK's cell.
    key = (getattr(pdk, "name", str(id(pdk))), (dev.model or "").lower(), dev.kind,
           round(w, 6), round(l, 6), dev.fingers, dev.multipliers,
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
            min_w = HRES_MIN_WIDTH if model == "ppolyf_u_1k" else RES_MIN_WIDTH
            if w < min_w:
                raise UnsupportedDeviceError(
                    f"{dev.name}: W={w} um is below the minimum {min_w} um "
                    f"for a {model} resistor.")
            c = poly_resistor(width=w, length=l, model=model)
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
    elif dev.kind == "bjt":
        # Vertical BJTs are fixed foundry cells; see mbg.fixed_cells.
        profile = cfg.profile
        spec = profile.device(dev.model) if profile is not None else None
        if spec is None or not spec.layout:
            raise UnsupportedDeviceError(
                f"{dev.name}: no layout for BJT model '{dev.model}' in "
                f"{getattr(profile, 'name', 'this PDK')}")
        from mbg.fixed_cells import build_fixed_device
        c = build_fixed_device(profile, spec.model)
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
_NATIVE_RESISTOR_MODELS = {"ppolyf_u", "ppolyf_u_1k"}


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
    else:
        # fixed foundry cells (mbg.fixed_cells) name ports <terminal>_<dir>
        for term in dev.terminals:
            out[term] = [f"{term}_{d}" for d in _DIRECTIONS]
    return out


def _layer_name(rules, layer_spec) -> Optional[str]:
    try:
        if isinstance(layer_spec, (tuple, list)):
            dt = int(layer_spec[1]) if len(layer_spec) > 1 else None
            return rules.name_of_gds(int(layer_spec[0]), dt)
        return rules.name_of_gds(int(layer_spec))
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
            bb = BoundingBox(min(xs), min(ys), max(xs), max(ys))
            # A ring or L-shape modelled by its bounding box claims everything
            # it encloses — a tie ring would then "contain" the drain metal
            # inside it and read as a short. Such polygons (sky130 gLayout tie
            # rings, foundry BJT cells) are split into rectangles; plain
            # rectangles, all gf180 gLayout geometry, take the old path.
            if len(pts) > 4 and _poly_area(xs, ys) < 0.9 * bb.area:
                from mbg.fixed_cells import rect_decompose
                for (rx0, ry0, rx1, ry1) in rect_decompose(list(zip(xs, ys))):
                    boxes.append(BoundingBox(rx0, ry0, rx1, ry1))
            else:
                boxes.append(bb)
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


def _poly_area(xs, ys) -> float:
    n = len(xs)
    return abs(sum(xs[i] * ys[(i + 1) % n] - xs[(i + 1) % n] * ys[i]
                   for i in range(n))) / 2.0


# ── floorplan ──────────────────────────────────────────────────────────

def _needs_nwell_gap(ctx, a: str, b: str, cfg) -> bool:
    """Do these two horizontally adjacent devices sit in DIFFERENT n-wells?

    Every gLayout PMOS brings its own n-well, so two PFETs side by side are
    two wells and the deck's NW.2 spacing applies between them. NMOS sit in
    the shared p-substrate and have no n-well to space.

    There is no exemption. Nothing in this flow merges n-wells, so two PFETs
    are always two islands and the gap always applies.
    """
    da, db = ctx.devices.get(a), ctx.devices.get(b)
    return bool(da and db and _has_nwell(da) and _has_nwell(db))


def _has_nwell(dev: Device) -> bool:
    """PFETs and vertical PNPs (whose base is an n-well) each bring a well."""
    return dev.kind == "pmos" or (dev.kind == "bjt"
                                  and (dev.model or "").lower().startswith("pnp"))


def _gap_between(ctx, a: str, b: str, cfg, base: float) -> float:
    """Edge-to-edge gap to leave between two adjacent devices."""
    if _needs_nwell_gap(ctx, a, b, cfg):
        return max(base, cfg.nwell_spacing)
    return base


def _row_of(dev: Device) -> int:
    """PMOS on top, NMOS with a floating source in the middle, NMOS sitting
    on the rail at the bottom, passives below that."""
    if dev.kind == "pmos":
        return 0
    if dev.kind == "nmos":
        src = (dev.terminals.get("source") or "").lower()
        return 2 if src in ("vss", "gnd", "vgnd", "0") else 1
    if dev.kind == "bjt":
        return 4
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
        members = _symmetric_order(ctx, cl)
        gaps = sum(_gap_between(ctx, members[i], members[i + 1], cfg,
                                cfg.intra_cluster_gap)
                   for i in range(len(members) - 1))
        return sum(sizes[d][0] for d in cl) + gaps

    def layout(rows_map) -> Dict[str, Placement]:
        placements: Dict[str, Placement] = {}
        row_heights = {r: max(sizes[d][1] for cl in cls for d in cl)
                       for r, cls in rows_map.items()}
        def row_width(cls):
            total = sum(cluster_width(cl) for cl in cls)
            for i in range(len(cls) - 1):
                a = _symmetric_order(ctx, cls[i])[-1]
                b = _symmetric_order(ctx, cls[i + 1])[0]
                total += _gap_between(ctx, a, b, cfg, cfg.channel_x)
            return total

        row_widths = {r: row_width(cls) for r, cls in rows_map.items()}
        max_w = max(row_widths.values()) if row_widths else 0.0

        y = 0.0
        for r in sorted(rows_map, reverse=True):        # row 0 (PMOS) ends up on top
            x = -row_widths[r] / 2.0
            for cl in rows_map[r]:
                members = _symmetric_order(ctx, cl)
                for i, d in enumerate(members):
                    w, h = sizes[d]
                    placements[d] = Placement(instance=d, x=x, y=y,
                                              orientation="R0", row=r)
                    x += w
                    if i + 1 < len(members):
                        x += _gap_between(ctx, d, members[i + 1], cfg,
                                          cfg.intra_cluster_gap)
                    else:
                        last_in_cluster = d
                # Between clusters the channel is usually wider than the well
                # rule, but a PMOS ending one cluster and a PMOS starting the
                # next are still two neighbouring wells.
                nxt = rows_map[r][rows_map[r].index(cl) + 1] if \
                    rows_map[r].index(cl) + 1 < len(rows_map[r]) else None
                if nxt:
                    first_of_next = _symmetric_order(ctx, nxt)[0]
                    x += _gap_between(ctx, last_in_cluster, first_of_next,
                                      cfg, cfg.channel_x)
            y += row_heights[r] + cfg.channel_y
        return placements

    if cfg.hints:
        return _plan_with_hints(ctx, sizes, cfg)

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


# ── placement hints (the agent's hands) ────────────────────────────────

def _hint_devices(h: dict) -> List[str]:
    names = list((h.get("rows") or {}).keys()) + list((h.get("fixed") or {}).keys())
    for seq in (h.get("order") or {}).values():
        names += list(seq)
    for g in (h.get("groups") or []) + (h.get("array") or []):
        names += list(g.get("devices", []))
    return names


def _apply_hint_groups(ctx, cfg) -> None:
    """``groups`` hints become matching groups, ahead of the detected ones.

    A device named in a hinted group is taken out of any detected group, so
    the agent's grouping wins instead of fighting the detector.
    """
    from mbg.design_context import MatchingGroup
    unknown = sorted({d for d in _hint_devices(cfg.hints) if d not in ctx.devices})
    if unknown:
        raise ValueError(f"placement hints name unknown device(s) {unknown}; "
                         f"devices are {sorted(ctx.devices)}")
    hinted = {}
    taken = set()
    for i, g in enumerate(cfg.hints.get("groups") or []):
        devs = [d for d in g.get("devices", []) if d not in taken]
        if len(devs) >= 2:
            name = g.get("name") or f"hint_{i + 1}"
            hinted[name] = MatchingGroup(name, g.get("kind", "generic"), devs,
                                         bool(g.get("symmetric", True)))
            taken.update(devs)
    rest = {}
    for name, g in ctx.matching_groups.items():
        devs = [d for d in g.devices if d not in taken]
        if len(devs) >= 2:
            g.devices = devs
            rest[name] = g
    ctx.matching_groups = {**hinted, **rest}


def _plan_with_hints(ctx, sizes: Dict[str, Tuple[float, float]],
                     cfg: PlacementConfig) -> Dict[str, Placement]:
    """The floorplan with the agent's rows / order / arrays / fixed slots.

    Same row model as :func:`plan_floorplan` (row 0 on top, clusters left to
    right, n-well gaps between wells), with three differences: a hinted row
    keeps the given order and is not reshuffled; an ``array`` is one block
    laid out as a grid; ``fixed`` devices are moved to the given slot last,
    and any overlap that causes is reported, never silently resolved.
    """
    import math
    h = cfg.hints
    arrays = [dict(a) for a in (h.get("array") or [])]
    in_array = {d: i for i, a in enumerate(arrays) for d in a.get("devices", [])}
    clusters = []
    for cl in _cluster_devices(ctx):
        rest = [d for d in cl if d not in in_array and d in sizes]
        if rest:
            clusters.append(rest)
    for i, a in enumerate(arrays):
        clusters.append([d for d in a["devices"] if d in sizes])
    array_idx = {tuple(a["devices"]): a for a in arrays}

    row_hint = {d: int(r) for d, r in (h.get("rows") or {}).items()}
    order = {int(r): list(seq) for r, seq in (h.get("order") or {}).items()}

    def cluster_row(cl):
        for d in cl:
            if d in row_hint:
                return row_hint[d]
        for r, seq in order.items():
            if any(d in seq for d in cl):
                return r
        return _cluster_row(ctx, cl)

    rows: Dict[int, List[List[str]]] = {}
    for cl in clusters:
        rows.setdefault(cluster_row(cl), []).append(cl)
    for r, cls in rows.items():
        if r in order:
            seq = order[r]
            cls.sort(key=lambda cl: min([seq.index(d) for d in cl if d in seq] or [len(seq)]))

    def members(cl):
        if tuple(cl) in array_idx:
            return list(cl)
        for seq in order.values():
            if all(d in seq for d in cl):
                return sorted(cl, key=seq.index)
        return _symmetric_order(ctx, cl)

    def array_geom(cl):
        a = array_idx[tuple(cl)]
        cols = max(1, int(a.get("cols", len(cl))))
        nrow = int(math.ceil(len(cl) / cols))
        colw = max(sizes[d][0] for d in cl)
        rowh = max(sizes[d][1] for d in cl)
        gap = float(a.get("gap", cfg.intra_cluster_gap))
        if any(_has_nwell(ctx.devices[d]) for d in cl):
            gap = max(gap, cfg.nwell_spacing)
        return cols, nrow, colw, rowh, gap

    def dims(cl):
        if tuple(cl) in array_idx:
            cols, nrow, colw, rowh, gap = array_geom(cl)
            return cols * colw + (cols - 1) * gap, nrow * rowh + (nrow - 1) * gap
        ms = members(cl)
        w = sum(sizes[d][0] for d in ms) + sum(
            _gap_between(ctx, ms[i], ms[i + 1], cfg, cfg.intra_cluster_gap)
            for i in range(len(ms) - 1))
        return w, max(sizes[d][1] for d in ms)

    def layout(rows_map) -> Dict[str, Placement]:
        placements: Dict[str, Placement] = {}
        heights = {r: max(dims(cl)[1] for cl in cls) for r, cls in rows_map.items()}
        widths = {}
        for r, cls in rows_map.items():
            total = sum(dims(cl)[0] for cl in cls)
            for i in range(len(cls) - 1):
                total += _gap_between(ctx, members(cls[i])[-1], members(cls[i + 1])[0],
                                      cfg, cfg.channel_x)
            widths[r] = total
        y = 0.0
        for r in sorted(rows_map, reverse=True):
            x = -widths[r] / 2.0
            for k, cl in enumerate(rows_map[r]):
                if tuple(cl) in array_idx:
                    cols, nrow, colw, rowh, gap = array_geom(cl)
                    for i, d in enumerate(cl):
                        ci, ri = i % cols, i // cols
                        placements[d] = Placement(
                            instance=d, x=x + ci * (colw + gap),
                            y=y + (nrow - 1 - ri) * (rowh + gap), orientation="R0", row=r)
                    x += dims(cl)[0]
                else:
                    ms = members(cl)
                    for i, d in enumerate(ms):
                        placements[d] = Placement(instance=d, x=x, y=y,
                                                  orientation="R0", row=r)
                        x += sizes[d][0]
                        if i + 1 < len(ms):
                            x += _gap_between(ctx, d, ms[i + 1], cfg, cfg.intra_cluster_gap)
                if k + 1 < len(rows_map[r]):
                    x += _gap_between(ctx, members(cl)[-1], members(rows_map[r][k + 1])[0],
                                      cfg, cfg.channel_x)
            y += heights[r] + cfg.channel_y
        return placements

    def cost(pl):
        return _hpwl_of_order(ctx, {d: (p.x + sizes[d][0] / 2.0, p.y + sizes[d][1] / 2.0)
                                    for d, p in pl.items()})

    best = layout(rows)
    best_cost = cost(best)
    improved, passes = True, 0
    while improved and passes < cfg.refine_passes:
        improved, passes = False, passes + 1
        for r, cls in rows.items():
            if r in order:
                continue                         # the agent fixed this row's order
            for i in range(len(cls)):
                for j in range(i + 1, len(cls)):
                    cls[i], cls[j] = cls[j], cls[i]
                    cand = layout(rows)
                    c = cost(cand)
                    if c < best_cost - 1e-9:
                        best, best_cost, improved = cand, c, True
                    else:
                        cls[i], cls[j] = cls[j], cls[i]

    for d, pos in (h.get("fixed") or {}).items():
        if d in best:
            best[d] = Placement(instance=d, x=float(pos["x"]), y=float(pos["y"]),
                                orientation="R0", row=best[d].row)
    overlaps = []
    names = list(best)
    for i in range(len(names)):
        a = best[names[i]]
        wa, ha = sizes[names[i]]
        for j in range(i + 1, len(names)):
            b = best[names[j]]
            wb, hb = sizes[names[j]]
            if a.x < b.x + wb and b.x < a.x + wa and a.y < b.y + hb and b.y < a.y + ha:
                overlaps.append([names[i], names[j]])
    if overlaps:
        cfg.log(1, f"  [PLACEMENT] WARNING hinted placement overlaps: {overlaps}")
    ctx.metrics["hint_overlaps"] = overlaps
    ctx.metrics["placement_hints"] = sorted(k for k, v in h.items() if v)
    ctx.metrics["placement_weighted_hpwl"] = round(cost(best), 3)
    return best


# ── the placer ─────────────────────────────────────────────────────────

def place(ctx, pdk, cfg: Optional[PlacementConfig] = None) -> Component:
    """Generate devices, place them, and fully populate the DesignContext."""
    cfg = cfg or PlacementConfig()
    if ctx.rules is None:
        from mbg.pdk_rules import get_rules
        ctx.rules = get_rules(pdk)
    ctx.pdk = pdk
    if cfg.profile is None:
        cfg.profile = getattr(ctx, "profile", None)
    if cfg.hints:
        _apply_hint_groups(ctx, cfg)

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
            # Same reason as above: a device that is silently skipped here is
            # a layout that can never pass LVS, discovered three stages later.
            raise ValueError(f"cannot build {name} ({dev.model}): "
                             f"{type(e).__name__}: {e}") from e
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

    _report_nwell_spacing(ctx, top, cfg)

    cfg.log(1, f"  [PLACEMENT] {len(ctx.references)} devices, {n_ap} access points, "
               f"{n_ob} obstacle shapes, {len(ctx.reserved_zones)} reserved zones")
    return top


def _report_nwell_spacing(ctx, top, cfg) -> None:
    """Measure the n-well islands the floorplan actually produced.

    Placement reasons about device bounding boxes, but NW.2 is a rule about
    n-well polygons, and the two are not the same line. This measures the
    real geometry and records it, so the spacing claim is evidence rather
    than an assumption.

    It is also what would notice if a well-merging device generator were
    added later: the island count would drop and the spacing would stop
    applying on its own, without anyone having to remember to flip a flag.
    """
    import itertools
    from shapely.geometry import Polygon
    from shapely.ops import unary_union

    try:
        spec = tuple(ctx.pdk.get_glayer("nwell"))
    except Exception as e:                                  # noqa: BLE001
        cfg.log(1, f"  [PLACEMENT] n-well check skipped: no nwell layer ({e})")
        return
    # gdsfactory's by_spec mapping, the same idiom harvest_obstacles uses.
    # Reading the whole placed component (not per-ref) is deliberate: wells
    # only merge across device boundaries, which is exactly what is measured.
    polys = []
    try:
        for ref in ctx.references.values():
            by_spec = ref.get_polygons(by_spec=True)
            for pts in by_spec.get(spec, ()):
                if len(pts) >= 3:
                    polys.append(Polygon([(float(x), float(y)) for x, y in pts]))
    except Exception as e:                                  # noqa: BLE001
        cfg.log(1, f"  [PLACEMENT] n-well check skipped: {type(e).__name__}: {e}")
        return
    if not polys:
        cfg.log(2, "  [PLACEMENT] n-well check: no nwell geometry placed")
        return
    merged = unary_union(polys)
    islands = list(getattr(merged, "geoms", (merged,)))
    gaps = sorted(a.distance(b) for a, b in itertools.combinations(islands, 2)
                  if a.distance(b) > 1e-9)
    ctx.metrics["nwell_islands"] = len(islands)
    if gaps:
        ctx.metrics["nwell_min_gap_um"] = round(gaps[0], 4)
    # The floor is the PLACEMENT target (1.5um), not the deck minimum
    # (1.4um): the extra 0.1um is the guard band that absorbs the difference
    # between a device bounding box and its n-well edge after grid snapping.
    floor = float(cfg.nwell_spacing)
    deck = ctx.rules.nwell_spacing()
    if len(islands) <= 1:
        cfg.log(1, "  [PLACEMENT] n-well: one island — no well-to-well "
                   "spacing to rule on")
        return
    if not gaps:
        return
    worst = gaps[0]
    ctx.metrics["nwell_spacing_ok"] = bool(worst >= floor - 1e-6)
    if worst < floor - 1e-6:
        severity = "VIOLATION" if worst < deck - 1e-6 else "below target"
        cfg.log(0, f"  [PLACEMENT] n-well {severity}: {len(islands)} islands, "
                   f"min gap {worst:.3f}um < {floor}um floor "
                   f"(deck NW.2b_LV is {deck}um)")
    else:
        cfg.log(1, f"  [PLACEMENT] n-well: {len(islands)} islands, "
                   f"min gap {worst:.3f}um >= {floor}um floor "
                   f"(deck NW.2b_LV {deck}um)")


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
