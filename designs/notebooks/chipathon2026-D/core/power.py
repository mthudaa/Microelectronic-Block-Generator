from glayout import via_stack, tapring


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

    vss_y = min_y - margin
    component.add_polygon([
        [min_x - margin, vss_y - hw], [min_x - margin + strip_w, vss_y - hw],
        [min_x - margin + strip_w, vss_y + hw], [min_x - margin, vss_y + hw],
    ], layer=met5)
    vss_via = component.add_ref(via_stack(pdk, "met2", "met5", centered=True))
    vss_via.move((min_x - margin + strip_w - 2.0, vss_y))
    vss_ports = [p for p in vss_via.get_ports_list() if "top_met" in p.name or "bottom_met" in p.name]

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
    return component, inner_ring, outer_ring
