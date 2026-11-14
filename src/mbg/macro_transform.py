"""Normalize final macro geometry and its physical contract in one operation."""
from mbg.design_context import BoundingBox


def normalize_macro(ctx, top):
    """Translate the declared macro lower-left to zero before GDS sign-off."""
    bb = ctx.macro_bbox
    if bb is None:
        return top
    dx, dy = -bb.xmin, -bb.ymin
    from gdsfactory import Component
    normalized = Component()
    ref = normalized.add_ref(top)
    ref.move((dx, dy))
    top = normalized.flatten()
    ctx.component = top
    seen = set()

    def box(b):
        if id(b) in seen:
            return
        seen.add(id(b))
        b.xmin += dx
        b.xmax += dx
        b.ymin += dy
        b.ymax += dy

    def point(p):
        if id(p) in seen:
            return
        seen.add(id(p))
        p.x += dx
        p.y += dy

    for b in ctx.device_bboxes.values():
        box(b)
    box(bb)
    for p in ctx.placements.values():
        point(p)
    for aps in ctx.net_to_access.values():
        for p in aps:
            point(p)
    # The delivered component is already a flattened copy. Keep retained
    # device references and aliased live Port objects in that same frame;
    # neither moving the wrapper nor translating AP scalars updates them.
    ports = {}
    for values in ctx.terminal_to_ports.values():
        for port in values:
            ports.setdefault(id(port), (port, tuple(port.center)))
    for aps in ctx.net_to_access.values():
        for ap in aps:
            if ap.port is not None:
                ports.setdefault(id(ap.port), (ap.port, tuple(ap.port.center)))
    moved_refs = set()
    for ref in ctx.references.values():
        if id(ref) not in moved_refs:
            ref.move((dx, dy))
            moved_refs.add(id(ref))
            _ = ref.ports  # refresh transformed reference-port caches
    for port, (x, y) in ports.values():
        port.move((x + dx - port.center[0], y + dy - port.center[1]))
    for ob in [*ctx.obstacles, *ctx.reserved_zones]:
        box(ob.bbox)
    # Plans and context segments can reference the same objects.
    for seg in [*ctx.segments, *(s for rn in ctx.routed_nets.values()
                                for plan in rn.plans for s in plan.segments)]:
        if id(seg) not in seen:
            seen.add(id(seg))
            seg.x1 += dx
            seg.x2 += dx
            seg.y1 += dy
            seg.y2 += dy
    for via in [*ctx.vias, *(v for rn in ctx.routed_nets.values()
                           for plan in rn.plans for v in plan.vias)]:
        point(via)

    def metadata(value):
        if isinstance(value, dict):
            for key, v in list(value.items()):
                if key in ('config', 'dut', 'wrapper'):
                    continue  # user constraints already use the normalized frame
                if key in ('rect', 'bounds', 'bbox', 'core_bounds', 'tap') and isinstance(v, (list, tuple)) and len(v) == 4:
                    value[key] = [v[0]+dx, v[1]+dy, v[2]+dx, v[3]+dy]
                elif key == 'rects' and isinstance(v, list):
                    value[key] = [[r[0]+dx, r[1]+dy, r[2]+dx, r[3]+dy] for r in v]
                elif key in ('center', 'position', 'access') and isinstance(v, (list, tuple)) and len(v) == 2:
                    value[key] = [v[0]+dx, v[1]+dy]
                else:
                    metadata(v)
        elif isinstance(value, list):
            for v in value:
                metadata(v)
    metadata(ctx.macro_interface)
    ctx.macro_interface['origin'] = [0.0, 0.0]
    ctx.macro_interface['translation'] = [dx, dy]
    return top
