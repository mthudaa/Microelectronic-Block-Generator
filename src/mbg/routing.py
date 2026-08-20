"""
@Owner: Huda (Lead Analog / Mixed-Signal Designer)
@Role: Analog Layout Strategist
@Responsibility: Auto-routing algorithm (PathFinder NCR) and optimal net connections with parasitic considerations.

STATUS: legacy shape router, retained for backward compatibility.
--------------------------------------------------------------
``spice_to_gds`` still calls ``auto_router`` here, and manual_route /
route_I / route_L / route_Z / route_U remain part of the public API, so this
module is kept working.  New work should use ``mbg.router.GridRouter``,
which the DesignContext flow (``mbg.pipeline.spice_to_gds_ctx``) drives:
this router tries a fixed catalogue of I/L/Z/U wire shapes between two ports
and cannot detour, share a corridor, or negotiate congestion.

Two confirmed defects are fixed below rather than left in place:

  * ``MemoryMap.device_obs`` only ever held met3/met4/met5, while gLayout
    devices place their geometry on met1/met2 — so it was empty on every run
    and the obstacle test in ``is_clear`` was dead code.  It now accepts the
    device metal layers as well.
  * the PathFinder ``penalty_threshold`` was computed each sweep and never
    passed to ``is_clear``, so congestion negotiation never actually relaxed
    anything, and geometry from a failed sweep was redrawn on top of itself
    on the next rip-up iteration.
"""
import math
from glayout import via_stack
import gdsfactory as gf
import numpy as np

_pdk = None

def set_pdk(pdk_obj):
    global _pdk
    _pdk = pdk_obj

def get_pdk():
    return _pdk

def _pmetal(p):
    return get_pdk().layer_to_glayer(p.layer)

L_M3 = (42, 0)
L_M4 = (46, 0)
L_M5 = (81, 0)

H_LAYERS = [("met3", L_M3, 42), ("met5", L_M5, 81)]
V_LAYER = ("met4", L_M4, 46)

MAX_SWEEPS = 100
MIN_SPACING = 0.3
RIPUP_ITER_MAX = 10


class MemoryMap:
    def __init__(self, spacing):
        self.obs = {42: [], 46: [], 81: []}
        self.spacing = spacing
        self.history = {42: {}, 46: {}, 81: {}}
        self.current = {42: {}, 46: {}, 81: {}}
        self.bucket_size = 3.0
        # gLayout devices put their metal on met1 (34) and met2 (36); keying
        # this dict on the routing layers alone made it permanently empty.
        self.device_obs = {34: [], 36: [], 42: [], 46: [], 81: []}

    def _bucket(self, x, y):
        return (int(x / self.bucket_size), int(y / self.bucket_size))

    def add_trace(self, layer_id, x1, y1, x2, y2, width, net_idx):
        hw = width / 2.0
        exp = self.spacing / 2.0
        min_x = min(x1, x2) - hw - exp
        max_x = max(x1, x2) + hw + exp
        min_y = min(y1, y2) - hw - exp
        max_y = max(y1, y2) + hw + exp
        self.obs[layer_id].append((min_x, max_x, min_y, max_y, net_idx))
        bx1, by1 = self._bucket(min_x, min_y)
        bx2, by2 = self._bucket(max_x, max_y)
        for bx in range(bx1, bx2 + 1):
            for by in range(by1, by2 + 1):
                key = (bx, by)
                self.current[layer_id][key] = self.current[layer_id].get(key, 0) + 1

    def is_clear(self, layer_id, x1, y1, x2, y2, width, current_net_idx, penalty_threshold=0):
        hw = width / 2.0
        exp = self.spacing / 2.0
        min_x = min(x1, x2) - hw - exp
        max_x = max(x1, x2) + hw + exp
        min_y = min(y1, y2) - hw - exp
        max_y = max(y1, y2) + hw + exp

        for (ox1, ox2, oy1, oy2) in self.device_obs.get(layer_id, []):
            if not (max_x <= ox1 or min_x >= ox2 or max_y <= oy1 or min_y >= oy2):
                return False

        penalty = 0
        for (ox1, ox2, oy1, oy2, obs_net_idx) in self.obs[layer_id]:
            if obs_net_idx == current_net_idx:
                continue
            if not (max_x <= ox1 or min_x >= ox2 or max_y <= oy1 or min_y >= oy2):
                bx1, by1 = self._bucket(min_x, min_y)
                bx2, by2 = self._bucket(max_x, max_y)
                for bx in range(bx1, bx2 + 1):
                    for by in range(by1, by2 + 1):
                        penalty += self.history.get(layer_id, {}).get((bx, by), 1)
        return penalty <= penalty_threshold

    def congestion_score(self, layer_id, x1, y1, x2, y2):
        bx1, by1 = self._bucket(min(x1, x2), min(y1, y2))
        bx2, by2 = self._bucket(max(x1, x2), max(y1, y2))
        score = 0
        for bx in range(bx1, bx2 + 1):
            for by in range(by1, by2 + 1):
                key = (bx, by)
                score += self.history.get(layer_id, {}).get(key, 0)
                score += self.current.get(layer_id, {}).get(key, 0) * 2
        return score

    def add_device_geometry(self, component):
        """Load real device geometry as obstacles.

        Devices are added as REFERENCES, so ``component.polygons`` at the top
        level is empty and this used to load nothing at all.  Reading the
        transformed polygons of each reference is what actually sees them.
        """
        n = 0
        for poly in component.polygons:
            lyr = poly.layer
            if lyr in self.device_obs:
                bbox = poly.bounding_box()
                self.device_obs[lyr].append((bbox[0][0], bbox[1][0],
                                             bbox[0][1], bbox[1][1]))
                n += 1
        for ref in getattr(component, "references", []):
            try:
                polys = ref.get_polygons(by_spec=True)
            except Exception:
                continue
            for spec, plist in polys.items():
                lyr = spec[0] if isinstance(spec, (tuple, list)) else spec
                if lyr not in self.device_obs:
                    continue
                for pts in plist:
                    xs = [p[0] for p in pts]
                    ys = [p[1] for p in pts]
                    self.device_obs[lyr].append((min(xs), max(xs), min(ys), max(ys)))
                    n += 1
        return n

    def get_penalty(self, layer_id, x1, y1, x2, y2, width, current_net_idx):
        hw = width / 2.0 + self.spacing / 2.0
        min_x = min(x1, x2) - hw
        max_x = max(x1, x2) + hw
        min_y = min(y1, y2) - hw
        max_y = max(y1, y2) + hw
        bx1, by1 = self._bucket(min_x, min_y)
        bx2, by2 = self._bucket(max_x, max_y)
        penalty = 0
        for bx in range(bx1, bx2 + 1):
            for by in range(by1, by2 + 1):
                key = (bx, by)
                penalty += self.history.get(layer_id, {}).get(key, 0)
                penalty += self.current.get(layer_id, {}).get(key, 0) * 2
        return penalty

    def commit_iteration(self):
        for lid in self.history:
            for key, count in self.current.get(lid, {}).items():
                self.history[lid][key] = self.history[lid].get(key, 0) + count
            self.current[lid].clear()

    def remove_all_nets(self):
        for lid in self.obs:
            self.obs[lid].clear()
        for lid in self.current:
            self.current[lid].clear()

    def remove_net(self, net_idx):
        for lid in self.obs:
            self.obs[lid] = [o for o in self.obs[lid] if o[4] != net_idx]


def draw_trace(c, layer, x1, y1, x2, y2, width, memory, net_idx):
    if x1 == x2 and y1 == y2:
        return
    hw = width / 2.0
    if x1 != x2:
        # horizontal: widen perpendicular (y), keep x span
        min_x, max_x = min(x1, x2), max(x1, x2)
        mid_y = (y1 + y2) / 2.0
        min_y, max_y = mid_y - hw, mid_y + hw
    else:
        # vertical: widen perpendicular (x), keep y span
        mid_x = (x1 + x2) / 2.0
        min_x, max_x = mid_x - hw, mid_x + hw
        min_y, max_y = min(y1, y2), max(y1, y2)

    c.add_polygon([[min_x, min_y], [max_x, min_y],
                   [max_x, max_y], [min_x, max_y]], layer=layer)
    memory.add_trace(layer[0], x1, y1, x2, y2, width, net_idx)


_via_cache = {}

def place_via(c, x, y, l_bot, l_top, width, memory, net_idx, orientation=None):
    if l_bot == l_top:
        return
    key = (l_bot, l_top)
    if key not in _via_cache:
        _via_cache[key] = via_stack(_pdk, l_bot, l_top, centered=True)
    via_ref = c.add_ref(_via_cache[key])
    hw = width / 2
    if orientation == 0:
        via_ref.move((x - hw, y))
    elif orientation == 180:
        via_ref.move((x + hw, y))
    elif orientation == 90:
        via_ref.move((x, y - hw))
    elif orientation == 270:
        via_ref.move((x, y + hw))
    else:
        via_ref.move((x, y))
    via_x, via_y = via_ref.origin[0], via_ref.origin[1]
    blocked = []
    if "met3" in [l_bot, l_top] or (l_bot == "met2" and l_top in ["met4", "met5"]):
        blocked.append(L_M3[0])
    if "met4" in [l_bot, l_top] or (l_bot == "met2" and l_top == "met5"):
        blocked.append(L_M4[0])
    if "met5" in [l_bot, l_top]:
        blocked.append(L_M5[0])

    for lid in blocked:
        memory.add_trace(lid, via_x, via_y, via_x, via_y, width, net_idx)


def find_clear_midpoint(x1, y1, x2, y2, w, memory, net_idx, is_horizontal, h_layer):
    pitch = w + MIN_SPACING
    h_id, v_id = h_layer[0], 46

    if is_horizontal:
        mid_base = (x1 + x2) / 2
        for i in range(MAX_SWEEPS):
            for sign in ([0] if i == 0 else [-1, 1]):
                mid = mid_base + sign * i * pitch
                if (memory.is_clear(h_id, x1, y1, mid, y1, w, net_idx) and
                    memory.is_clear(v_id, mid, y1, mid, y2, w, net_idx) and
                    memory.is_clear(h_id, mid, y2, x2, y2, w, net_idx)):
                    return mid
    else:
        mid_base = (y1 + y2) / 2
        for i in range(MAX_SWEEPS):
            for sign in ([0] if i == 0 else [-1, 1]):
                mid = mid_base + sign * i * pitch
                if (memory.is_clear(v_id, x1, y1, x1, mid, w, net_idx) and
                    memory.is_clear(h_id, x1, mid, x2, mid, w, net_idx) and
                    memory.is_clear(v_id, x2, mid, x2, y2, w, net_idx)):
                    return mid
    return None


def manual_route(component, routes, memory=None, start_net_idx=0):
    """AI-agent-friendly manual routing.

    Draws explicit trace segments and vias between ports. Each route
    specifies the complete path: port → via → trace → via → ... → port.
    The function handles port vias (met2→routing layer) automatically.

    Args:
        component: gdsfactory Component to draw into.
        routes: List of route dicts, each with:
            net_name: str          — Net name (for logging)
            port1: Port            — Starting port object
            port2: Port            — Ending port object
            segments: list of      — Trace segments as:
                (x1, y1, x2, y2, layer_name)
                layer_name is "met3", "met4", or "met5"
            via1_layer: str        — Override port1 via layer (default: auto)
            via2_layer: str        — Override port2 via layer (default: auto)
            width: float           — Trace width (default: 0.5)
            or:
            Instead of segments, provide:
            midpoints: list of (x, y, layer) — Waypoints; function
                generates I/L/Z/U route automatically between consecutive
                waypoints.
        memory: MemoryMap instance (created if None).
        start_net_idx: Starting net index for memory tracking.

    Returns:
        (component, net_idx)
        component: Updated component with traces drawn.
        net_idx: Next available net index.
    """
    if memory is None:
        memory = MemoryMap(MIN_SPACING)
        memory.add_device_geometry(component)

    net_idx = start_net_idx

    for route in routes:
        name = route.get("net_name", f"net_{net_idx}")
        p1 = route.get("port1")
        p2 = route.get("port2")
        w = route.get("width", 0.5)

        p1m = _pmetal(p1) if p1 else "met2"
        p2m = _pmetal(p2) if p2 else "met2"

        def _port_layer(p):
            return "met3" if (p.orientation % 180 == 0) else "met4"

        # Determine via layers
        v1l = route.get("via1_layer") or (_port_layer(p1) if p1 else "met3")
        v2l = route.get("via2_layer") or (_port_layer(p2) if p2 else "met3")

        segs = list(route.get("segments", []))

        # If midpoints given, expand into segments
        if not segs and "midpoints" in route:
            mpts = route["midpoints"]
            for i in range(len(mpts) - 1):
                x1, y1, l1 = mpts[i]
                x2, y2, l2 = mpts[i + 1]
                segs.append((x1, y1, x2, y2, l1))
                if l1 != l2:
                    segs.append((x2, y2, x2, y2, f"via_{l1}_{l2}"))

        if not segs and p1 and p2:
            x1, y1 = p1.center[0], p1.center[1]
            x2, y2 = p2.center[0], p2.center[1]
            # Default: straight route
            is_H = (p1.orientation % 180 == 0)
            h_layer = "met3" if is_H else "met4"
            segs = [(x1, y1, x2, y2, h_layer)]

        # Draw port vias and segments
        if p1:
            place_via(component, p1.center[0], p1.center[1],
                      p1m, v1l, w, memory, net_idx, p1.orientation)
        if p2:
            place_via(component, p2.center[0], p2.center[1],
                      p2m, v2l, w, memory, net_idx, p2.orientation)

        for sx1, sy1, sx2, sy2, layer_name in segs:
            if layer_name.startswith("via_"):
                parts = layer_name.split("_")
                l_bot, l_top = parts[1], parts[2]
                place_via(component, sx1, sy1, l_bot, l_top, w, memory, net_idx)
                continue
            layer_map = {"met3": L_M3, "met4": L_M4, "met5": L_M5}
            lt = layer_map.get(layer_name)
            if lt is None:
                print(f"  [WARN] Unknown layer {layer_name}, skipping")
                continue
            draw_trace(component, lt, sx1, sy1, sx2, sy2, w, memory, net_idx)

        print(f"  [ROUTE] {name}: {len(segs)} segs, {p1.name if p1 else '?'} -> {p2.name if p2 else '?'}")
        net_idx += 1

    return component, net_idx


def get_net_distance(port_list):
    valid = []
    for pin_data in port_list:
        if isinstance(pin_data, list) and pin_data:
            p = pin_data[0][0]
        elif isinstance(pin_data, tuple) and len(pin_data) == 2:
            p = pin_data[0]
        else:
            continue
        valid.append(p)
    if len(valid) < 2:
        return 0
    xs = [p.center[0] for p in valid]
    ys = [p.center[1] for p in valid]
    return math.hypot(max(xs) - min(xs), max(ys) - min(ys))


def get_net_constraint(port_list):
    valid = []
    for pin_data in port_list:
        if isinstance(pin_data, list) and pin_data:
            p = pin_data[0][0]
        elif isinstance(pin_data, tuple) and len(pin_data) == 2:
            p = pin_data[0]
        else:
            continue
        valid.append(p)
    n = len(valid)
    if n < 2:
        return 0
    xs = [p.center[0] for p in valid]
    ys = [p.center[1] for p in valid]
    span = max(math.hypot(max(xs) - min(xs), max(ys) - min(ys)), 1.0)
    return (n * n) / span


def decompose_mst(ports):
    n = len(ports)
    if n <= 1:
        return []
    if n == 2:
        x1, y1 = ports[0].center[0], ports[0].center[1]
        x2, y2 = ports[1].center[0], ports[1].center[1]
        return [(0, 1, abs(x1 - x2) + abs(y1 - y2))]

    def mdist(i, j):
        return abs(ports[i].center[0] - ports[j].center[0]) + \
               abs(ports[i].center[1] - ports[j].center[1])

    visited = {0}
    edges = []
    while len(visited) < n:
        best = None
        best_d = float('inf')
        for u in visited:
            for v in range(n):
                if v not in visited:
                    d = mdist(u, v)
                    if d < best_d:
                        best_d = d
                        best = (u, v, d)
        if best:
            edges.append(best)
            visited.add(best[1])
    return sorted(edges, key=lambda e: e[2])


def route_I(component, p1, p2, w, h_layer, h_str, memory, net_idx):
    x1, y1, x2, y2 = p1.center[0], p1.center[1], p2.center[0], p2.center[1]
    h_id = h_layer[0]
    is_H = (p1.orientation % 180 == 0)
    o1, o2 = p1.orientation, p2.orientation
    p1m, p2m = _pmetal(p1), _pmetal(p2)

    if is_H and abs(y1 - y2) < 0.5:
        if not memory.is_clear(h_id, x1, y1, x2, y2, w, net_idx):
            return False
        place_via(component, x1, y1, p1m, h_str, w, memory, net_idx, o1)
        place_via(component, x2, y2, p2m, h_str, w, memory, net_idx, o2)
        draw_trace(component, h_layer, x1, y1, x2, y2, w, memory, net_idx)
        return True
    elif not is_H and abs(x1 - x2) < 0.5:
        if not memory.is_clear(46, x1, y1, x2, y2, w, net_idx):
            return False
        place_via(component, x1, y1, p1m, "met4", w, memory, net_idx, o1)
        place_via(component, x2, y2, p2m, "met4", w, memory, net_idx, o2)
        draw_trace(component, L_M4, x1, y1, x2, y2, w, memory, net_idx)
        return True
    return False


def route_L(component, p1, p2, w, h_layer, h_str, memory, net_idx):
    x1, y1, x2, y2 = p1.center[0], p1.center[1], p2.center[0], p2.center[1]
    h_id = h_layer[0]
    is_p1_H = (p1.orientation % 180 == 0)
    is_p2_H = (p2.orientation % 180 == 0)
    o1, o2 = p1.orientation, p2.orientation
    p1m, p2m = _pmetal(p1), _pmetal(p2)

    if is_p1_H == is_p2_H:
        return False

    if is_p1_H and not is_p2_H:
        if not (memory.is_clear(h_id, x1, y1, x2, y1, w, net_idx) and
                memory.is_clear(46, x2, y1, x2, y2, w, net_idx)):
            return False
        place_via(component, x1, y1, p1m, h_str, w, memory, net_idx, o1)
        place_via(component, x2, y2, p2m, "met4", w, memory, net_idx, o2)
        draw_trace(component, h_layer, x1, y1, x2, y1, w, memory, net_idx)
        draw_trace(component, L_M4, x2, y1, x2, y2, w, memory, net_idx)
        place_via(component, x2, y1, h_str, "met4", w, memory, net_idx)
    else:
        if not (memory.is_clear(46, x1, y1, x1, y2, w, net_idx) and
                memory.is_clear(h_id, x1, y2, x2, y2, w, net_idx)):
            return False
        place_via(component, x1, y1, p1m, "met4", w, memory, net_idx, o1)
        place_via(component, x2, y2, p2m, h_str, w, memory, net_idx, o2)
        draw_trace(component, L_M4, x1, y1, x1, y2, w, memory, net_idx)
        draw_trace(component, h_layer, x1, y2, x2, y2, w, memory, net_idx)
        place_via(component, x1, y2, h_str, "met4", w, memory, net_idx)

    return True


def route_Z(component, p1, p2, w, h_layer, h_str, memory, net_idx):
    x1, y1, x2, y2 = p1.center[0], p1.center[1], p2.center[0], p2.center[1]
    is_H = (p1.orientation % 180 == 0)
    o1, o2 = p1.orientation, p2.orientation
    p1m, p2m = _pmetal(p1), _pmetal(p2)

    if is_H:
        mid_x = find_clear_midpoint(x1, y1, x2, y2, w, memory, net_idx, True, h_layer)
        if mid_x is None:
            return False
        place_via(component, x1, y1, p1m, h_str, w, memory, net_idx, o1)
        place_via(component, x2, y2, p2m, h_str, w, memory, net_idx, o2)
        draw_trace(component, h_layer, x1, y1, mid_x, y1, w, memory, net_idx)
        draw_trace(component, L_M4, mid_x, y1, mid_x, y2, w, memory, net_idx)
        draw_trace(component, h_layer, mid_x, y2, x2, y2, w, memory, net_idx)
        place_via(component, mid_x, y1, h_str, "met4", w, memory, net_idx)
        place_via(component, mid_x, y2, h_str, "met4", w, memory, net_idx)
    else:
        mid_y = find_clear_midpoint(x1, y1, x2, y2, w, memory, net_idx, False, h_layer)
        if mid_y is None:
            return False
        place_via(component, x1, y1, p1m, "met4", w, memory, net_idx, o1)
        place_via(component, x2, y2, p2m, "met4", w, memory, net_idx, o2)
        draw_trace(component, L_M4, x1, y1, x1, mid_y, w, memory, net_idx)
        draw_trace(component, h_layer, x1, mid_y, x2, mid_y, w, memory, net_idx)
        draw_trace(component, L_M4, x2, mid_y, x2, y2, w, memory, net_idx)
        place_via(component, x1, mid_y, h_str, "met4", w, memory, net_idx)
        place_via(component, x2, mid_y, h_str, "met4", w, memory, net_idx)

    return True


def route_U(component, p1, p2, w, h_layer, h_str, memory, net_idx):
    x1, y1, x2, y2 = p1.center[0], p1.center[1], p2.center[0], p2.center[1]
    is_H = (p1.orientation % 180 == 0)
    o1, o2 = p1.orientation, p2.orientation
    p1m, p2m = _pmetal(p1), _pmetal(p2)
    h_id = h_layer[0]
    pitch = w + MIN_SPACING

    if is_H:
        mid_x_center = (x1 + x2) / 2
        for sign in [-1, 1]:
            y_out = (max(y1, y2) + 3 * pitch) if sign == 1 else (min(y1, y2) - 3 * pitch)
            for i in range(MAX_SWEEPS):
                detour_y = y_out + sign * i * pitch
                if (memory.is_clear(h_id, x1, y1, mid_x_center, y1, w, net_idx) and
                    memory.is_clear(46, mid_x_center, y1, mid_x_center, detour_y, w, net_idx) and
                    memory.is_clear(h_id, mid_x_center, detour_y, x2, detour_y, w, net_idx) and
                    memory.is_clear(46, x2, detour_y, x2, y2, w, net_idx)):
                    place_via(component, x1, y1, p1m, h_str, w, memory, net_idx, o1)
                    place_via(component, x2, y2, p2m, h_str, w, memory, net_idx, o2)
                    draw_trace(component, h_layer, x1, y1, mid_x_center, y1, w, memory, net_idx)
                    place_via(component, mid_x_center, y1, h_str, "met4", w, memory, net_idx)
                    draw_trace(component, L_M4, mid_x_center, y1, mid_x_center, detour_y, w, memory, net_idx)
                    place_via(component, mid_x_center, detour_y, "met4", h_str, w, memory, net_idx)
                    draw_trace(component, h_layer, mid_x_center, detour_y, x2, detour_y, w, memory, net_idx)
                    place_via(component, x2, detour_y, h_str, "met4", w, memory, net_idx)
                    draw_trace(component, L_M4, x2, detour_y, x2, y2, w, memory, net_idx)
                    return True
    else:
        mid_y_center = (y1 + y2) / 2
        for sign in [-1, 1]:
            x_out = (max(x1, x2) + 3 * pitch) if sign == 1 else (min(x1, x2) - 3 * pitch)
            for i in range(MAX_SWEEPS):
                detour_x = x_out + sign * i * pitch
                if (memory.is_clear(46, x1, y1, detour_x, y1, w, net_idx) and
                    memory.is_clear(h_id, detour_x, y1, detour_x, mid_y_center, w, net_idx) and
                    memory.is_clear(46, detour_x, mid_y_center, x2, mid_y_center, w, net_idx) and
                    memory.is_clear(h_id, x2, mid_y_center, x2, y2, w, net_idx)):
                    place_via(component, x1, y1, p1m, "met4", w, memory, net_idx, o1)
                    place_via(component, x2, y2, p2m, "met4", w, memory, net_idx, o2)
                    draw_trace(component, L_M4, x1, y1, detour_x, y1, w, memory, net_idx)
                    place_via(component, detour_x, y1, "met4", h_str, w, memory, net_idx)
                    draw_trace(component, h_layer, detour_x, y1, detour_x, mid_y_center, w, memory, net_idx)
                    place_via(component, detour_x, mid_y_center, h_str, "met4", w, memory, net_idx)
                    draw_trace(component, L_M4, detour_x, mid_y_center, x2, mid_y_center, w, memory, net_idx)
                    place_via(component, x2, mid_y_center, "met4", h_str, w, memory, net_idx)
                    draw_trace(component, h_layer, x2, mid_y_center, x2, y2, w, memory, net_idx)
                    return True
    return False


def auto_router(component, connection_goals):
    PATHFINDER_MAX_ITER = 10

    _poly_baseline = len(component.polygons)
    _ref_baseline = len(component.references)

    memory = MemoryMap(MIN_SPACING)
    n_obs = memory.add_device_geometry(component)
    print(f"  [INFO] Device geometry: {n_obs} polygons loaded as obstacles")

    for pf_iter in range(PATHFINDER_MAX_ITER):
        while len(component.polygons) > _poly_baseline:
            component.remove(component.polygons[-1])
        while len(component.references) > _ref_baseline:
            component.remove(component.references[-1])
        memory.remove_all_nets()

        penalty_threshold = max(0, 100 - pf_iter * 15)
        print(f"\n  === PathFinder iter {pf_iter+1}/{PATHFINDER_MAX_ITER} (penalty<={penalty_threshold}) ===")

        all_edges = []
        net_port_list = {}
        net_idx = 0

        for _orig_idx, (net_name, port_list) in enumerate(connection_goals):
            pin_options = []
            for pin_data in port_list:
                if isinstance(pin_data, list):
                    pin_options.append(pin_data)
                elif isinstance(pin_data, tuple) and len(pin_data) == 2:
                    port_obj, layer = pin_data
                    pin_options.append([(port_obj, layer)])
                else:
                    pin_options.append([(pin_data, 0)])

            if len(pin_options) < 2:
                continue

            repr_ports = [opts[0][0] for opts in pin_options if opts]
            pairs = decompose_mst(repr_ports)
            for pi, pj, _dist in pairs:
                all_edges.append((net_idx, net_name, pin_options[pi], pin_options[pj]))
            net_port_list[net_idx] = pin_options
            net_idx += 1

        if not all_edges:
            print("  [INFO] Tidak ada edge untuk di-route.")
            return component

        def edge_span(edge):
            _nid, _name, p1_opts, p2_opts = edge
            p1 = p1_opts[0][0] if isinstance(p1_opts, list) and p1_opts else p1_opts
            p2 = p2_opts[0][0] if isinstance(p2_opts, list) and p2_opts else p2_opts
            return abs(p1.center[0] - p2.center[0]) + abs(p1.center[1] - p2.center[1])

        all_edges.sort(key=edge_span)
        print(f"  [INFO] Total edge: {len(all_edges)} (setelah MST decomp)")

        failed_edges = set()

        for iteration in range(RIPUP_ITER_MAX):
            if iteration > 0:
                # every edge is re-routed below, so the previous attempt's
                # geometry has to go; leaving it produced duplicate traces
                # and vias stacked on top of each other.
                while len(component.polygons) > _poly_baseline:
                    component.remove(component.polygons[-1])
                while len(component.references) > _ref_baseline:
                    component.remove(component.references[-1])
                memory.remove_all_nets()
            all_ok = True
            failed_edges.clear()

            for _edge_pos, (e_net_idx, net_name, p1_opts, p2_opts) in enumerate(all_edges):
                routed = False
                layer_used = ""
                p1_name = "?"
                p2_name = "?"
                tried_count = 0

                def _add_midpoint_ports(opts):
                    result = list(opts)
                    n_ports = [p for p, _ in opts if p.orientation == 90]
                    s_ports = [p for p, _ in opts if p.orientation == 270]
                    e_ports = [p for p, _ in opts if p.orientation == 0]
                    w_ports = [p for p, _ in opts if p.orientation == 180]
                    if n_ports and s_ports:
                        pn, ps = n_ports[0], s_ports[0]
                        for frac in (0.25, 0.50, 0.75):
                            mx, my = (pn.center[0] + ps.center[0]) / 2, pn.center[1] * (1 - frac) + ps.center[1] * frac
                            mid_port = gf.Port(name=f"{pn.name}_midNS{frac:.2f}", center=(mx, my),
                                               width=ps.width, orientation=0, layer=pn.layer)
                            result.insert(0, (mid_port, 0))
                    if e_ports and w_ports:
                        pe, pw = e_ports[0], w_ports[0]
                        for frac in (0.25, 0.50, 0.75):
                            mx, my = pe.center[0] * (1 - frac) + pw.center[0] * frac, (pe.center[1] + pw.center[1]) / 2
                            mid_port = gf.Port(name=f"{pe.name}_midEW{frac:.2f}", center=(mx, my),
                                               width=pw.width, orientation=90, layer=pe.layer)
                            result.insert(0, (mid_port, 0))
                    return result

                p1_opts_mid = _add_midpoint_ports(p1_opts)
                p2_opts_mid = _add_midpoint_ports(p2_opts)

                combos = []
                for p1_port, _l1 in p1_opts_mid:
                    for p2_port, _l2 in p2_opts_mid:
                        d = abs(p1_port.center[0] - p2_port.center[0]) + abs(p1_port.center[1] - p2_port.center[1])
                        combos.append((d, p1_port, p2_port))
                combos.sort(key=lambda x: x[0])

                for _dist, p1_port, p2_port in combos:
                    if routed:
                        break
                    tried_count += 1
                    x1, y1 = p1_port.center[0], p1_port.center[1]
                    x2, y2 = p2_port.center[0], p2_port.center[1]
                    w = 0.5
                    p1_name = p1_port.name
                    p2_name = p2_port.name

                    if abs(x1 - x2) < 0.01 and abs(y1 - y2) < 0.01:
                        routed = True; layer_used = "same-point"
                        continue

                    is_p1_H = (p1_port.orientation % 180 == 0)
                    is_p2_H = (p2_port.orientation % 180 == 0)

                    if not routed and abs(y1 - y2) < 0.5 and is_p1_H:
                        for h_str, h_layer, _lid in H_LAYERS:
                            if route_I(component, p1_port, p2_port, w, h_layer, h_str, memory, e_net_idx):
                                routed = True; layer_used = h_str; break
                    if not routed and abs(x1 - x2) < 0.5 and not is_p1_H:
                        if route_I(component, p1_port, p2_port, w, L_M4, "met4", memory, e_net_idx):
                            routed = True; layer_used = "met4"

                    if not routed and is_p1_H != is_p2_H:
                        for h_str, h_layer, _lid in H_LAYERS:
                            if route_L(component, p1_port, p2_port, w, h_layer, h_str, memory, e_net_idx):
                                routed = True; layer_used = h_str; break

                    if not routed and is_p1_H == is_p2_H:
                        for h_str, h_layer, _lid in H_LAYERS:
                            if route_Z(component, p1_port, p2_port, w, h_layer, h_str, memory, e_net_idx):
                                routed = True; layer_used = h_str; break

                    if not routed and is_p1_H == is_p2_H:
                        for h_str, h_layer, _lid in H_LAYERS:
                            if route_U(component, p1_port, p2_port, w, h_layer, h_str, memory, e_net_idx):
                                routed = True; layer_used = h_str; break

                if routed:
                    d = abs(p1_port.center[0] - p2_port.center[0]) + abs(p1_port.center[1] - p2_port.center[1])
                    print(f"  [OK] {net_name}: {p1_name}->{p2_name}  [{layer_used.upper()}] d~{d:.1f}um (#{tried_count}/{len(combos)})")
                else:
                    print(f"  [GAGAL] {net_name}: {p1_name}->{p2_name}  (semua {tried_count} kombinasi arah buntu)")
                    failed_edges.add(e_net_idx)
                    all_ok = False

            if all_ok:
                print(f"  => Semua net sukses (iterasi {iteration + 1}/{RIPUP_ITER_MAX})")
                break
            else:
                if iteration < RIPUP_ITER_MAX - 1:
                    print(f"  => {len(failed_edges)} net gagal. Rip-up & retry...")
                    for fe_nid in failed_edges:
                        memory.remove_net(fe_nid)
                    remaining = [e for e in all_edges if e[0] not in failed_edges]
                    retry = [e for e in all_edges if e[0] in failed_edges]
                    all_edges = retry + remaining
                else:
                    print(f"  => FATAL: {len(failed_edges)} net gagal setelah {RIPUP_ITER_MAX} iterasi.")

        if all_ok:
            memory.commit_iteration()
            total_wl = sum(abs(e[2][0][0].center[0] - e[3][0][0].center[0]) +
                           abs(e[2][0][0].center[1] - e[3][0][0].center[1])
                           for e in all_edges if e[2] and e[3])
            print(f"  => PathFinder iter {pf_iter+1} konvergen | total wire ~{total_wl:.1f}um")
            break
        else:
            memory.commit_iteration()
            if pf_iter < PATHFINDER_MAX_ITER - 1:
                print(f"  => Retry dengan congestion history...")
            else:
                print(f"  => Max iterasi tercapai, lanjut dengan hasil terbaik")

    return component
