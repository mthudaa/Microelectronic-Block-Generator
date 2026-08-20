"""
@Owner: Huda (Lead Analog / Mixed-Signal Designer)
@Role: Analog Layout Strategist
@Responsibility: Generation of power strips (VDD/VSS) and guard rings to minimize noise in analog circuits.
"""
from glayout import via_stack, tapring
from gdsfactory.components import rectangle


def add_power_strips(component, pdk, strip_width=1.0, margin=2.0):
    bbox = component.bbox
    min_x, min_y = bbox[0][0], bbox[0][1]
    max_x, max_y = bbox[1][0], bbox[1][1]
    w = max_x - min_x
    strip_w = w + 2 * margin
    hw = strip_width / 2.0
    met5 = pdk.get_glayer("met5")

    vdd_y = max_y + margin
    component.add_polygon([
        [min_x - margin, vdd_y - hw], [min_x - margin + strip_w, vdd_y - hw],
        [min_x - margin + strip_w, vdd_y + hw], [min_x - margin, vdd_y + hw],
    ], layer=met5)
    vdd_via = component.add_ref(via_stack(pdk, "met2", "met5", centered=True))
    vdd_via.move((min_x - margin + 2.0, vdd_y))
    vdd_ports = [p for p in vdd_via.get_ports_list() if "top_met" in p.name or "bottom_met" in p.name]
    # Add VDD label directly on component (Magic sees top-level labels)
    vdd_label_xy = (min_x - margin + 2.0, vdd_y)
    component.add_label(text="vdd", layer=pdk.get_glayer("met5_label"), position=vdd_label_xy)
    component.add_polygon([
        [vdd_label_xy[0]-0.5, vdd_label_xy[1]-0.5],
        [vdd_label_xy[0]+0.5, vdd_label_xy[1]-0.5],
        [vdd_label_xy[0]+0.5, vdd_label_xy[1]+0.5],
        [vdd_label_xy[0]-0.5, vdd_label_xy[1]+0.5],
    ], layer=pdk.get_glayer("met5_pin"))

    vss_y = min_y - margin
    component.add_polygon([
        [min_x - margin, vss_y - hw], [min_x - margin + strip_w, vss_y - hw],
        [min_x - margin + strip_w, vss_y + hw], [min_x - margin, vss_y + hw],
    ], layer=met5)
    vss_via = component.add_ref(via_stack(pdk, "met2", "met5", centered=True))
    vss_via.move((min_x - margin + strip_w - 2.0, vss_y))
    vss_ports = [p for p in vss_via.get_ports_list() if "top_met" in p.name or "bottom_met" in p.name]
    # Add VSS label directly on component (Magic sees top-level labels)
    vss_label_xy = (min_x - margin + strip_w - 2.0, vss_y)
    component.add_label(text="vss", layer=pdk.get_glayer("met5_label"), position=vss_label_xy)
    component.add_polygon([
        [vss_label_xy[0]-0.5, vss_label_xy[1]-0.5],
        [vss_label_xy[0]+0.5, vss_label_xy[1]-0.5],
        [vss_label_xy[0]+0.5, vss_label_xy[1]+0.5],
        [vss_label_xy[0]-0.5, vss_label_xy[1]+0.5],
    ], layer=pdk.get_glayer("met5_pin"))

    print(f"[POWER] VDD y={vdd_y:.1f} via@left, VSS y={vss_y:.1f} via@right, strip_w={strip_w:.1f}um")
    return component, vdd_ports, vss_ports


def add_double_guardring(component, pdk, vdd_ports=None, vss_ports=None, area_scale=2.75, ring_gap=1.0):
    bbox = component.bbox
    min_x, min_y = bbox[0][0], bbox[0][1]
    max_x, max_y = bbox[1][0], bbox[1][1]
    w = max_x - min_x
    h = max_y - min_y
    cx = min_x + w / 2.0
    cy = min_y + h / 2.0
    scale = area_scale ** 0.5
    print(f"[GUARDRING] Bbox: ({min_x:.1f},{min_y:.1f})-({max_x:.1f},{max_y:.1f}), center=({cx:.1f},{cy:.1f}), size={w:.1f}x{h:.1f}")

    outer_w, outer_h = w * scale, h * scale
    outer_size = (outer_w, outer_h)
    outer_ring = tapring(pdk, enclosed_rectangle=outer_size, sdlayer="p+s/d")
    outer_ref = component.add_ref(outer_ring)
    outer_ref.move((cx, cy))
    print(f"[GUARDRING] Outer P+ tap: {outer_w:.1f}x{outer_h:.1f}um")

    inner_w = outer_w - 2.0 * ring_gap
    inner_h = outer_h - 2.0 * ring_gap
    inner_size = (max(inner_w, 1.0), max(inner_h, 1.0))
    try:
        inner_ring = tapring(pdk, enclosed_rectangle=inner_size, sdlayer="n+s/d")
    except Exception:
        inner_ring = tapring(pdk, enclosed_rectangle=inner_size, sdlayer="p+s/d")
    inner_ref = component.add_ref(inner_ring)
    inner_ref.move((cx, cy))
    print(f"[GUARDRING] Inner N+ tap: {inner_size[0]:.1f}x{inner_size[1]:.1f}um (gap={ring_gap}um)")
    if vdd_ports or vss_ports:
        print(f"[GUARDRING] vdd_ports={len(vdd_ports or [])} vss_ports={len(vss_ports or [])} — connect manually via manual_route()")
    return component, inner_ring, outer_ring


def manual_power(component, pdk, strips=None, rails=None, guardring=None):
    """AI-agent-friendly manual power distribution.

    Creates power strips, local rails, and guard rings at explicit
    coordinates. Returns port references for the router.

    Args:
        component: gdsfactory Component to draw into.
        pdk: MappedPDK object (gf180 / sky130).
        strips: List of power strip dicts, each with:
            net: "VDD" or "VSS"
            layer: str — default "met5"
            y: float — Y center of strip
            x_start: float — Start X
            x_end: float — End X
            width: float — Strip width (default 1.0)
            via_x: float — X position of via stack (optional)
            via_bottom: str — Bottom via layer (default "met2")
        rails: List of local power rail dicts, each with:
            net: "VDD" or "VSS"
            layer: str — "met1"|"met2"|"met3"
            x: float, y: float — Position
            length: float — Rail length in routing direction
            width: float — Rail width (default 0.5)
            direction: "H" or "V" — default "H" (auto from layer)
        guardring: dict or None:
            enabled: bool
            area_scale: float — default 2.75
            ring_gap: float — default 1.0

    Returns:
        (component, ports_dict)
        ports_dict: {"VDD": [Port, ...], "VSS": [Port, ...]}
            Each port can be used with manual_route() / auto_router().
    """
    if strips:
        required = {"net", "y"}
        for i, s in enumerate(strips):
            missing = required - set(s.keys())
            if missing:
                raise KeyError(f"strips[{i}] missing keys: {missing}")
            if s["net"].upper() not in ("VDD", "VSS"):
                raise ValueError(f"strips[{i}].net='{s['net']}' — must be VDD or VSS")

    ports = {"VDD": [], "VSS": []}

    # ── Power strips ──────────────────────────────────────────────────
    for s in (strips or []):
        net = s["net"].upper()
        y = float(s["y"])
        xs = float(s.get("x_start", -50))
        xe = float(s.get("x_end", 50))
        w = float(s.get("width", 1.0))
        hw = w / 2.0
        layer_name = s.get("layer", "met5")
        layer = pdk.get_glayer(layer_name)

        component.add_polygon([[xs, y - hw], [xe, y - hw],
                               [xe, y + hw], [xs, y + hw]], layer=layer)

        via_x = s.get("via_x", xs + 2.0)
        via_bottom = s.get("via_bottom", "met2")
        via = component.add_ref(via_stack(pdk, via_bottom, layer_name, centered=True))
        via.move((via_x, y))
        for p in via.get_ports_list():
            if "top_met" in p.name or "bottom_met" in p.name:
                ports[net].append(p)

        # Label
        pin_layer = pdk.get_glayer(f"{layer_name}_pin")
        label_layer = pdk.get_glayer(f"{layer_name}_label")
        lbl = rectangle(layer=pin_layer, size=(1.0, 1.0), centered=True).copy()
        lbl.add_label(text=net.lower(), layer=label_layer)
        lr = component.add_ref(lbl)
        lr.move((via_x, y))

        print(f"[POWER] {net} strip y={y:.1f} {xs:.1f}..{xe:.1f} via@({via_x:.1f},{y:.1f})")

    # ── Local rails ───────────────────────────────────────────────────
    for r in (rails or []):
        net = r["net"].upper()
        x, y = float(r["x"]), float(r["y"])
        length = float(r["length"])
        w = float(r.get("width", 0.5))
        hw = w / 2.0
        layer_name = r.get("layer", "met3")
        layer = pdk.get_glayer(layer_name)
        direc = r.get("direction", "H")

        if direc == "H":
            pts = [[x, y - hw], [x + length, y - hw],
                   [x + length, y + hw], [x, y + hw]]
        else:
            pts = [[x - hw, y], [x + hw, y],
                   [x + hw, y + length], [x - hw, y + length]]
        component.add_polygon(pts, layer=layer)
        print(f"[POWER] {net} rail @ ({x:.1f},{y:.1f}) len={length} {layer_name} {direc}")

    # ── Guard ring ────────────────────────────────────────────────────
    if guardring and guardring.get("enabled", False):
        bbox = component.bbox
        min_x, min_y = bbox[0][0], bbox[0][1]
        max_x, max_y = bbox[1][0], bbox[1][1]
        w_b = max_x - min_x
        h_b = max_y - min_y
        cx = min_x + w_b / 2.0
        cy = min_y + h_b / 2.0
        scale = float(guardring.get("area_scale", 2.75)) ** 0.5
        gap = float(guardring.get("ring_gap", 1.0))

        outer_w, outer_h = w_b * scale, h_b * scale
        outer = tapring(pdk, enclosed_rectangle=(outer_w, outer_h), sdlayer="p+s/d")
        component.add_ref(outer).move((cx, cy))
        print(f"[GUARD] Outer P+ tap: {outer_w:.1f}x{outer_h:.1f}um")

        inner_w = max(outer_w - 2 * gap, 1.0)
        inner_h = max(outer_h - 2 * gap, 1.0)
        try:
            inner = tapring(pdk, enclosed_rectangle=(inner_w, inner_h), sdlayer="n+s/d")
        except Exception:
            inner = tapring(pdk, enclosed_rectangle=(inner_w, inner_h), sdlayer="p+s/d")
        component.add_ref(inner).move((cx, cy))
        print(f"[GUARD] Inner N+ tap: {inner_w:.1f}x{inner_h:.1f}um (gap={gap}um)")

    return component, ports


# ══════════════════════════════════════════════════════════════════════
#  DesignContext power rails
#
#  The legacy flow bolted power strips on after placement and fed their
#  ports into the router's goal list. The DesignContext flow needs the
#  rails to exist *before* routing, registered as real access points on the
#  supply nets, so the router treats them as terminals like any other and
#  LVS sees a connected supply.
# ══════════════════════════════════════════════════════════════════════

def add_power_rails(ctx, top, pdk, rail_layer="met5", access_layer="met3",
                    rail_width=2.0, margin=3.0, drop_pitch=12.0, verbosity=1):
    """Draw VDD and VSS rails and register them on the supply nets.

    A rail is a wide strip on ``rail_layer`` spanning the design, with via
    stacks dropping to ``access_layer`` at regular intervals. Each drop
    becomes a PinAccessPoint on the corresponding supply net, so the router
    connects device supply terminals to the nearest drop rather than daisy-
    chaining them through each other.

    Returns a dict describing what was created; records rail geometry on the
    context as net-owned obstacles so foreign nets route around it.
    """
    from mbg.design_context import BoundingBox, Obstacle, PinAccessPoint, Zone
    from mbg.pdk_rules import get_rules
    from glayout import via_stack
    from mbg.router import snap_to_grid

    rules = ctx.rules or get_rules(pdk)
    supplies = []
    for net in sorted(ctx.power_nets):
        supplies.append((net, "vdd"))
    for net in sorted(ctx.ground_nets):
        supplies.append((net, "vss"))
    if not supplies:
        if verbosity:
            print("  [POWER] no supply nets in the netlist — no rails added")
        return {"rails": [], "drops": 0}

    bb = ctx.design_bbox()
    x0 = rules.snap(bb.xmin - margin)
    x1 = rules.snap(bb.xmax + margin)
    span = x1 - x0
    if span <= 0:
        return {"rails": [], "drops": 0}

    hw = rail_width / 2.0
    rail_gds = rules.layer_tuple(rail_layer)
    n_drops = max(2, int(span // drop_pitch) + 1)
    created, total_drops = [], 0

    for idx, (net, kind) in enumerate(supplies):
        # VDD above the design, VSS below; extra supplies stack outwards.
        step = margin + rail_width * 1.5
        if kind == "vdd":
            y = bb.ymax + margin + step * (idx // 2)
        else:
            y = bb.ymin - margin - step * (idx // 2)
        # Land the rail on a routing track. Everything the router emits is
        # grid-aligned, and the pitch is what keeps it legal; an off-grid rail
        # drop is the one thing that can violate spacing against a route.
        _, y = snap_to_grid(ctx, x0, y)

        top.add_polygon([[x0, y - hw], [x1, y - hw], [x1, y + hw], [x0, y + hw]],
                        layer=rail_gds)

        rail_bb = BoundingBox(x0, y - hw, x1, y + hw)
        ctx.add_obstacle(Obstacle(layer=rail_layer, bbox=rail_bb,
                                  owner=f"RAIL_{net}", kind="power_rail", net=net))
        ctx.add_zone(Zone(kind="power", bbox=rail_bb, layers=[rail_layer],
                          owner=f"RAIL_{net}", net=net))

        # via drops to the routing layer, each an access point for this net
        stack = via_stack(pdk, access_layer, rail_layer, centered=True)
        pad = rules.via_footprint(access_layer, rail_layer)
        for k in range(n_drops):
            raw = x0 + (span * k) / max(1, n_drops - 1) if n_drops > 1 else x0 + span / 2
            dx, _ = snap_to_grid(ctx, min(max(raw, x0 + pad), x1 - pad), y)
            ref = top.add_ref(stack)
            ref.move((dx, y))

            # The drop pad sits wherever the rail geometry puts it, which is
            # not on the router's track grid. Register it as net-owned metal on
            # every layer the stack passes through so foreign nets are held off
            # by the normal spacing inflation; same-net routing still reaches it.
            half = pad / 2.0
            pad_bb = BoundingBox(dx - half, y - half, dx + half, y + half)
            for lname in rules.layers_traversed(access_layer, rail_layer):
                ctx.add_obstacle(Obstacle(layer=lname, bbox=pad_bb,
                                          owner=f"RAIL_{net}", kind="power_via",
                                          net=net))

            ctx.add_access_point(PinAccessPoint(
                instance=f"RAIL_{net}", terminal=f"tap{k}", net=net,
                layer=access_layer, x=dx, y=y, orientation=270.0 if kind == "vdd" else 90.0,
                width=pad))
            total_drops += 1

        # the supply net must be routable: give it terminals in the net record
        n = ctx.nets.get(net)
        if n is not None:
            for k in range(n_drops):
                n.terminals.append((f"RAIL_{net}", f"tap{k}"))

        created.append({"net": net, "kind": kind, "y": y, "x0": x0, "x1": x1,
                        "width": rail_width, "layer": rail_layer, "drops": n_drops})
        if verbosity:
            print(f"  [POWER] {kind.upper()} rail '{net}' on {rail_layer} "
                  f"y={y:.2f} x=[{x0:.2f},{x1:.2f}] {n_drops} via drops")

    return {"rails": created, "drops": total_drops}
