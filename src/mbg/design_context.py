"""
@Owner: Huda (Lead Analog / Mixed-Signal Designer)
@Role: Analog Layout Strategist
@Responsibility: Shared design metadata carried across parse -> place -> route -> verify.

The DesignContext is the single object that every pipeline stage reads from
and enriches.  It exists to stop the historical failure mode of this project,
where each stage rediscovered (and mis-guessed) information the previous
stage already knew:

    parser knows the netlist  -> placement re-derived terminals from strings
    placement knows the ports -> router re-guessed access points
    router knows the geometry -> DRC/LVS found the damage afterwards

Stages *add* to the context and must not destroy what an earlier stage put
there.  The logical netlist in particular stays alive for the whole run so
that connectivity can be verified against it (see mbg.connectivity).
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple


# ── geometry primitives ────────────────────────────────────────────────

@dataclass
class BoundingBox:
    xmin: float
    ymin: float
    xmax: float
    ymax: float

    @staticmethod
    def from_gf(bbox) -> "BoundingBox":
        return BoundingBox(float(bbox[0][0]), float(bbox[0][1]),
                           float(bbox[1][0]), float(bbox[1][1]))

    def inflate(self, d: float) -> "BoundingBox":
        return BoundingBox(self.xmin - d, self.ymin - d, self.xmax + d, self.ymax + d)

    def overlaps(self, other: "BoundingBox") -> bool:
        return not (self.xmax <= other.xmin or self.xmin >= other.xmax or
                    self.ymax <= other.ymin or self.ymin >= other.ymax)

    def contains_point(self, x: float, y: float) -> bool:
        return self.xmin <= x <= self.xmax and self.ymin <= y <= self.ymax

    @property
    def width(self) -> float:
        return self.xmax - self.xmin

    @property
    def height(self) -> float:
        return self.ymax - self.ymin

    @property
    def center(self) -> Tuple[float, float]:
        return ((self.xmin + self.xmax) / 2.0, (self.ymin + self.ymax) / 2.0)

    @property
    def area(self) -> float:
        return max(0.0, self.width) * max(0.0, self.height)


# ── logical design ─────────────────────────────────────────────────────

@dataclass
class Device:
    """One SPICE instance, kept alive for the whole flow."""
    name: str
    model: str
    kind: str                       # "nmos" | "pmos" | "res" | "cap" | "other"
    terminals: Dict[str, str] = field(default_factory=dict)   # terminal -> net
    width: Optional[float] = None       # total device width from SPICE (um)
    length: Optional[float] = None
    fingers: int = 1
    multipliers: int = 1
    finger_width: Optional[float] = None  # width actually handed to glayout
    params: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_mos(self) -> bool:
        return self.kind in ("nmos", "pmos")


@dataclass
class Net:
    """One SPICE net, as a hyperedge over device terminals."""
    name: str
    terminals: List[Tuple[str, str]] = field(default_factory=list)  # (device, terminal)
    is_power: bool = False
    is_ground: bool = False
    is_critical: bool = False
    is_sensitive: bool = False
    weight: float = 1.0

    @property
    def degree(self) -> int:
        return len(self.terminals)


@dataclass
class MatchingGroup:
    """Devices that must be laid out identically (diff pair, mirror, ...)."""
    name: str
    kind: str                       # "diff_pair" | "current_mirror" | "cascode" | "generic"
    devices: List[str] = field(default_factory=list)
    symmetric: bool = True


@dataclass
class SymmetryConstraint:
    """A pair (or singleton) that must straddle / sit on a symmetry axis."""
    group: str
    device_a: str
    device_b: Optional[str] = None      # None => self-symmetric, sits on the axis
    axis: str = "vertical"


# ── placement results ──────────────────────────────────────────────────

@dataclass
class Placement:
    instance: str
    x: float
    y: float
    orientation: str = "R0"             # R0 | R180 | MX | MY
    row: int = 0


@dataclass
class PinAccessPoint:
    """A physical routing access point for one logical terminal.

    Coordinates are always read back from the *transformed* reference, never
    cached from before a move (§17).
    """
    instance: str
    terminal: str
    net: str
    layer: str
    x: float
    y: float
    orientation: float
    port: Any = None                    # the live gdsfactory Port
    direction: str = ""                 # N/S/E/W tag from the generator
    width: float = 0.0                  # real port extent along its own edge

    def footprint(self, min_width: float) -> "BoundingBox":
        """The metal this port actually occupies.

        A gLayout terminal port is an EDGE, not a point: it spans ``width``
        along the device face.  Treating it as a point is what let a via pad
        on one terminal silently overlap the neighbouring terminal's metal.
        """
        half_edge = max(self.width, min_width) / 2.0
        half_thick = min_width / 2.0
        if int(round(self.orientation)) % 180 == 0:     # faces E/W -> spans y
            return BoundingBox(self.x - half_thick, self.y - half_edge,
                               self.x + half_thick, self.y + half_edge)
        return BoundingBox(self.x - half_edge, self.y - half_thick,
                           self.x + half_edge, self.y + half_thick)


@dataclass
class Zone:
    """A protected area — device-local interconnect, well, guard ring."""
    kind: str                           # "device_local" | "dnw" | "guardring" | "power"
    bbox: BoundingBox
    layers: List[str] = field(default_factory=list)
    owner: str = ""
    net: Optional[str] = None


@dataclass
class Obstacle:
    """Routing obstacle derived from real geometry (§58)."""
    layer: str
    bbox: BoundingBox
    owner: str = ""
    kind: str = "device_geometry"
    net: Optional[str] = None           # None => unknown owner, treat as foreign


# ── routing results ────────────────────────────────────────────────────

@dataclass
class Segment:
    """A committed conductor.  Always carries its net owner (§40)."""
    net: str
    layer: str
    x1: float
    y1: float
    x2: float
    y2: float
    width: float

    def bbox(self) -> BoundingBox:
        """Footprint of the conductor as it is actually drawn.

        The realized polygon extends by half a width past each end so that
        consecutive runs merge at corners; the model must include that same
        extension or the verifier would check different geometry than the
        GDS contains.
        """
        hw = self.width / 2.0
        if abs(self.y1 - self.y2) < 1e-9:       # horizontal
            return BoundingBox(min(self.x1, self.x2) - hw, self.y1 - hw,
                               max(self.x1, self.x2) + hw, self.y1 + hw)
        if abs(self.x1 - self.x2) < 1e-9:       # vertical
            return BoundingBox(self.x1 - hw, min(self.y1, self.y2) - hw,
                               self.x1 + hw, max(self.y1, self.y2) + hw)
        return BoundingBox(min(self.x1, self.x2) - hw, min(self.y1, self.y2) - hw,
                           max(self.x1, self.x2) + hw, max(self.y1, self.y2) + hw)

    def length(self) -> float:
        return abs(self.x2 - self.x1) + abs(self.y2 - self.y1)


@dataclass
class Via:
    """A committed via stack.  Always carries its net owner (§40)."""
    net: str
    x: float
    y: float
    lower: str
    upper: str
    size: float

    def bbox(self) -> BoundingBox:
        h = self.size / 2.0
        return BoundingBox(self.x - h, self.y - h, self.x + h, self.y + h)


@dataclass
class RoutePlan:
    """Stage-1 routing result: topology only, no geometry yet (§37)."""
    net: str
    segments: List[Segment] = field(default_factory=list)
    vias: List[Via] = field(default_factory=list)
    detour_factor: float = 1.0
    manhattan_min: float = 0.0

    def wire_length(self) -> float:
        return sum(s.length() for s in self.segments)

    def via_count(self) -> int:
        return len(self.vias)


@dataclass
class RoutedNet:
    net: str
    plans: List[RoutePlan] = field(default_factory=list)
    complete: bool = False

    def wire_length(self) -> float:
        return sum(p.wire_length() for p in self.plans)

    def via_count(self) -> int:
        return sum(p.via_count() for p in self.plans)


@dataclass
class RoutingFailure:
    """Structured failure so placement can react instead of guessing (§52)."""
    net: str
    cause: str                          # NO_PIN_ESCAPE | BLOCKED | CONGESTED | NO_LEGAL_VIA | SEARCH_EXHAUSTED
    region: Optional[BoundingBox] = None
    blocking_instances: List[str] = field(default_factory=list)
    suggested_action: str = ""
    detail: str = ""


@dataclass
class Conflict:
    net_a: str
    net_b: str
    layer: str
    bbox: Optional[BoundingBox] = None
    kind: str = "overlap"


# ── verification results ───────────────────────────────────────────────

@dataclass
class DRCViolation:
    """A rule violation that knows where it came from (§61)."""
    rule: str
    stage: str                          # "placement" | "routing" | "signoff"
    objects: List[str] = field(default_factory=list)
    nets: List[str] = field(default_factory=list)
    layer: str = ""
    bbox: Optional[BoundingBox] = None
    detail: str = ""


@dataclass
class LVSViolation:
    kind: str                           # "SHORT" | "OPEN" | "PORT_MISMATCH"
    nets: List[str] = field(default_factory=list)
    detail: str = ""


@dataclass
class PlacementFeedback:
    """What trial routing tells placement (§30)."""
    unrouted_nets: List[str] = field(default_factory=list)
    congestion_regions: List[BoundingBox] = field(default_factory=list)
    inaccessible_pins: List[Tuple[str, str]] = field(default_factory=list)
    excessive_detours: List[str] = field(default_factory=list)
    failures: List[RoutingFailure] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return not (self.unrouted_nets or self.inaccessible_pins or self.failures)


# ── congestion ─────────────────────────────────────────────────────────

class CongestionMap:
    """Coarse demand/capacity grid used by both placement and routing (§28)."""

    def __init__(self, bbox: BoundingBox, cell: float = 3.0, capacity: float = 8.0):
        self.bbox = bbox
        self.cell = max(cell, 0.1)
        self.capacity = capacity
        self.demand: Dict[Tuple[int, int], float] = {}

    def _key(self, x: float, y: float) -> Tuple[int, int]:
        return (int((x - self.bbox.xmin) // self.cell),
                int((y - self.bbox.ymin) // self.cell))

    def add_demand(self, x1: float, y1: float, x2: float, y2: float, amount: float = 1.0):
        kx1, ky1 = self._key(min(x1, x2), min(y1, y2))
        kx2, ky2 = self._key(max(x1, x2), max(y1, y2))
        for kx in range(kx1, kx2 + 1):
            for ky in range(ky1, ky2 + 1):
                self.demand[(kx, ky)] = self.demand.get((kx, ky), 0.0) + amount

    def at(self, x: float, y: float) -> float:
        return self.demand.get(self._key(x, y), 0.0)

    def ratio(self, x: float, y: float) -> float:
        return self.at(x, y) / self.capacity if self.capacity else 0.0

    def hotspots(self, threshold: float = 1.0) -> List[BoundingBox]:
        out = []
        for (kx, ky), d in self.demand.items():
            if self.capacity and d / self.capacity >= threshold:
                x0 = self.bbox.xmin + kx * self.cell
                y0 = self.bbox.ymin + ky * self.cell
                out.append(BoundingBox(x0, y0, x0 + self.cell, y0 + self.cell))
        return out

    def max_ratio(self) -> float:
        if not self.demand or not self.capacity:
            return 0.0
        return max(self.demand.values()) / self.capacity

    def avg_ratio(self) -> float:
        if not self.demand or not self.capacity:
            return 0.0
        return (sum(self.demand.values()) / len(self.demand)) / self.capacity


# ── the context itself ─────────────────────────────────────────────────

@dataclass
class DesignContext:
    """Shared state for one layout run.

    Populated incrementally:
        parser    -> devices, nets, ports, matching groups, power/ground
        placement -> component, references, terminal_to_ports, placements,
                     bboxes, reserved zones, access points, clusters
        routing   -> routed_nets, segments, vias, occupancy, failures
        verify    -> drc_violations, lvs_violations, connectivity graph
    """
    name: str = "top"

    # logical design ---------------------------------------------------
    devices: Dict[str, Device] = field(default_factory=dict)
    nets: Dict[str, Net] = field(default_factory=dict)
    top_ports: List[str] = field(default_factory=list)

    # analog constraints -----------------------------------------------
    matching_groups: Dict[str, MatchingGroup] = field(default_factory=dict)
    symmetry_constraints: List[SymmetryConstraint] = field(default_factory=list)
    clusters: Dict[str, List[str]] = field(default_factory=dict)
    critical_nets: Set[str] = field(default_factory=set)
    sensitive_nets: Set[str] = field(default_factory=set)
    power_nets: Set[str] = field(default_factory=set)
    ground_nets: Set[str] = field(default_factory=set)
    differential_pairs: List[Tuple[str, str]] = field(default_factory=list)

    # physical (gLayout / gdsfactory) ----------------------------------
    component: Any = None
    references: Dict[str, Any] = field(default_factory=dict)
    terminal_to_ports: Dict[Tuple[str, str], List[Any]] = field(default_factory=dict)
    net_to_access: Dict[str, List[PinAccessPoint]] = field(default_factory=dict)

    # placement --------------------------------------------------------
    placements: Dict[str, Placement] = field(default_factory=dict)
    device_bboxes: Dict[str, BoundingBox] = field(default_factory=dict)
    reserved_zones: List[Zone] = field(default_factory=list)
    obstacles: List[Obstacle] = field(default_factory=list)
    deep_nwell_flags: Dict[str, bool] = field(default_factory=dict)
    placement_congestion: Optional[CongestionMap] = None

    # routing ----------------------------------------------------------
    routed_nets: Dict[str, RoutedNet] = field(default_factory=dict)
    segments: List[Segment] = field(default_factory=list)
    vias: List[Via] = field(default_factory=list)
    unresolved_nets: List[str] = field(default_factory=list)
    failures: List[RoutingFailure] = field(default_factory=list)
    conflicts: List[Conflict] = field(default_factory=list)
    routing_congestion: Optional[CongestionMap] = None

    # verification -----------------------------------------------------
    drc_violations: List[DRCViolation] = field(default_factory=list)
    lvs_violations: List[LVSViolation] = field(default_factory=list)

    # technology -------------------------------------------------------
    pdk: Any = None
    rules: Any = None                   # PDKRules
    metrics: Dict[str, Any] = field(default_factory=dict)

    # ── controlled updates (§10) ────────────────────────────────────
    def add_device(self, dev: Device):
        self.devices[dev.name] = dev

    def add_net(self, net: Net):
        self.nets[net.name] = net

    def add_placement(self, p: Placement, bbox: Optional[BoundingBox] = None):
        self.placements[p.instance] = p
        if bbox is not None:
            self.device_bboxes[p.instance] = bbox

    def add_access_point(self, ap: PinAccessPoint):
        self.net_to_access.setdefault(ap.net, []).append(ap)
        self.terminal_to_ports.setdefault((ap.instance, ap.terminal), [])
        if ap.port is not None and ap.port not in self.terminal_to_ports[(ap.instance, ap.terminal)]:
            self.terminal_to_ports[(ap.instance, ap.terminal)].append(ap.port)

    def add_zone(self, z: Zone):
        self.reserved_zones.append(z)

    def add_obstacle(self, o: Obstacle):
        self.obstacles.append(o)

    def add_route(self, plan: RoutePlan):
        rn = self.routed_nets.setdefault(plan.net, RoutedNet(net=plan.net))
        rn.plans.append(plan)
        self.segments.extend(plan.segments)
        self.vias.extend(plan.vias)

    def add_failure(self, f: RoutingFailure):
        self.failures.append(f)
        if f.net not in self.unresolved_nets:
            self.unresolved_nets.append(f.net)

    def add_violation(self, v):
        if isinstance(v, DRCViolation):
            self.drc_violations.append(v)
        elif isinstance(v, LVSViolation):
            self.lvs_violations.append(v)
        else:
            raise TypeError(f"unsupported violation type {type(v).__name__}")

    def clear_routing(self):
        """Drop every routing result — used between rip-up sweeps so that
        geometry is never drawn twice for the same net."""
        self.routed_nets.clear()
        self.segments.clear()
        self.vias.clear()
        self.unresolved_nets.clear()
        self.failures.clear()
        self.conflicts.clear()

    # ── queries ─────────────────────────────────────────────────────
    def access_points(self, instance: str, terminal: str) -> List[PinAccessPoint]:
        out = []
        for aps in self.net_to_access.values():
            for ap in aps:
                if ap.instance == instance and ap.terminal == terminal:
                    out.append(ap)
        return out

    def net_weight(self, net: str) -> float:
        n = self.nets.get(net)
        if n is None:
            return 1.0
        w = n.weight
        if net in self.critical_nets:
            w *= 2.0
        if net in self.sensitive_nets:
            w *= 1.5
        return w

    def hpwl(self, net: str) -> float:
        """Half-perimeter wire length over that net's access points (§19)."""
        aps = self.net_to_access.get(net, [])
        if len(aps) < 2:
            return 0.0
        xs = [a.x for a in aps]
        ys = [a.y for a in aps]
        return (max(xs) - min(xs)) + (max(ys) - min(ys))

    def total_weighted_hpwl(self) -> float:
        return sum(self.net_weight(n) * self.hpwl(n) for n in self.net_to_access)

    def routable_nets(self) -> List[str]:
        return [n for n, net in self.nets.items() if net.degree >= 2]

    def is_power_or_ground(self, net: str) -> bool:
        return net in self.power_nets or net in self.ground_nets

    def design_bbox(self) -> BoundingBox:
        if self.device_bboxes:
            return BoundingBox(
                min(b.xmin for b in self.device_bboxes.values()),
                min(b.ymin for b in self.device_bboxes.values()),
                max(b.xmax for b in self.device_bboxes.values()),
                max(b.ymax for b in self.device_bboxes.values()),
            )
        if self.component is not None:
            return BoundingBox.from_gf(self.component.bbox)
        return BoundingBox(0, 0, 0, 0)

    # ── reporting ───────────────────────────────────────────────────
    def routing_summary(self) -> Dict[str, Any]:
        """Only metrics that were actually measured (§68)."""
        nets = self.routable_nets()
        routed = [n for n in nets if self.routed_nets.get(n) and self.routed_nets[n].complete]
        wl_by_layer: Dict[str, float] = {}
        for s in self.segments:
            wl_by_layer[s.layer] = wl_by_layer.get(s.layer, 0.0) + s.length()
        via_by_type: Dict[str, int] = {}
        for v in self.vias:
            key = f"{v.lower}->{v.upper}"
            via_by_type[key] = via_by_type.get(key, 0) + 1
        detours = [p.detour_factor for rn in self.routed_nets.values()
                   for p in rn.plans if p.manhattan_min > 0]
        out = {
            "total_nets": len(nets),
            "routed_nets": len(routed),
            "unrouted_nets": len(nets) - len(routed),
            "unresolved": sorted(set(self.unresolved_nets)),
            "wire_length": round(sum(s.length() for s in self.segments), 3),
            "wire_length_by_layer": {k: round(v, 3) for k, v in sorted(wl_by_layer.items())},
            "via_count": len(self.vias),
            "via_count_by_type": dict(sorted(via_by_type.items())),
            "drc_violations": len(self.drc_violations),
            "lvs_violations": len(self.lvs_violations),
            "conflicts": len(self.conflicts),
        }
        if detours:
            out["avg_detour_factor"] = round(sum(detours) / len(detours), 3)
            out["max_detour_factor"] = round(max(detours), 3)
        if self.routing_congestion is not None:
            out["max_congestion"] = round(self.routing_congestion.max_ratio(), 3)
            out["avg_congestion"] = round(self.routing_congestion.avg_ratio(), 3)
        out.update(self.metrics)
        return out
