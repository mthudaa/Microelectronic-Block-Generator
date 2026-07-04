import math
from glayout import via_stack
import gdsfactory as gf

_pdk = None

def set_pdk(pdk_obj):
    global _pdk
    _pdk = pdk_obj

def get_pdk():
    return _pdk

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
        self.device_obs = {42: [], 46: [], 81: []}

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
                bx1, by1 = self._bucket(ox1, oy1)
                bx2, by2 = self._bucket(ox2, oy2)
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
        for poly in component.polygons:
            lyr = poly.layer
            if lyr not in self.device_obs:
                continue
            bbox = poly.bounding_box()
            self.device_obs[lyr].append((bbox[0][0], bbox[1][0], bbox[0][1], bbox[1][1]))

    def get_penalty(self, layer_id, x1, y1, x2, y2, current_net_idx):
        hw = self.spacing / 2.0
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
    min_x, max_x = min(x1, x2), max(x1, x2)
    min_y, max_y = min(y1, y2), max(y1, y2)

    if x1 != x2:
        min_x -= width / 2;   max_x += width / 2
        min_y -= width / 2;   max_y += width / 2
    else:
        min_x -= width / 2;   max_x += width / 2
        min_y -= width / 2;   max_y += width / 2

    c.add_polygon([[min_x, min_y], [max_x, min_y],
                   [max_x, max_y], [min_x, max_y]], layer=layer)
    memory.add_trace(layer[0], x1, y1, x2, y2, width, net_idx)


def place_via(c, x, y, l_bot, l_top, width, memory, net_idx, orientation=None):
    if l_bot == l_top:
        return
    via_ref = c.add_ref(via_stack(_pdk, l_bot, l_top, centered=True))
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
        blocked.append(42)
    if "met4" in [l_bot, l_top] or (l_bot == "met2" and l_top == "met5"):
        blocked.append(46)
    if "met5" in [l_bot, l_top]:
        blocked.append(81)

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

    if is_H and abs(y1 - y2) < 0.5:
        if not memory.is_clear(h_id, x1, y1, x2, y2, w, net_idx):
            return False
        place_via(component, x1, y1, "met2", h_str, w, memory, net_idx, o1)
        place_via(component, x2, y2, "met2", h_str, w, memory, net_idx, o2)
        draw_trace(component, h_layer, x1, y1, x2, y2, w, memory, net_idx)
        return True
    elif not is_H and abs(x1 - x2) < 0.5:
        if not memory.is_clear(46, x1, y1, x2, y2, w, net_idx):
            return False
        place_via(component, x1, y1, "met2", "met4", w, memory, net_idx, o1)
        place_via(component, x2, y2, "met2", "met4", w, memory, net_idx, o2)
        draw_trace(component, L_M4, x1, y1, x2, y2, w, memory, net_idx)
        return True
    return False


def route_L(component, p1, p2, w, h_layer, h_str, memory, net_idx):
    x1, y1, x2, y2 = p1.center[0], p1.center[1], p2.center[0], p2.center[1]
    h_id = h_layer[0]
    is_p1_H = (p1.orientation % 180 == 0)
    is_p2_H = (p2.orientation % 180 == 0)
    o1, o2 = p1.orientation, p2.orientation

    if is_p1_H == is_p2_H:
        return False

    if is_p1_H and not is_p2_H:
        if not (memory.is_clear(h_id, x1, y1, x2, y1, w, net_idx) and
                memory.is_clear(46, x2, y1, x2, y2, w, net_idx)):
            return False
        place_via(component, x1, y1, "met2", h_str, w, memory, net_idx, o1)
        place_via(component, x2, y2, "met2", "met4", w, memory, net_idx, o2)
        draw_trace(component, h_layer, x1, y1, x2, y1, w, memory, net_idx)
        draw_trace(component, L_M4, x2, y1, x2, y2, w, memory, net_idx)
        place_via(component, x2, y1, h_str, "met4", w, memory, net_idx)
    else:
        if not (memory.is_clear(46, x1, y1, x1, y2, w, net_idx) and
                memory.is_clear(h_id, x1, y2, x2, y2, w, net_idx)):
            return False
        place_via(component, x1, y1, "met2", "met4", w, memory, net_idx, o1)
        place_via(component, x2, y2, "met2", h_str, w, memory, net_idx, o2)
        draw_trace(component, L_M4, x1, y1, x1, y2, w, memory, net_idx)
        draw_trace(component, h_layer, x1, y2, x2, y2, w, memory, net_idx)
        place_via(component, x1, y2, h_str, "met4", w, memory, net_idx)

    return True


def route_Z(component, p1, p2, w, h_layer, h_str, memory, net_idx):
    x1, y1, x2, y2 = p1.center[0], p1.center[1], p2.center[0], p2.center[1]
    is_H = (p1.orientation % 180 == 0)
    o1, o2 = p1.orientation, p2.orientation

    if is_H:
        mid_x = find_clear_midpoint(x1, y1, x2, y2, w, memory, net_idx, True, h_layer)
        if mid_x is None:
            return False
        place_via(component, x1, y1, "met2", h_str, w, memory, net_idx, o1)
        place_via(component, x2, y2, "met2", h_str, w, memory, net_idx, o2)
        draw_trace(component, h_layer, x1, y1, mid_x, y1, w, memory, net_idx)
        draw_trace(component, L_M4, mid_x, y1, mid_x, y2, w, memory, net_idx)
        draw_trace(component, h_layer, mid_x, y2, x2, y2, w, memory, net_idx)
        place_via(component, mid_x, y1, h_str, "met4", w, memory, net_idx)
        place_via(component, mid_x, y2, h_str, "met4", w, memory, net_idx)
    else:
        mid_y = find_clear_midpoint(x1, y1, x2, y2, w, memory, net_idx, False, h_layer)
        if mid_y is None:
            return False
        place_via(component, x1, y1, "met2", "met4", w, memory, net_idx, o1)
        place_via(component, x2, y2, "met2", "met4", w, memory, net_idx, o2)
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
                    place_via(component, x1, y1, "met2", h_str, w, memory, net_idx, o1)
                    place_via(component, x2, y2, "met2", h_str, w, memory, net_idx, o2)
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
                    place_via(component, x1, y1, "met2", "met4", w, memory, net_idx, o1)
                    place_via(component, x2, y2, "met2", "met4", w, memory, net_idx, o2)
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
    memory.add_device_geometry(component)
    print(f"  [INFO] Device geometry: {len(component.polygons)} polygons loaded as obstacles")

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
