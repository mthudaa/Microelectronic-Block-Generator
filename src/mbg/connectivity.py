"""
@Owner: Huda (Lead Analog / Mixed-Signal Designer)
@Role: Analog Layout Strategist
@Responsibility: Internal physical-connectivity verification (§60).

Compares the *expected* connectivity graph (from SPICE, held in the
DesignContext) against the *physical* connectivity graph (from the net-owned
geometry the router committed).  Detects OPEN / SHORT / PORT_MISMATCH before
the design is handed to Magic + netgen, so that obvious electrical errors are
caught at the stage that caused them instead of at signoff.

This does not replace external DRC/LVS — it is the fast internal check that
external signoff then confirms.  Every conductor considered here carries an
explicit net owner; anonymous geometry is reported rather than ignored.
"""
from typing import Dict, List, Optional, Set, Tuple

from mbg.design_context import (
    BoundingBox, DRCViolation, LVSViolation, Obstacle, Segment, Via,
)


class _UnionFind:
    def __init__(self):
        self.parent: Dict[int, int] = {}

    def add(self, x: int):
        self.parent.setdefault(x, x)

    def find(self, x: int) -> int:
        self.add(x)
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[x] != root:      # path compression
            self.parent[x], x = root, self.parent[x]
        return root

    def union(self, a: int, b: int):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


class _Shape:
    """A conductor occupying a contiguous range of metal layers."""
    __slots__ = ("uid", "net", "lo", "hi", "bbox", "kind", "label")

    def __init__(self, uid, net, lo, hi, bbox, kind, label):
        self.uid = uid
        self.net = net
        self.lo = lo            # lowest metal index occupied
        self.hi = hi            # highest metal index occupied
        self.bbox = bbox
        self.kind = kind        # "segment" | "via" | "access" | "device"
        self.label = label

    def layer_overlap(self, other: "_Shape") -> bool:
        return not (self.hi < other.lo or other.hi < self.lo)

    def touches(self, other: "_Shape", tol: float = 1e-6) -> bool:
        a, b = self.bbox, other.bbox
        return not (a.xmax < b.xmin - tol or a.xmin > b.xmax + tol or
                    a.ymax < b.ymin - tol or a.ymin > b.ymax + tol)


def _idx(rules, layer: str) -> int:
    try:
        return rules.layer(layer).index
    except Exception:
        return -1


def build_physical_graph(ctx) -> Tuple[_UnionFind, List[_Shape]]:
    """Union every conductor that physically touches, ignoring net labels.

    Net labels are deliberately *not* used to merge shapes: that is the whole
    point — we want to discover what the geometry actually connects, then
    compare with what the netlist says it should connect.
    """
    rules = ctx.rules
    uf = _UnionFind()
    shapes: List[_Shape] = []
    uid = 0

    for s in ctx.segments:
        i = _idx(rules, s.layer)
        if i < 0:
            continue
        shapes.append(_Shape(uid, s.net, i, i, s.bbox(), "segment",
                             f"{s.layer}:{s.net}"))
        uid += 1

    for v in ctx.vias:
        lo, hi = _idx(rules, v.lower), _idx(rules, v.upper)
        if lo < 0 or hi < 0:
            continue
        shapes.append(_Shape(uid, v.net, min(lo, hi), max(lo, hi), v.bbox(),
                             "via", f"{v.lower}->{v.upper}:{v.net}"))
        uid += 1

    # device access points anchor each net to the real device terminals.
    # The anchor is deliberately small: the *extent* of the terminal's metal
    # comes from the device polygons below, which are real geometry rather
    # than a rectangle synthesised from a port's edge length.
    for net_name, aps in ctx.net_to_access.items():
        for ap in aps:
            i = _idx(rules, ap.layer)
            if i < 0:
                continue
            try:
                h = rules.min_width(ap.layer) / 2.0
            except Exception:
                h = 0.14
            bb = BoundingBox(ap.x - h, ap.y - h, ap.x + h, ap.y + h)
            shapes.append(_Shape(uid, net_name, i, i, bb, "access",
                                 f"{ap.instance}.{ap.terminal}"))
            uid += 1

    # real device metal, with the net attribution placement worked out.
    # Unattributed shapes carry net "" and are inert for short detection but
    # still let same-net device metal bridge two access points.
    for ob in ctx.obstacles:
        if ob.net is None:
            continue
        i = _idx(rules, ob.layer)
        if i < 0:
            continue
        shapes.append(_Shape(uid, ob.net, i, i, ob.bbox, "device",
                             f"{ob.owner}:{ob.layer}"))
        uid += 1

    for sh in shapes:
        uf.add(sh.uid)

    # A device terminal's N/E/S/W ports are one node: the generator already
    # connects them inside the device.  Union them so that using one of them
    # is not mistaken for leaving the others dangling.
    same_terminal: Dict[str, List[int]] = {}
    for sh in shapes:
        if sh.kind == "access":
            same_terminal.setdefault(sh.label, []).append(sh.uid)
    for uids in same_terminal.values():
        for u in uids[1:]:
            uf.union(uids[0], u)

    # O(n^2) is fine at analog-block scale; bucket first to keep it cheap
    bucket: Dict[Tuple[int, int], List[_Shape]] = {}
    CELL = 5.0
    for sh in shapes:
        x0, y0 = int(sh.bbox.xmin // CELL), int(sh.bbox.ymin // CELL)
        x1, y1 = int(sh.bbox.xmax // CELL), int(sh.bbox.ymax // CELL)
        for bx in range(x0, x1 + 1):
            for by in range(y0, y1 + 1):
                bucket.setdefault((bx, by), []).append(sh)

    seen: Set[Tuple[int, int]] = set()
    for group in bucket.values():
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a, b = group[i], group[j]
                key = (min(a.uid, b.uid), max(a.uid, b.uid))
                if key in seen:
                    continue
                seen.add(key)
                if a.layer_overlap(b) and a.touches(b):
                    uf.union(a.uid, b.uid)
    return uf, shapes


def check_opens(ctx, uf, shapes) -> List[LVSViolation]:
    """A net is OPEN when its terminals land in more than one cluster."""
    by_uid = {s.uid: s for s in shapes}
    clusters_by_net: Dict[str, Dict[int, List[str]]] = {}
    for s in shapes:
        if s.kind != "access":
            continue
        root = uf.find(s.uid)
        clusters_by_net.setdefault(s.net, {}).setdefault(root, []).append(s.label)

    out = []
    for net, clusters in clusters_by_net.items():
        expected = ctx.nets.get(net)
        if expected is not None and expected.degree < 2:
            continue                       # single-terminal net cannot be open
        if len(clusters) > 1:
            frags = ["{" + ", ".join(sorted(v)) + "}" for v in clusters.values()]
            out.append(LVSViolation(
                kind="OPEN", nets=[net],
                detail=f"net '{net}' splits into {len(clusters)} disconnected "
                       f"groups: {' | '.join(frags)}"))
    return out


def check_shorts(ctx, uf, shapes) -> List[LVSViolation]:
    """Two nets are SHORTED when their geometry lands in one cluster."""
    nets_in_cluster: Dict[int, Set[str]] = {}
    witness: Dict[int, List[str]] = {}
    for s in shapes:
        root = uf.find(s.uid)
        nets_in_cluster.setdefault(root, set()).add(s.net)
        witness.setdefault(root, []).append(s.label)

    out = []
    for root, nets in nets_in_cluster.items():
        real = {n for n in nets if n}
        if len(real) > 1:
            out.append(LVSViolation(
                kind="SHORT", nets=sorted(real),
                detail=f"nets {sorted(real)} are electrically merged; "
                       f"members: {sorted(set(witness[root]))[:8]}"))
    return out


def check_spacing(ctx, stage: str = "routing") -> List[DRCViolation]:
    """Same-layer spacing between conductors of *different* nets (§43).

    Uses the PDK's real min_separation.  Same-net proximity is allowed here
    (merging is legal); foreign-net proximity below the rule is a violation.
    """
    rules = ctx.rules
    if rules is None:
        return []
    by_layer: Dict[str, List[Tuple[str, BoundingBox, str]]] = {}
    for s in ctx.segments:
        by_layer.setdefault(s.layer, []).append((s.net, s.bbox(), f"seg:{s.net}"))
    for v in ctx.vias:
        try:
            for lname in rules.layers_traversed(v.lower, v.upper):
                by_layer.setdefault(lname, []).append(
                    (v.net, v.bbox(), f"via:{v.lower}->{v.upper}:{v.net}"))
        except Exception:
            continue

    out = []
    for layer, items in by_layer.items():
        try:
            sp = rules.min_spacing(layer)
        except Exception:
            continue
        for i in range(len(items)):
            neti, bi, li = items[i]
            for j in range(i + 1, len(items)):
                netj, bj, lj = items[j]
                if neti == netj:
                    continue
                if bi.inflate(sp).overlaps(bj):
                    out.append(DRCViolation(
                        rule=f"{layer.upper()}_SPACING", stage=stage,
                        objects=[li, lj], nets=[neti, netj], layer=layer,
                        bbox=bi,
                        detail=f"{neti} and {netj} closer than {sp}um on {layer}"))
    return out


def check_via_legality(ctx, stage: str = "routing") -> List[DRCViolation]:
    """Via enclosure + cut spacing against foreign nets (§42)."""
    rules = ctx.rules
    if rules is None:
        return []
    out = []
    for v in ctx.vias:
        stack = rules.via_stack_between(v.lower, v.upper)
        for cut in stack:
            need = cut.min_pad()
            if v.size + 1e-9 < need:
                out.append(DRCViolation(
                    rule=f"{cut.name.upper()}_ENCLOSURE", stage=stage,
                    objects=[f"via@({v.x:.3f},{v.y:.3f})"], nets=[v.net],
                    layer=cut.lower, bbox=v.bbox(),
                    detail=f"via pad {v.size:.3f}um < required {need:.3f}um "
                           f"(cut {cut.cut_width} + 2x enclosure)"))
                break
    for i in range(len(ctx.vias)):
        a = ctx.vias[i]
        sa = set(rules.layers_traversed(a.lower, a.upper))
        for j in range(i + 1, len(ctx.vias)):
            b = ctx.vias[j]
            if a.net == b.net:
                continue
            if not sa & set(rules.layers_traversed(b.lower, b.upper)):
                continue
            cuts = rules.via_stack_between(a.lower, a.upper)
            sep = max((c.cut_spacing for c in cuts), default=0.36)
            if a.bbox().inflate(sep).overlaps(b.bbox()):
                out.append(DRCViolation(
                    rule="VIA_SPACING", stage=stage,
                    objects=[f"via@({a.x:.3f},{a.y:.3f})", f"via@({b.x:.3f},{b.y:.3f})"],
                    nets=[a.net, b.net], layer=a.lower, bbox=a.bbox(),
                    detail=f"vias of {a.net} and {b.net} closer than {sep}um"))
    return out


def check_anonymous_geometry(ctx) -> List[LVSViolation]:
    """Every conductor must have a net owner (§40)."""
    bad = [s for s in ctx.segments if not s.net] + [v for v in ctx.vias if not v.net]
    if not bad:
        return []
    return [LVSViolation(kind="PORT_MISMATCH", nets=[],
                         detail=f"{len(bad)} routing objects have no net owner")]


def verify(ctx, stage: str = "routing", spacing: bool = True,
           vias: bool = True) -> Dict[str, object]:
    """Full internal verification pass.  Records findings on the context.

    Returns a plain dict so callers can log or assert on it.
    """
    uf, shapes = build_physical_graph(ctx)
    opens = check_opens(ctx, uf, shapes)
    shorts = check_shorts(ctx, uf, shapes)
    anon = check_anonymous_geometry(ctx)
    drc: List[DRCViolation] = []
    if spacing:
        drc += check_spacing(ctx, stage)
    if vias:
        drc += check_via_legality(ctx, stage)

    # A terminal the layout never gave an access point to is invisible to the
    # checks above: it produces no shape, so it joins no cluster, so no open
    # is ever reported for it. compare_with_netlist is what sees that class,
    # and its verdict used to be computed, printed, and then ignored — leaving
    # a completely unconnected device terminal able to pass a "clean" internal
    # check and reach external LVS as the first thing that notices.
    consistency = compare_with_netlist(ctx)
    missing = list(consistency["missing_access"])

    for v in opens + shorts + anon:
        ctx.add_violation(v)
    for d in drc:
        ctx.add_violation(d)

    result = {
        "opens": len(opens),
        "shorts": len(shorts),
        "anonymous": len(anon),
        "drc": len(drc),
        "missing_access": len(missing),
        "clean": not (opens or shorts or anon or drc or missing),
        "open_details": [v.detail for v in opens],
        "short_details": [v.detail for v in shorts],
        "drc_details": [f"{d.rule}: {d.detail}" for d in drc[:20]],
        "missing_access_details": missing[:20],
        "netlist_consistency": consistency,
    }
    return result


def _is_substrate_terminal(ctx, dev, term: str, net: str) -> bool:
    """True for a native passive's bulk pin, which the substrate itself makes.

    ``ppolyf_u`` extracts with three terminals — the two resistor ends plus the
    p-substrate it sits in — so a schematic that declares only two makes netgen
    invent a proxy net and the LVS fails on net count.  Declaring the third
    terminal on ground fixes the LVS, but ``mbg.passives.poly_resistor`` builds
    no substrate contact and has no port for one: the connection is formed by
    the p-substrate under the device, held at ground by the substrate taps of
    its neighbours, which is exactly how Magic extracts it.

    Demanding a routed access point for that pin would therefore report a
    missing connection that no router could ever satisfy.  This is narrow on
    purpose: only the bulk of a ``res``/``cap`` primitive, and only when it
    sits on the ground net.  A passive whose bulk is on any other net needs an
    isolating well and a real contact, and is still reported.
    """
    if term != "body" or getattr(dev, "kind", None) not in ("res", "cap"):
        return False
    n = ctx.nets.get(net)
    if n is not None and getattr(n, "is_ground", False):
        return True
    return str(net).strip().lower() in ("vss", "gnd", "0", "vssa")


def compare_with_netlist(ctx) -> Dict[str, object]:
    """Expected (SPICE) vs physical connectivity, terminal by terminal.

    Reports terminals the layout never gave an access point to — the
    'missing connection' class of failure that used to surface only in LVS.
    """
    missing: List[str] = []
    for dev in ctx.devices.values():
        for term, net in dev.terminals.items():
            if not net:
                continue
            if _is_substrate_terminal(ctx, dev, term, net):
                continue
            aps = [a for a in ctx.net_to_access.get(net, [])
                   if a.instance == dev.name and a.terminal == term]
            if not aps:
                missing.append(f"{dev.name}.{term} (net {net})")
    unrouted = [n for n in ctx.routable_nets()
                if not (ctx.routed_nets.get(n) and ctx.routed_nets[n].complete)]
    return {
        "expected_nets": len(ctx.routable_nets()),
        "missing_access": missing,
        "unrouted_nets": unrouted,
        "consistent": not missing and not unrouted,
    }
