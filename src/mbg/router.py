"""
@Owner: Huda (Lead Analog / Mixed-Signal Designer)
@Role: Analog Layout Strategist
@Responsibility: DRC-aware multi-layer maze router (A* + negotiated rip-up).

Why this is a new module rather than more code inside routing.py
----------------------------------------------------------------
``core/routing.py`` implements a *shape* router: it tries a fixed catalogue of
I/L/Z/U wire shapes between two ports and gives up when none of them fits.
That algorithm cannot express detours, cannot share a corridor, and cannot
negotiate congestion, so the fixes required by the brief (grid search, real
occupancy, via legality, rip-up-and-reroute) are not edits to it — they are a
different algorithm.  Rather than tangle the two, the new engine lives here
and ``routing.auto_router`` delegates to it.  Every legacy entry point in
routing.py keeps working unchanged.

Design
------
    node        = (ix, iy, layer_index)
    edges       = step in preferred/non-preferred direction, via up, via down
    cost        = length + bend + via + congestion(present + history) + policy
    legality    = obstacle inflation (spacing + half width) checked during
                  expansion, never after the path is complete
    ownership   = every emitted Segment and Via carries its net (§40)
"""
import heapq
import math
from typing import Dict, List, Optional, Sequence, Set, Tuple

from mbg.design_context import (
    BoundingBox, CongestionMap, Obstacle, PinAccessPoint, RoutePlan,
    RoutedNet, RoutingFailure, Segment, Via,
)


# ── tuning (all overridable via RouterConfig, nothing hidden) ───────────

class RouterConfig:
    """Every weight the router uses.  No tuning constant is hidden
    elsewhere in the codebase (§20)."""

    def __init__(self, **kw):
        # layer policy (§33/§34): general routing stays off the device-local
        # metals unless a layer is explicitly allowed here.
        self.routing_layers: List[str] = kw.get("routing_layers", ["met3", "met4", "met5"])
        self.access_layer: str = kw.get("access_layer", "met3")

        # geometry
        self.width_multiplier: float = kw.get("width_multiplier", 1.0)
        self.power_width_multiplier: float = kw.get("power_width_multiplier", 2.0)
        self.grid_pitch: Optional[float] = kw.get("grid_pitch", None)   # None => derive from PDK
        self.margin: float = kw.get("margin", 6.0)

        # A* costs
        self.bend_cost: float = kw.get("bend_cost", 1.0)
        self.via_cost: float = kw.get("via_cost", 4.0)
        self.wrong_direction_cost: float = kw.get("wrong_direction_cost", 1.6)
        self.congestion_weight: float = kw.get("congestion_weight", 2.0)
        self.history_weight: float = kw.get("history_weight", 1.0)
        self.sensitive_spacing_mult: float = kw.get("sensitive_spacing_mult", 2.0)

        # search / iteration limits
        self.max_escape_steps: int = kw.get("max_escape_steps", 6)
        # Extra clearance on top of the PDK spacing rule, in manufacturing
        # grid units.  Absorbs the difference between our bounding-box model
        # and the real polygon edges after grid snapping, which otherwise
        # leaves sub-0.05um notches that Magic reports as spacing errors.
        self.drc_margin_grids: float = kw.get("drc_margin_grids", 4.0)
        self.max_expansions: int = kw.get("max_expansions", 400_000)
        self.ripup_iterations: int = kw.get("ripup_iterations", 8)
        self.detour_limit: float = kw.get("detour_limit", 4.0)

        self.verbosity: int = kw.get("verbosity", 1)

    def log(self, level: int, msg: str):
        if self.verbosity >= level:
            print(msg)


class AccessChoice:
    """The terminal port the router selected, plus where its via lands.

    ``(vx, vy)`` may sit outside the port itself: the escape runs on the
    port's own metal until there is room for a via pad (§26).
    """
    __slots__ = ("ap", "vx", "vy", "legal", "_boxes")

    def __init__(self, ap, vx, vy, legal=True):
        self.ap, self.vx, self.vy = ap, vx, vy
        self.legal = legal

    @property
    def net(self):
        return self.ap.net


# ── occupancy ──────────────────────────────────────────────────────────

class OccupancyDB:
    """Net-aware occupancy over the routing grid (§41).

    A cell is stored per (layer, ix, iy).  ``blocked_for`` answers the only
    question the search asks: may net N use this cell?  Same-net reuse is
    allowed (that is how a routing tree merges); foreign-net occupancy and
    hard obstacles are not.
    """

    def __init__(self, layers: Sequence[str]):
        self.layers = list(layers)
        self.occ: Dict[str, Dict[Tuple[int, int], str]] = {l: {} for l in self.layers}
        self.hard: Dict[str, Set[Tuple[int, int]]] = {l: set() for l in self.layers}
        self.hard_owner: Dict[str, Dict[Tuple[int, int], str]] = {l: {} for l in self.layers}
        self.history: Dict[str, Dict[Tuple[int, int], float]] = {l: {} for l in self.layers}
        self.present: Dict[str, Dict[Tuple[int, int], int]] = {l: {} for l in self.layers}
        # Cells a specific net may use despite a hard obstacle. Obstacle cells
        # are marked with a conservative inflation meant for wires; an access
        # landing is checked exactly (overlap-or-clear against real geometry),
        # so the coarse rule must not veto what the exact rule approved.
        self.exempt: Dict[str, Dict[Tuple[int, int], Set[str]]] = {l: {} for l in self.layers}

    # -- obstacles (never removed) --
    def block(self, layer: str, cell: Tuple[int, int], owner: str = ""):
        if layer in self.hard:
            self.hard[layer].add(cell)
            if owner:
                self.hard_owner[layer][cell] = owner

    def is_hard(self, layer: str, cell: Tuple[int, int]) -> bool:
        return cell in self.hard.get(layer, ())

    def hard_owner_of(self, layer: str, cell: Tuple[int, int]) -> str:
        return self.hard_owner.get(layer, {}).get(cell, "")

    # -- routes (removable for rip-up) --
    def claim(self, layer: str, cell: Tuple[int, int], net: str):
        if layer not in self.occ:
            return
        self.occ[layer][cell] = net
        self.present[layer][cell] = self.present[layer].get(cell, 0) + 1

    def release_net(self, net: str):
        for layer in self.layers:
            drop = [c for c, n in self.occ[layer].items() if n == net]
            for c in drop:
                del self.occ[layer][c]
                if c in self.present[layer]:
                    self.present[layer][c] -= 1
                    if self.present[layer][c] <= 0:
                        del self.present[layer][c]

    def release_all(self):
        for layer in self.layers:
            self.occ[layer].clear()
            self.present[layer].clear()

    def owner(self, layer: str, cell: Tuple[int, int]) -> Optional[str]:
        return self.occ.get(layer, {}).get(cell)

    def allow(self, layer: str, cell: Tuple[int, int], net: str):
        """Record that `net` may use `cell` despite a hard obstacle there."""
        if layer in self.exempt:
            self.exempt[layer].setdefault(cell, set()).add(net)

    def is_exempt(self, layer: str, cell: Tuple[int, int], net: str) -> bool:
        return net in self.exempt.get(layer, {}).get(cell, ())

    def blocked_for(self, layer: str, cell: Tuple[int, int], net: str) -> bool:
        if (self.is_hard(layer, cell) and self.hard_owner_of(layer, cell) != net
                and not self.is_exempt(layer, cell, net)):
            return True
        o = self.owner(layer, cell)
        return o is not None and o != net

    # -- negotiated congestion (§46/§47) --
    def bump_history(self, factor: float = 1.0):
        for layer in self.layers:
            for cell, n in self.present[layer].items():
                if n > 1:
                    self.history[layer][cell] = self.history[layer].get(cell, 0.0) + factor

    def penalise(self, layer: str, cell: Tuple[int, int], factor: float = 1.0):
        self.history[layer][cell] = self.history[layer].get(cell, 0.0) + factor

    def cost_of(self, layer: str, cell: Tuple[int, int], cfg: RouterConfig) -> float:
        h = self.history.get(layer, {}).get(cell, 0.0)
        p = self.present.get(layer, {}).get(cell, 0)
        return cfg.history_weight * h + cfg.congestion_weight * p


# ── the router ─────────────────────────────────────────────────────────

def grid_params(ctx, cfg=None):
    """The routing grid (origin, pitch) for a context.

    Exposed so power rails can place their via drops on the same tracks the
    router uses. Off-grid drops are the one thing the pitch cannot keep legal:
    everything else the router emits is grid-aligned by construction.

    The origin depends only on device bounding boxes, never on rail geometry,
    so calling this before or after rails are added gives the same answer.
    """
    from mbg.pdk_rules import get_rules
    cfg = cfg or RouterConfig()
    rules = ctx.rules or get_rules(ctx.pdk)
    layers = [l for l in cfg.routing_layers if rules.has_layer(l)]
    sp = max(rules.min_spacing(l) for l in layers)
    widest_wire = max(rules.min_width(l) for l in layers) * max(
        cfg.width_multiplier, cfg.power_width_multiplier)
    widest_pad = 0.0
    for lo in rules.metals:
        for hi in layers:
            try:
                widest_pad = max(widest_pad, rules.via_footprint(lo, hi))
            except Exception:
                continue
    half = max(widest_wire, widest_pad) / 2.0
    pitch = cfg.grid_pitch or rules.snap(2 * half + sp + rules.manufacturing_grid())
    bb = ctx.design_bbox().inflate(cfg.margin)
    return (rules.snap(bb.xmin), rules.snap(bb.ymin)), pitch


def snap_to_grid(ctx, x, y, cfg=None):
    """Nearest routing-grid intersection to (x, y)."""
    (ox, oy), pitch = grid_params(ctx, cfg)
    from mbg.pdk_rules import get_rules
    rules = ctx.rules or get_rules(ctx.pdk)
    return (rules.snap(ox + round((x - ox) / pitch) * pitch),
            rules.snap(oy + round((y - oy) / pitch) * pitch))


class GridRouter:
    """Multi-layer A* router driven entirely by the DesignContext (§32)."""

    def __init__(self, ctx, config: Optional[RouterConfig] = None):
        self.ctx = ctx
        self.cfg = config or RouterConfig()
        self.rules = ctx.rules
        if self.rules is None:
            raise ValueError("DesignContext.rules is not set — call "
                             "build_design_context(config, pdk) first")

        self.layers = [l for l in self.cfg.routing_layers if self.rules.has_layer(l)]
        if not self.layers:
            raise ValueError(f"none of {self.cfg.routing_layers} exist in this PDK")
        self.li = {l: i for i, l in enumerate(self.layers)}

        self.pitch = self.cfg.grid_pitch or self._derive_pitch()
        bb = ctx.design_bbox().inflate(self.cfg.margin)
        self.origin = (self.rules.snap(bb.xmin), self.rules.snap(bb.ymin))
        self.nx = max(1, int(math.ceil(bb.width / self.pitch)) + 1)
        self.ny = max(1, int(math.ceil(bb.height / self.pitch)) + 1)

        self.occ = OccupancyDB(self.layers)
        self._chosen_access: Optional[Dict[Tuple[str, str], object]] = None
        self._access_failures: List[RoutingFailure] = []
        self._load_obstacles()
        self.select_access_points()
        self._reserve_access_cells()
        self._block_escape_corridors()

    # -- grid helpers --
    def _derive_pitch(self) -> float:
        """Grid pitch that is legal for the WIDEST object the router emits.

        Two objects on distinct grid cells are then always at least
        min_spacing apart, whatever they are:

            gap = pitch - half_widest - half_widest >= min_spacing

        Sizing the pitch from the minimum wire width (the obvious choice)
        silently breaks as soon as a wide power wire or a via landing pad —
        both larger than a signal wire — sits on a neighbouring track.  One
        extra grid unit of margin keeps the comparison off the equality
        boundary where float rounding lives.
        """
        s = max(self.rules.min_spacing(l) for l in self.layers)
        widest_wire = max(self.rules.min_width(l) for l in self.layers) * max(
            self.cfg.width_multiplier, self.cfg.power_width_multiplier)
        widest_pad = 0.0
        for lo in self.rules.metals:
            for hi in self.layers:
                try:
                    widest_pad = max(widest_pad, self.rules.via_footprint(lo, hi))
                except Exception:
                    continue
        half = max(widest_wire, widest_pad) / 2.0
        return self.rules.snap(2 * half + s + self.rules.manufacturing_grid())

    def to_cell(self, x: float, y: float) -> Tuple[int, int]:
        return (int(round((x - self.origin[0]) / self.pitch)),
                int(round((y - self.origin[1]) / self.pitch)))

    def to_xy(self, ix: int, iy: int) -> Tuple[float, float]:
        return (self.rules.snap(self.origin[0] + ix * self.pitch),
                self.rules.snap(self.origin[1] + iy * self.pitch))

    def in_bounds(self, ix: int, iy: int) -> bool:
        return 0 <= ix < self.nx and 0 <= iy < self.ny

    # -- obstacles (§44 inflation, §58 from real geometry) --
    def _load_obstacles(self):
        n = 0
        for ob in self.ctx.obstacles:
            if ob.layer not in self.li:
                continue
            w = self.rules.min_width(ob.layer)
            sp = self.rules.min_spacing(ob.layer)
            inflated = ob.bbox.inflate(sp + w / 2.0)
            c0 = self.to_cell(inflated.xmin, inflated.ymin)
            c1 = self.to_cell(inflated.xmax, inflated.ymax)
            for ix in range(c0[0], c1[0] + 1):
                for iy in range(c0[1], c1[1] + 1):
                    if self.in_bounds(ix, iy):
                        self.occ.block(ob.layer, (ix, iy), ob.net or ob.owner)
                        n += 1
        # reserved device-local zones are protected from general routing (§27)
        for z in self.ctx.reserved_zones:
            for lname in z.layers:
                if lname not in self.li:
                    continue
                w = self.rules.min_width(lname)
                sp = self.rules.min_spacing(lname)
                bb = z.bbox.inflate(sp + w / 2.0)
                c0 = self.to_cell(bb.xmin, bb.ymin)
                c1 = self.to_cell(bb.xmax, bb.ymax)
                for ix in range(c0[0], c1[0] + 1):
                    for iy in range(c0[1], c1[1] + 1):
                        if self.in_bounds(ix, iy):
                            self.occ.block(lname, (ix, iy), z.net or "")
                            n += 1
        self.cfg.log(1, f"  [ROUTER] obstacle cells marked: {n} "
                        f"(grid {self.nx}x{self.ny} @ {self.pitch}um, layers {self.layers})")

    def _reserve_access_cells(self):
        """Reserve the via landing itself for its own net.

        Only what is physically required: any grid cell close enough that a
        foreign wire there would violate spacing against the via pad.  An
        earlier version reserved the whole port->via->track corridor, which
        walled terminals into their own escape channel and turned routable
        nets into BLOCKED ones.
        """
        lname = self.cfg.access_layer
        sp = self.rules.min_spacing(lname)
        wire_half = self.rules.routing_width(
            lname, self.cfg.power_width_multiplier) / 2.0
        contested = 0
        for (inst, term), ch in (self._chosen_access or {}).items():
            if not ch.legal:
                continue
            ap = ch.ap
            need = self._via_pad(ap) / 2.0 + sp + wire_half
            reach = int(math.floor(need / self.pitch))
            cx, cy = self.to_cell(ch.vx, ch.vy)
            # The landing passed the exact geometric check in
            # _find_via_landing, so let this net stand on it even if the
            # conservative obstacle inflation covered the cell.
            self.occ.allow(lname, (cx, cy), ap.net)
            for dx in range(-reach, reach + 1):
                for dy in range(-reach, reach + 1):
                    c = (cx + dx, cy + dy)
                    if not self.in_bounds(*c):
                        continue
                    owner = self.occ.owner(lname, c)
                    if owner is None:
                        self.occ.claim(lname, c, ap.net)
                    elif owner != ap.net:
                        contested += 1
        if contested:
            self.cfg.log(2, f"  [ROUTER] {contested} via-landing cells contested "
                            f"between nets (resolved by routing priority)")

    def _block_escape_corridors(self):
        """Keep routed track out of a notch against a committed escape leg.

        Escape legs are off-grid — they run from the port to the via landing
        on the port's own metal — so nothing in the occupancy grid described
        them. The maze router could therefore lay a track parallel to a leg
        and only 0.13um away, which Magic reports as "Metal3 spacing < 0.28um"
        even though both shapes belong to the same net: proximity without
        overlap is a notch regardless of connectivity (§45).

        The corridor is blocked with a neutral owner so the leg's *own* net
        avoids it too. The via landing itself stays reachable because
        _reserve_access_cells exempts that cell for the net.
        """
        n = 0
        for (inst, term), ch in (self._chosen_access or {}).items():
            if not ch.legal:
                continue
            ap = ch.ap
            # The legs run on the PORT's own metal, which is not necessarily
            # cfg.access_layer — a met3 capacitor pad escapes on met3.
            # Blocking the wrong layer silently protects nothing.
            lname = ap.layer
            if lname not in self.li:
                continue
            sp = self.rules.min_spacing(lname)
            wire_half = self.rules.routing_width(
                lname, self.cfg.power_width_multiplier) / 2.0
            landing = self.to_cell(ch.vx, ch.vy)
            legs = self._escape_path(ap, ch.vx, ch.vy)
            widths = self._leg_widths(ap, len(legs))
            for (x1, y1, x2, y2), w in zip(legs, widths):
                half = w / 2.0
                box = BoundingBox(min(x1, x2) - half, min(y1, y2) - half,
                                  max(x1, x2) + half, max(y1, y2) + half)
                grown = box.inflate(sp + 2 * wire_half)
                c0 = self.to_cell(grown.xmin, grown.ymin)
                c1 = self.to_cell(grown.xmax, grown.ymax)
                for ix in range(c0[0], c1[0] + 1):
                    for iy in range(c0[1], c1[1] + 1):
                        if not self.in_bounds(ix, iy) or (ix, iy) == landing:
                            continue
                        cx, cy = self.to_xy(ix, iy)
                        foot = BoundingBox(cx - wire_half, cy - wire_half,
                                           cx + wire_half, cy + wire_half)
                        if foot.overlaps(box):
                            # merges with the leg: fine for this net, a short
                            # for anyone else.
                            self.occ.block(lname, (ix, iy), ap.net)
                        elif foot.inflate(sp).overlaps(box):
                            # the notch band — too close to merge, too close
                            # to clear. Nobody may route here, this net least
                            # of all, because it is the one that would notch.
                            self.occ.block(lname, (ix, iy), "")
                        else:
                            continue        # genuinely clear, leave it usable
                        n += 1
        if n:
            self.cfg.log(2, f"  [ROUTER] {n} cells blocked alongside pin escapes")
        return n

    # -- routing width policy --
    def width_for(self, net: str) -> float:
        mult = (self.cfg.power_width_multiplier
                if self.ctx.is_power_or_ground(net) else self.cfg.width_multiplier)
        return self.rules.routing_width(self.cfg.access_layer, mult)

    # -- access point selection (§16) --
    def _via_pad(self, ap) -> float:
        if ap.layer == self.cfg.access_layer:
            return self.rules.min_width(self.cfg.access_layer)
        return self.rules.via_footprint(ap.layer, self.cfg.access_layer)

    def _device_shapes(self, layers) -> List[Tuple[BoundingBox, Optional[str]]]:
        """Real device metal on ``layers`` with its net owner, cached."""
        key = tuple(layers)
        cache = getattr(self, "_shape_cache", None)
        if cache is None:
            cache = self._shape_cache = {}
        if key not in cache:
            wanted = set(layers)
            cache[key] = [(ob.bbox, ob.net) for ob in self.ctx.obstacles
                          if ob.layer in wanted]
        return cache[key]

    def _metal_legal(self, box: BoundingBox, net: str, layers) -> bool:
        """May this piece of metal exist here?

        Against every real device shape on the same layers, exactly one of
        two things must hold:

            it OVERLAPS the shape  -> legal only if the shape is the same net
                                      (the two merge into one conductor)
            it CLEARS the shape    -> by at least min_spacing

        Anything in between is a notch: same-net proximity is NOT
        automatically DRC-clean (§45), and it is what Magic reported as
        "Metal2 spacing < 0.28um" after the escapes were added.
        """
        sp = (max(self.rules.min_spacing(l) for l in layers)
              + self.cfg.drc_margin_grids * self.rules.manufacturing_grid())
        grown = box.inflate(sp)
        for bb, obnet in self._device_shapes(layers):
            if box.overlaps(bb):
                if obnet != net:
                    return False          # short, or merging with unknown metal
            elif grown.overlaps(bb):
                return False              # notch / spacing violation
        return True

    def _choice_boxes(self, ch):
        """Every piece of metal a committed access choice puts down:
        its via pad and its escape legs, each with the layers it occupies."""
        cached = getattr(ch, "_boxes", None)
        if cached is not None:
            return cached
        ap = ch.ap
        half = self._via_pad(ap) / 2.0
        out = [(BoundingBox(ch.vx - half, ch.vy - half,
                            ch.vx + half, ch.vy + half),
                self.rules.layers_traversed(ap.layer, self.cfg.access_layer))]
        legs = self._escape_path(ap, ch.vx, ch.vy)
        for (x1, y1, x2, y2), w in zip(legs, self._leg_widths(ap, len(legs))):
            h = w / 2.0
            out.append((BoundingBox(min(x1, x2) - h, min(y1, y2) - h,
                                    max(x1, x2) + h, max(y1, y2) + h),
                        [ap.layer]))
        try:
            object.__setattr__(ch, "_boxes", out)
        except Exception:
            pass
        return out

    def _leg_widths(self, ap, nlegs: int) -> List[float]:
        """Width of each pin-escape leg on the port's own metal.

        The leg that runs INTO the via is widened to the pad size; the rest
        stay at minimum width.  A narrow wire meeting a wider pad leaves a
        sub-DRC slit alongside it — our own geometry violating metal spacing
        against itself — while widening every leg makes the escapes so bulky
        that neighbouring terminals stop finding legal landings at all.
        Widening only the last leg fixes the slit and costs nothing.
        """
        base = self.rules.routing_width(ap.layer)
        pad = self._via_pad(ap)
        if nlegs <= 0:
            return []
        return [base] * (nlegs - 1) + [max(base, pad)]

    def _escape_width(self, ap) -> float:
        """Worst-case escape width, used for clearance checks."""
        return max(self.rules.routing_width(ap.layer), self._via_pad(ap))

    def _pad_box(self, ap) -> BoundingBox:
        h = self._via_pad(ap) / 2.0
        return BoundingBox(ap.x - h, ap.y - h, ap.x + h, ap.y + h)

    def _access_conflict(self, cand, other) -> bool:
        """Would a via pad on ``cand`` clash with the real metal of ``other``?

        ``other`` is any access point of a different net — including the ones
        the router did not choose, because that metal exists on the device
        whether or not the router uses it.  Checking only the chosen points
        let a via pad on a drain overlap the neighbouring source of the very
        same transistor.
        """
        cuts = self.rules.via_stack_between(cand.layer, self.cfg.access_layer)
        sep = max((c.cut_spacing for c in cuts), default=0.36)
        try:
            mw = self.rules.min_width(other.layer)
        except Exception:
            mw = 0.28
        return self._pad_box(cand).inflate(sep).overlaps(other.footprint(mw))

    def select_access_points(self) -> Dict[Tuple[str, str], object]:
        """Pick ONE physical access point per logical terminal.

        A gLayout MOS terminal exposes N/E/S/W ports that are already tied
        together inside the device, so exactly one of them should carry the
        route out.  Choosing all of them (the previous behaviour) sprayed via
        stacks across the cell and shorted neighbouring terminals together.

        Selection order: terminals with the fewest legal options first, then
        the candidate nearest its net centroid, rejecting any candidate whose
        via would clash with an already-committed one on a different net.
        """
        by_terminal: Dict[Tuple[str, str], List[object]] = {}
        centroid: Dict[str, Tuple[float, float]] = {}
        for net, aps in self.ctx.net_to_access.items():
            if aps:
                centroid[net] = (sum(a.x for a in aps) / len(aps),
                                 sum(a.y for a in aps) / len(aps))
            for ap in aps:
                ix, iy = self.to_cell(ap.x, ap.y)
                if self.in_bounds(ix, iy):
                    by_terminal.setdefault((ap.instance, ap.terminal), []).append(ap)

        # every access point in the design is real device metal, so a via pad
        # must clear all of them, not only the ones the router selects
        all_points = [a for aps in self.ctx.net_to_access.values() for a in aps]

        chosen: Dict[Tuple[str, str], AccessChoice] = {}
        committed: List[AccessChoice] = []
        self._access_failures: List[RoutingFailure] = []
        rejected = 0

        for key in sorted(by_terminal, key=lambda k: (len(by_terminal[k]), k)):
            cands = by_terminal[key]
            cx, cy = centroid.get(cands[0].net, (cands[0].x, cands[0].y))
            cands = sorted(cands, key=lambda a: abs(a.x - cx) + abs(a.y - cy))
            pick = None
            for ap in cands:
                landing = self._find_via_landing(ap, all_points, committed)
                if landing is None:
                    rejected += 1
                    continue
                pick = AccessChoice(ap=ap, vx=landing[0], vy=landing[1])
                break
            if pick is None:
                # No legal landing anywhere on this terminal.  Mark it illegal
                # and leave it unrouted: emitting the via anyway would place a
                # pad on top of a neighbouring net, i.e. manufacture a short
                # and then report the net as successfully routed (§82).
                ap = cands[0]
                pick = AccessChoice(ap=ap, vx=ap.x, vy=ap.y, legal=False)
                self._access_failures.append(RoutingFailure(
                    net=ap.net, cause="NO_LEGAL_VIA",
                    region=BoundingBox(ap.x - 1, ap.y - 1, ap.x + 1, ap.y + 1),
                    blocking_instances=[ap.instance],
                    suggested_action="increase device spacing so this terminal "
                                     "gains a via landing site",
                    detail=f"{key[0]}.{key[1]} has no clash-free via landing on "
                           f"any of its {len(cands)} ports"))
            chosen[key] = pick
            if pick.legal:
                committed.append(pick)

        bad = sum(1 for c in chosen.values() if not c.legal)
        self.cfg.log(1 if bad else 2,
                     f"  [ROUTER] access points: {len(chosen)} terminals, "
                     f"{rejected} candidates rejected for via clash"
                     + (f", {bad} terminals with NO legal landing" if bad else ""))
        self._chosen_access = chosen
        return chosen

    def _normal(self, ap) -> Tuple[float, float]:
        o = ap.orientation % 360
        if abs(o) < 45 or abs(o - 360) < 45:
            return (1.0, 0.0)
        if abs(o - 90) < 45:
            return (0.0, 1.0)
        if abs(o - 180) < 45:
            return (-1.0, 0.0)
        return (0.0, -1.0)

    def _escape_path(self, ap, gx, gy):
        """The two legs of the pin escape, on the port's own metal.

        Leaves the port along its normal first, then turns to reach the grid
        intersection where the via goes up.  Returns [] when the port already
        sits on the intersection.
        """
        ox, oy = self._normal(ap)
        legs = []
        if abs(ox) > 0:
            if abs(gx - ap.x) > 1e-9:
                legs.append((ap.x, ap.y, gx, ap.y))
            if abs(gy - ap.y) > 1e-9:
                legs.append((gx, ap.y, gx, gy))
        else:
            if abs(gy - ap.y) > 1e-9:
                legs.append((ap.x, ap.y, ap.x, gy))
            if abs(gx - ap.x) > 1e-9:
                legs.append((ap.x, gy, gx, gy))
        return legs

    def _find_via_landing(self, ap, all_points, committed):
        """Where may this terminal's via stack land?

        Two requirements drive this:

        1. A gLayout device is ringed by its own tie/tap metal, so the via
           pad frequently does not fit directly on the port.  We step outward
           along the port normal until it does.
        2. The landing must be a GRID INTERSECTION.  Landing off-grid forces
           a met3 stub to reach the nearest track, and those stubs are the one
           piece of met3 the pitch cannot keep legal — they were the source of
           every remaining spacing violation.  Escaping on the port's own
           metal (met2, the designated pin-escape layer) all the way to the
           intersection removes them entirely, so *all* met3 geometry is
           grid-aligned and legal by construction.
        """
        ox, oy = self._normal(ap)
        cuts = self.rules.via_stack_between(ap.layer, self.cfg.access_layer)
        sep = max((c.cut_spacing for c in cuts), default=0.36)
        half = self._via_pad(ap) / 2.0
        esc_half = self._escape_width(ap) / 2.0
        esc_sp = self.rules.min_spacing(ap.layer)

        touched = self.rules.layers_traversed(ap.layer, self.cfg.access_layer)
        # Candidate landings: a neighbourhood around the port, ordered so the
        # port's own outward direction is tried first.  Searching only along
        # the normal is too rigid for small single-finger devices, whose
        # terminals are packed closer than a via pad plus its spacing — those
        # nets simply became unroutable.
        R = self.cfg.max_escape_steps
        base = self.to_cell(ap.x, ap.y)
        cand = []
        for dx in range(-R, R + 1):
            for dy in range(-R, R + 1):
                cell = (base[0] + dx, base[1] + dy)
                if not self.in_bounds(*cell):
                    continue
                gx, gy = self.to_xy(*cell)
                along = (gx - ap.x) * ox + (gy - ap.y) * oy      # >0 = outward
                lateral = abs((gx - ap.x) * oy) + abs((gy - ap.y) * ox)
                cand.append((0 if along >= -1e-9 else 1,          # outward first
                             round(lateral, 4),                   # then straight
                             round(abs(along), 4),                # then close
                             cell))
        cand.sort()

        seen = set()
        for _o, _lat, _al, cell in cand:
            if cell in seen:
                continue
            seen.add(cell)
            gx, gy = self.to_xy(*cell)

            pad = BoundingBox(gx - half, gy - half, gx + half, gy + half)
            if not self._metal_legal(pad, ap.net, touched):
                continue

            legs = self._escape_path(ap, gx, gy)
            lw = self._leg_widths(ap, len(legs))
            boxes = [(pad, touched)]
            for (x1, y1, x2, y2), w in zip(legs, lw):
                h = w / 2.0
                boxes.append((BoundingBox(
                    min(x1, x2) - h, min(y1, y2) - h,
                    max(x1, x2) + h, max(y1, y2) + h), [ap.layer]))

            bad = False
            for box, layers in boxes:
                if not self._metal_legal(box, ap.net, layers):
                    bad = True
                    break
                # against everything already committed, on every shared layer:
                # overlap is legal only for the same net, and anything closer
                # than min_spacing without overlapping is a notch (§45).
                for c in committed:
                    for obox, olayers in self._choice_boxes(c):
                        shared = set(layers) & set(olayers)
                        if not shared:
                            continue
                        sp2 = max(self.rules.min_spacing(l) for l in shared)
                        if box.overlaps(obox):
                            if c.ap.net != ap.net:
                                bad = True
                                break
                        elif box.inflate(sp2).overlaps(obox):
                            bad = True
                            break
                    if bad:
                        break
                if bad:
                    break
            if bad:
                continue
            return (gx, gy)
        return None

    # -- terminal cells --
    def escape_cell(self, ch) -> Tuple[int, int]:
        """Grid cell the via lands on — chosen to be an exact intersection so
        no off-grid stub is needed on the routing layer."""
        return self.to_cell(ch.vx, ch.vy)

    def terminal_groups(self, net: str) -> List[List[Tuple[int, int, int]]]:
        """One group per logical terminal, holding the single chosen access
        node for that terminal."""
        if getattr(self, "_chosen_access", None) is None:
            self.select_access_points()
        li_access = self.li[self.cfg.access_layer]
        groups = []
        for (inst, term), ch in self._chosen_access.items():
            if ch.net != net or not ch.legal:
                continue
            cell = self.escape_cell(ch)
            if self.in_bounds(*cell):
                groups.append([(cell[0], cell[1], li_access)])
        return groups

    # -- A* --
    def _heuristic(self, node, targets_xy) -> float:
        ix, iy, lz = node
        best = float("inf")
        for (tx, ty, tz) in targets_xy:
            d = (abs(ix - tx) + abs(iy - ty)) * self.pitch
            d += abs(lz - tz) * self.cfg.via_cost
            best = min(best, d)
        return best

    def _search(self, net: str, sources: List[Tuple[int, int, int]],
                targets: Set[Tuple[int, int, int]],
                target_list: List[Tuple[int, int, int]]
                ) -> Tuple[Optional[List[Tuple[int, int, int]]], str]:
        """A* from any source node to any target node.  Returns (path, reason)."""
        if not sources or not targets:
            return None, "NO_PIN_ESCAPE"

        openq = []
        gscore: Dict[Tuple[int, int, int], float] = {}
        parent: Dict[Tuple[int, int, int], Optional[Tuple[int, int, int]]] = {}
        usable_source = False
        for s in sources:
            if self.occ.blocked_for(self.layers[s[2]], (s[0], s[1]), net):
                continue
            usable_source = True
            gscore[s] = 0.0
            parent[s] = None
            heapq.heappush(openq, (self._heuristic(s, target_list), 0.0, s))
        if not usable_source:
            return None, "NO_PIN_ESCAPE"

        expansions = 0
        while openq:
            _f, g, node = heapq.heappop(openq)
            if g > gscore.get(node, float("inf")):
                continue
            if node in targets:
                path = []
                cur = node
                while cur is not None:
                    path.append(cur)
                    cur = parent[cur]
                return list(reversed(path)), "OK"

            expansions += 1
            if expansions > self.cfg.max_expansions:
                return None, "SEARCH_EXHAUSTED"

            ix, iy, lz = node
            lname = self.layers[lz]
            prev = parent.get(node)
            pdir = None
            if prev is not None and prev[2] == lz:
                pdir = (ix - prev[0], iy - prev[1])

            # planar moves
            pref = self.rules.preferred_direction(lname)
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx_, ny_ = ix + dx, iy + dy
                if not self.in_bounds(nx_, ny_):
                    continue
                if self.occ.blocked_for(lname, (nx_, ny_), net):
                    continue
                step = self.pitch
                moving_h = dx != 0
                if (pref == "H") != moving_h:
                    step *= self.cfg.wrong_direction_cost
                if pdir is not None and (dx, dy) != pdir:
                    step += self.cfg.bend_cost
                step += self.occ.cost_of(lname, (nx_, ny_), self.cfg)
                nxt = (nx_, ny_, lz)
                ng = g + step
                if ng < gscore.get(nxt, float("inf")):
                    gscore[nxt] = ng
                    parent[nxt] = node
                    heapq.heappush(openq, (ng + self._heuristic(nxt, target_list), ng, nxt))

            # via moves
            for dz in (1, -1):
                nz = lz + dz
                if not (0 <= nz < len(self.layers)):
                    continue
                nlname = self.layers[nz]
                if self.occ.blocked_for(nlname, (ix, iy), net):
                    continue
                if not self._via_is_legal(net, ix, iy, lname, nlname):
                    continue
                step = self.cfg.via_cost + self.occ.cost_of(nlname, (ix, iy), self.cfg)
                nxt = (ix, iy, nz)
                ng = g + step
                if ng < gscore.get(nxt, float("inf")):
                    gscore[nxt] = ng
                    parent[nxt] = node
                    heapq.heappush(openq, (ng + self._heuristic(nxt, target_list), ng, nxt))

        return None, "BLOCKED"

    def _via_is_legal(self, net: str, ix: int, iy: int,
                      lower: str, upper: str) -> bool:
        """Reject an illegal via *before* committing it (§42/§43).

        The via pad is larger than the wire, so it must clear foreign
        occupancy on both metals over its whole footprint, not just at the
        centre cell.
        """
        vi = self.rules.via_between(lower, upper) or self.rules.via_between(upper, lower)
        if vi is None:
            return False
        pad = vi.min_pad()
        x, y = self.to_xy(ix, iy)
        for lname in (lower, upper):
            sp = self.rules.min_spacing(lname)
            reach = int(math.ceil((pad / 2.0 + sp) / self.pitch))
            for dx in range(-reach, reach + 1):
                for dy in range(-reach, reach + 1):
                    c = (ix + dx, iy + dy)
                    if not self.in_bounds(*c):
                        return False
                    if self.occ.blocked_for(lname, c, net):
                        return False
        return True

    # -- one net --
    def route_net(self, net: str) -> Tuple[Optional[RoutePlan], Optional[RoutingFailure]]:
        stranded = [f"{k[0]}.{k[1]}" for k, ch in (self._chosen_access or {}).items()
                    if ch.net == net and not ch.legal]
        if stranded:
            ap = next(ch.ap for k, ch in self._chosen_access.items()
                      if ch.net == net and not ch.legal)
            return None, RoutingFailure(
                net=net, cause="NO_LEGAL_VIA",
                region=BoundingBox(ap.x - 1, ap.y - 1, ap.x + 1, ap.y + 1),
                blocking_instances=sorted({s.split(".")[0] for s in stranded}),
                suggested_action="increase device spacing so these terminals "
                                 "gain via landing sites",
                detail=f"terminals with no legal via landing: {stranded}")

        groups = self.terminal_groups(net)
        if len(groups) < 2:
            return None, None                     # nothing to connect

        width = self.width_for(net)
        plan = RoutePlan(net=net)

        # seed the tree with the first terminal's access nodes
        tree: Set[Tuple[int, int, int]] = set(groups[0])
        self._commit_access(plan, net, groups[0], width)

        # Steiner-ish growth: attach each remaining terminal to the nearest
        # point already on the tree (§39) — never back to a single root.
        remaining = groups[1:]
        remaining.sort(key=lambda grp: self._group_distance(grp, tree))

        manhattan_total = 0.0
        for grp in remaining:
            targets = set(tree)
            path, reason = self._search(net, grp, targets, list(targets))
            if path is None:
                # try the other direction before declaring failure
                path, reason = self._search(net, list(tree), set(grp), list(grp))
            if path is None:
                return None, RoutingFailure(
                    net=net, cause=reason,
                    region=self._group_bbox(grp),
                    blocking_instances=self._blockers(grp),
                    suggested_action=self._suggestion(reason),
                    detail=f"could not attach terminal group at "
                           f"{[self.to_xy(c[0], c[1]) for c in grp[:2]]}")
            self._commit_access(plan, net, grp, width)
            manhattan_total += self._group_distance(grp, tree)
            self._commit_path(plan, net, path, width)
            tree.update(path)
            tree.update(grp)

        plan.manhattan_min = manhattan_total
        actual = plan.wire_length()
        plan.detour_factor = (actual / manhattan_total) if manhattan_total > 1e-9 else 1.0
        return plan, None

    def _group_distance(self, grp, tree) -> float:
        best = float("inf")
        for (ax, ay, az) in grp:
            for (bx, by, bz) in tree:
                d = (abs(ax - bx) + abs(ay - by)) * self.pitch
                best = min(best, d)
        return 0.0 if best == float("inf") else best

    def _group_bbox(self, grp) -> BoundingBox:
        pts = [self.to_xy(c[0], c[1]) for c in grp]
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        return BoundingBox(min(xs) - self.pitch, min(ys) - self.pitch,
                           max(xs) + self.pitch, max(ys) + self.pitch)

    def _blockers(self, grp) -> List[str]:
        out: Set[str] = set()
        for (ix, iy, lz) in grp:
            lname = self.layers[lz]
            for dx in range(-2, 3):
                for dy in range(-2, 3):
                    o = self.occ.hard_owner_of(lname, (ix + dx, iy + dy))
                    if o:
                        out.add(o)
        return sorted(out)

    @staticmethod
    def _suggestion(reason: str) -> str:
        return {
            "NO_PIN_ESCAPE": "increase spacing around the instance so the "
                             "terminal gains a legal escape",
            "BLOCKED": "open a routing channel between the blocking instances",
            "SEARCH_EXHAUSTED": "reduce congestion or enlarge the routing area",
            "NO_LEGAL_VIA": "make room for a via landing pad",
        }.get(reason, "review placement near this net")

    # -- committing --
    def _commit_access(self, plan: RoutePlan, net: str,
                       grp: List[Tuple[int, int, int]], width: float):
        """Drop the access via stack for the CHOSEN port of this terminal
        only, and record occupancy on every metal the stack passes through so
        that no other net can land a via on top of it."""
        li_access = self.li[self.cfg.access_layer]
        for (inst, term), ch in (self._chosen_access or {}).items():
            if ch.net != net or not ch.legal:
                continue
            ap = ch.ap
            cell = self.escape_cell(ch)
            if (cell[0], cell[1], li_access) not in grp:
                continue
            px, py = self.rules.snap_xy(ch.vx, ch.vy)

            # Each terminal needs its OWN escape wire even when two terminals
            # of the same net share a via landing.  Skipping the whole block
            # on a duplicate via left the second terminal with no metal at
            # all — an open that the router still reported as routed.
            legs = self._escape_path(ap, px, py)
            for (x1, y1, x2, y2), ew in zip(legs, self._leg_widths(ap, len(legs))):
                plan.segments.append(Segment(
                    net=net, layer=ap.layer,
                    x1=self.rules.snap(x1), y1=self.rules.snap(y1),
                    x2=self.rules.snap(x2), y2=self.rules.snap(y2), width=ew))

            # the via itself is shared, so emit it only once
            already = any(abs(v.x - px) < 1e-6 and abs(v.y - py) < 1e-6
                          for v in plan.vias)
            if not already and ap.layer != self.cfg.access_layer:
                size = self.rules.via_footprint(ap.layer, self.cfg.access_layer)
                plan.vias.append(Via(net=net, x=px, y=py, lower=ap.layer,
                                     upper=self.cfg.access_layer, size=size))

            for lname in self.rules.layers_traversed(ap.layer, self.cfg.access_layer):
                if lname in self.li:
                    self.occ.claim(lname, cell, net)

    def _commit_path(self, plan: RoutePlan, net: str,
                     path: List[Tuple[int, int, int]], width: float):
        """Turn A* nodes into Segments + Vias (§37 stage 2) and claim cells."""
        for (ix, iy, lz) in path:
            self.occ.claim(self.layers[lz], (ix, iy), net)

        run_start = path[0]
        for k in range(1, len(path)):
            prev, cur = path[k - 1], path[k]
            if cur[2] != prev[2]:                       # layer change => via
                self._emit_segment(plan, net, run_start, prev, width)
                x, y = self.to_xy(prev[0], prev[1])
                lo, hi = self.layers[min(prev[2], cur[2])], self.layers[max(prev[2], cur[2])]
                plan.vias.append(Via(net=net, x=x, y=y, lower=lo, upper=hi,
                                     size=self.rules.via_footprint(lo, hi)))
                run_start = cur
                continue
            # direction change => close the straight run
            if k + 1 < len(path):
                nxt = path[k + 1]
                if nxt[2] == cur[2]:
                    d1 = (cur[0] - prev[0], cur[1] - prev[1])
                    d2 = (nxt[0] - cur[0], nxt[1] - cur[1])
                    if d1 != d2:
                        self._emit_segment(plan, net, run_start, cur, width)
                        run_start = cur
        self._emit_segment(plan, net, run_start, path[-1], width)

    def _emit_segment(self, plan: RoutePlan, net: str, a, b, width: float):
        if a[:2] == b[:2]:
            return
        x1, y1 = self.to_xy(a[0], a[1])
        x2, y2 = self.to_xy(b[0], b[1])
        plan.segments.append(Segment(net=net, layer=self.layers[a[2]],
                                     x1=x1, y1=y1, x2=x2, y2=y2, width=width))

    # -- priority (§48) --
    def net_priority(self, net: str) -> Tuple[float, str]:
        n = self.ctx.nets.get(net)
        score = 0.0
        if net in self.ctx.sensitive_nets:
            score += 40
        if net in self.ctx.critical_nets:
            score += 25
        if n is not None:
            score += 4 * n.degree
        aps = self.ctx.net_to_access.get(net, [])
        if aps:                       # tight pin access = route it early
            xs = [a.x for a in aps]
            ys = [a.y for a in aps]
            span = (max(xs) - min(xs)) + (max(ys) - min(ys))
            score += min(30.0, span / max(self.pitch, 1e-6) * 0.05)
        if self.ctx.is_power_or_ground(net):
            score -= 15               # rails are wide and forgiving: route last
        return (-score, net)          # sort ascending => highest score first

    # -- top level with negotiated rip-up (§47) --
    def run(self) -> Dict[str, object]:
        nets = [n for n in self.ctx.routable_nets()
                if len(self.terminal_groups(n)) >= 2]
        order = sorted(nets, key=self.net_priority)
        self.cfg.log(1, f"  [ROUTER] {len(order)} nets to route; order: {order}")

        best_plans: Dict[str, RoutePlan] = {}
        best_failures: List[RoutingFailure] = []

        for it in range(self.cfg.ripup_iterations):
            self.occ.release_all()
            self._reserve_access_cells()
            self._block_escape_corridors()
            plans: Dict[str, RoutePlan] = {}
            failures: List[RoutingFailure] = []

            for net in order:
                plan, fail = self.route_net(net)
                if plan is not None:
                    plans[net] = plan
                elif fail is not None:
                    failures.append(fail)

            self.cfg.log(1, f"  [ROUTER] iter {it + 1}/{self.cfg.ripup_iterations}: "
                            f"{len(plans)}/{len(order)} routed, {len(failures)} failed")

            if len(plans) > len(best_plans) or (len(plans) == len(best_plans) and not best_plans):
                best_plans, best_failures = plans, failures

            if not failures:
                best_plans, best_failures = plans, failures
                break

            # negotiate: make the regions that blocked us expensive, then
            # reorder so the losers get first pick next sweep.
            for f in failures:
                if f.region is None:
                    continue
                c0 = self.to_cell(f.region.xmin, f.region.ymin)
                c1 = self.to_cell(f.region.xmax, f.region.ymax)
                for lname in self.layers:
                    for ix in range(c0[0], c1[0] + 1):
                        for iy in range(c0[1], c1[1] + 1):
                            self.occ.penalise(lname, (ix, iy), 1.0)
            self.occ.bump_history(1.0)
            failed_names = [f.net for f in failures]
            order = failed_names + [n for n in order if n not in failed_names]

        # publish onto the context.  clear_routing() wipes failures, so the
        # access-selection failures are re-attached afterwards — otherwise a
        # terminal that could never be reached vanished from the report.
        self.ctx.clear_routing()
        for f in self._access_failures:
            self.ctx.add_failure(f)
        for net, plan in best_plans.items():
            self.ctx.add_route(plan)
            self.ctx.routed_nets[net].complete = True
        for f in best_failures:
            self.ctx.add_failure(f)

        # A net is only "routed" if its committed geometry is actually one
        # connected conductor.  Trusting the search alone let a stranded
        # terminal be reported as success (§82); this closes that gap by
        # construction rather than by hoping the bug does not recur.
        self._confirm_connectivity()

        cong = CongestionMap(self.ctx.design_bbox().inflate(self.cfg.margin),
                             cell=max(self.pitch * 4, 2.0),
                             capacity=max(4.0, 4 * len(self.layers)))
        for s in self.ctx.segments:
            cong.add_demand(s.x1, s.y1, s.x2, s.y2, 1.0)
        self.ctx.routing_congestion = cong

        routed_now = sorted(n for n, rn in self.ctx.routed_nets.items() if rn.complete)
        return {
            "routed": routed_now,
            "failed": sorted({f.net for f in self.ctx.failures}),
            "iterations_used": it + 1,
        }

    def _confirm_connectivity(self):
        """Downgrade any net whose geometry is not one connected piece."""
        from mbg import connectivity as _conn
        uf, shapes = _conn.build_physical_graph(self.ctx)
        clusters: Dict[str, set] = {}
        for sh in shapes:
            if sh.kind == "access" and sh.net:
                clusters.setdefault(sh.net, set()).add(uf.find(sh.uid))
        for net, roots in clusters.items():
            rn = self.ctx.routed_nets.get(net)
            if rn is None or not rn.complete or len(roots) <= 1:
                continue
            rn.complete = False
            self.ctx.add_failure(RoutingFailure(
                net=net, cause="INCOMPLETE_TREE",
                suggested_action="inspect the access geometry for this net",
                detail=f"committed geometry forms {len(roots)} disconnected "
                       f"pieces; the net is not fully connected"))
            self.cfg.log(1, f"  [ROUTER] net {net}: geometry is not connected "
                            f"({len(roots)} pieces) — reported as unrouted")


def realize(ctx, component, cfg: Optional[RouterConfig] = None):
    """Stage 2 (§37): turn the committed RoutePlans into real gdsfactory /
    gLayout geometry.  Nothing is drawn that is not in the context, so the
    GDS and the verified model can never drift apart."""
    from glayout import via_stack
    cfg = cfg or RouterConfig()
    rules = ctx.rules
    pdk = ctx.pdk

    for s in ctx.segments:
        hw = s.width / 2.0
        layer = rules.layer_tuple(s.layer)
        if abs(s.y1 - s.y2) < 1e-9:
            x0, x1 = sorted((s.x1, s.x2))
            pts = [[x0 - hw, s.y1 - hw], [x1 + hw, s.y1 - hw],
                   [x1 + hw, s.y1 + hw], [x0 - hw, s.y1 + hw]]
        else:
            y0, y1 = sorted((s.y1, s.y2))
            pts = [[s.x1 - hw, y0 - hw], [s.x1 + hw, y0 - hw],
                   [s.x1 + hw, y1 + hw], [s.x1 - hw, y1 + hw]]
        component.add_polygon(pts, layer=layer)

    for pts, layer in _same_net_notch_fills(ctx, cfg):
        component.add_polygon(pts, layer=layer)

    cache: Dict[Tuple[str, str], object] = {}
    for v in ctx.vias:
        key = (v.lower, v.upper)
        if key not in cache:
            cache[key] = via_stack(pdk, v.lower, v.upper, centered=True)
        ref = component.add_ref(cache[key])
        ref.move((v.x, v.y))
    cfg.log(1, f"  [ROUTER] realized {len(ctx.segments)} segments, "
               f"{len(ctx.vias)} vias into {component.name}")
    return component


def _same_net_notch_fills(ctx, cfg):
    """Close sub-spacing gaps between two conductors of the SAME net.

    A pin escape leg and the track that returns to it can end up running
    parallel a fraction of a micron apart. Electrically that is one net and
    perfectly correct, but Magic reports "Metal3 spacing < 0.28um": proximity
    without overlap is a notch no matter who owns the metal (§45).

    Filling the gap is safe precisely because the two shapes are the same
    net — the fill shorts nothing that is not already connected — and it is
    strictly better than nudging the router, which would just move the notch
    somewhere else. Different nets are never bridged; those are real shorts
    and must be reported, not papered over.
    """
    rules = ctx.rules
    out = []
    by_key = {}
    for seg in ctx.segments:
        by_key.setdefault((seg.layer, seg.net), []).append(seg.bbox())
    for (layer, net), boxes in by_key.items():
        sp = rules.min_spacing(layer)
        lt = rules.layer_tuple(layer)
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                a, b = boxes[i], boxes[j]
                if a.overlaps(b):
                    continue
                # gap along x, with a shared y extent (and vice versa)
                gx = max(a.xmin, b.xmin) - min(a.xmax, b.xmax)
                gy = max(a.ymin, b.ymin) - min(a.ymax, b.ymax)
                oy = min(a.ymax, b.ymax) - max(a.ymin, b.ymin)
                ox = min(a.xmax, b.xmax) - max(a.xmin, b.xmin)
                if 0 < gx < sp and oy > 0:
                    x0, x1 = min(a.xmax, b.xmax), max(a.xmin, b.xmin)
                    y0, y1 = max(a.ymin, b.ymin), min(a.ymax, b.ymax)
                elif 0 < gy < sp and ox > 0:
                    x0, x1 = max(a.xmin, b.xmin), min(a.xmax, b.xmax)
                    y0, y1 = min(a.ymax, b.ymax), max(a.ymin, b.ymin)
                else:
                    continue
                out.append(([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], lt))
    if out:
        cfg.log(2, f"  [ROUTER] {len(out)} same-net notch(es) filled")
    return out
