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
