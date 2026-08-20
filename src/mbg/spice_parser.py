"""
@Owner: Huda (Lead Analog / Mixed-Signal Designer)
@Role: Analog Layout Strategist
@Responsibility: Parsing SPICE netlists into a data structure understood by the layout generator.
"""
import re
from collections import defaultdict
from gdsfactory import port

def _first(params, *keys, default="-"):
    """First key in `params` that carries a real value, not the "-" placeholder."""
    for k in keys:
        v = params.get(k, "-")
        if v not in ("-", "", None):
            return v
    return default


def parse_netlist_with_pdk(file_content, manual_pdk="Tidak Terdeteksi", mode="analog"):
    if file_content is None:
        raise ValueError("file_content is None — no SPICE netlist provided")
    parsed_components = []
    lines = file_content.replace('\r\n', '\n').replace('\r', '\n').strip().split('\n')
    
    # Variabel untuk menyimpan nama PDK
    detected_pdk = manual_pdk
    
    for line in lines:
        line_str = line.strip()
        
        # Abaikan baris kosong dan komentar
        if not line_str or line_str.startswith('*'):
            continue
            
        line_upper = line_str.upper()
        
        # --- DETEKSI PDK OTOMATIS ---
        if line_upper.startswith('.LIB') or line_upper.startswith('.INC'):
            if 'SKY130' in line_upper:
                detected_pdk = 'sky130'
            elif 'GF180' in line_upper:
                detected_pdk = 'gf180'
            continue 
            
        # Tangani perintah SPICE (.SUBCKT)
        if line_upper.startswith('.'):
            parts = line_str.split()
            command = parts[0].upper()
            
            if command == '.SUBCKT':
                subckt_name = parts[1]
                ports = parts[2:]
                parsed_components.append({
                    "type": "subcircuit",
                    "subcir": subckt_name,
                    "port": ports
                })
            continue
            
        # --- LOGIKA KOMPONEN ---
        parts = line_str.split()
        device_name = parts[0]
        device_type = device_name[0].upper()
        device_type_linear_dev = device_name.upper()[:2]  # Untuk menangani XC and XR (MIM Capacitor dan Resistor)
        
        params = {"w": "-", "l": "-", "m": "-", "nf": "-", "c_width": "-", "c_length": "-", "r_width": "-", "r_length": "-"}
        param_dict = None
        model_name = "-"
        nodes_dict = {}
        
        # MOSFET (supports standard SPICE names M1/M2... and XM1/XM2...)
        if device_type == 'M' or device_type_linear_dev == 'XM':
            nodes_dict = {
                "drain": parts[1] if len(parts) > 1 else "-",
                "gate": parts[2] if len(parts) > 2 else "-",
                "source": parts[3] if len(parts) > 3 else "-",
                "body": parts[4] if len(parts) > 4 else "-"
            }
            if len(parts) > 5:
                model_name = parts[5]
            remaining = " ".join(parts[6:])

        # CAPACITOR MIM (XC)
        elif device_type_linear_dev == 'XC':
            pre_params = []
            param_start_idx = len(parts)
            for i, p in enumerate(parts[1:], 1):
                if '=' in p:
                    param_start_idx = i
                    break
                pre_params.append(p)

            remaining = " ".join(parts[param_start_idx:])
            
            if len(pre_params) > 0:
                model_name = pre_params[-1]
                raw_nodes = pre_params[:-1]
            else:
                raw_nodes = []
                
            nodes_dict = {
                "p": raw_nodes[0] if len(raw_nodes) > 0 else "-",
                "n": raw_nodes[1] if len(raw_nodes) > 1 else "-",
                "body": raw_nodes[2] if len(raw_nodes) > 2 else "-"
            }

        # RESISTOR (XR)
        elif device_type_linear_dev == 'XR':
            pre_params = []
            param_start_idx = len(parts)
            for i, p in enumerate(parts[1:], 1):
                if '=' in p:
                    param_start_idx = i
                    break
                pre_params.append(p)

            remaining = " ".join(parts[param_start_idx:])
            
            if len(pre_params) > 0:
                model_name = pre_params[-1]
                raw_nodes = pre_params[:-1]
            else:
                raw_nodes = []
                
            nodes_dict = {
                "p": raw_nodes[0] if len(raw_nodes) > 0 else "-",
                "n": raw_nodes[1] if len(raw_nodes) > 1 else "-",
                "body": raw_nodes[2] if len(raw_nodes) > 2 else "-"
            }

        # SUBCIRCUIT (X)
        elif device_type == 'X': 
            nodes_and_name = [p for p in parts[1:] if '=' not in p]
            if len(nodes_and_name) > 0:
                model_name = nodes_and_name[-1] 
                raw_nodes = nodes_and_name[:-1]
                nodes_dict = {f"pin{i+1}": node for i, node in enumerate(raw_nodes)}
            remaining = "" 
            param_dict = {} 
            
        else: 
            raw_nodes = [parts[1], parts[2]] if len(parts) > 2 else [parts[1]]
            nodes_dict = {f"pin{i+1}": node for i, node in enumerate(raw_nodes)}
            if len(parts) > len(raw_nodes) + 1:
                model_name = parts[len(raw_nodes) + 1]
            remaining = " ".join(parts[len(raw_nodes) + 2:])

        # Ekstrak Parameter menggunakan Regex
        if param_dict is None:
            for p in params.keys():
                match = re.search(rf'{p}=(\S+)', remaining, re.IGNORECASE)
                if match:
                    params[p] = match.group(1)

            if device_type_linear_dev == 'XM':
                param_dict = { "w": params['w'], "l": params['l'], "m": params['m'], "nf": params['nf'] }
            elif device_type_linear_dev == 'XC':
                # A subcircuit capacitor may be sized either the PDK way
                # (c_width/c_length) or the way everyone actually writes it,
                # and the way the LLM emits it (W=/L=). Accepting only the
                # former silently dropped the size and fell back to a default.
                param_dict = { "c_width": _first(params, 'c_width', 'w'),
                               "c_length": _first(params, 'c_length', 'l'),
                               "m": params['m'] }
            elif device_type_linear_dev == 'XR':
                param_dict = { "r_width": _first(params, 'r_width', 'w'),
                               "r_length": _first(params, 'r_length', 'l'),
                               "m": params['m'] }
            elif device_type == 'R':
                param_dict = { "r_width": params.get('w', params.get('r_width', '-')),
                               "r_length": params.get('l', params.get('r_length', '-')),
                               "m": params['m'] }
            elif device_type == 'C':
                param_dict = { "c_width": params.get('w', params.get('c_width', '-')),
                               "c_length": params.get('l', params.get('c_length', '-')),
                               "m": params['m'] }
            else:
                param_dict = { "w": params['w'], "l": params['l'], "m": params['m'] }
            
        parsed_components.append({
            "type": "device",
            "name": device_name,
            "parameters": param_dict,
            "nodes": nodes_dict,
            "model": model_name
        })

    # --- BUNGKUS KE DALAM STRUKTUR FINAL ---
    final_output = {
        "metadata": {
            "pdk": detected_pdk
        },
        "components": parsed_components
    }

    _assign_initial_placement(final_output)

    return final_output



def _assign_initial_placement(final_output):
    """Give every device a first-pass (x, y) from a multi-row floorplan.

    Split out of ``parse_netlist_with_pdk`` unchanged: a netlist parser
    had no business also being a placer, and the two concerns together ran
    to 365 lines. This mutates ``final_output`` in place, exactly as the
    inlined version did, and the DesignContext flow later replaces these
    coordinates with analog-aware placement — they are a starting point,
    not the final floorplan.
    """
    # Ambil list device saja untuk kalkulasi matriks
    devices = [c for c in final_output["components"] if c["type"] == "device"]

    # --- Helper untuk mengubah nilai string '10u' menjadi float ---
    def parse_micrometer(val_str):
        val_str = val_str.replace('-', '0')
        if val_str.lower().endswith('u'):
            return float(val_str[:-1])
        try:
            return float(val_str)
        except ValueError:
            return 0.0

    # --- LOGIKA SCORES KONEKSI ---
    vdd_counts = defaultdict(int)
    vss_counts = defaultdict(int)
    net_to_devices = defaultdict(list)

    for dev in devices:
        name = dev["name"]
        for pin, net in dev["nodes"].items():
            if net == "-": continue
            if net.lower() == "vdd": vdd_counts[name] += 1
            elif net.lower() in ["vss", "gnd"]: vss_counts[name] += 1
            else: net_to_devices[net].append(name)

    device_connections = defaultdict(int)
    for net, dev_list in net_to_devices.items():
        if len(dev_list) > 1:
            for d in dev_list:
                device_connections[d] += (len(dev_list) - 1)

    # =========================================================
    # --- MULTI-ROW PLACEMENT (by connection rank) ---
    # =========================================================
    # Rank 0: PMOS, VDD-connected resistors
    # Rank 1: NMOS (non-VSS source), general resistors
    # Rank 2: NMOS (VSS source), VSS-connected resistors
    # Rank 3: Capacitors (MIM, large devices at bottom)

    def _dev_terminals(dev):
        """Return all terminal net names for a device."""
        nodes = dev.get("nodes", {})
        return [n.lower() for n in nodes.values() if n != "-"]

    def _dev_has_net(dev, net_name):
        """Check if device connects to a specific net (case-insensitive)."""
        return net_name.lower() in _dev_terminals(dev)

    def _dev_source_net(dev):
        """Return the source net of a MOSFET device."""
        nodes = dev.get("nodes", {})
        return nodes.get("source", "").lower()

    def _dev_rank(dev):
        model = dev.get("model", "").lower()
        dev_name = dev.get("name", "").upper()

        # --- Capacitors (XC) ---
        if dev_name.startswith("XC") or model.startswith("cap"):
            # Large devices — place at bottom row
            return 3

        # --- Resistors (XR) ---
        if dev_name.startswith("XR") or model.startswith("rm") or model.startswith("r"):
            # Place near their strongest supply connection
            if _dev_has_net(dev, "vdd") or _dev_has_net(dev, "vpwr"):
                return 0  # with PMOS row
            if _dev_has_net(dev, "vss") or _dev_has_net(dev, "gnd"):
                return 2  # with NMOS row
            return 1  # middle row

        # --- MOSFETs (M / XM) ---
        src = _dev_source_net(dev)
        if "p" in model[:2]:
            return 0  # PMOS row
        if src in ("vss", "gnd"):
            return 2  # NMOS row
        return 1  # NMOS with internal source

    rows = defaultdict(list)
    for dev in devices:
        rows[_dev_rank(dev)].append(dev)

    # Sort ranks ascending
    sorted_ranks = sorted(rows.keys())

    # --- UKURAN CELL PER DEVICE ---
    def cell_width(dev):
        params = dev.get("parameters", {})
        dev_name = dev.get("name", "").upper()
        model = dev.get("model", "").lower()

        # Capacitor: width from c_width or w parameter
        if dev_name.startswith("XC") or model.startswith("cap"):
            cw = parse_micrometer(params.get("c_width", params.get("w", "10u")))
            cl = parse_micrometer(params.get("c_length", params.get("l", "10u")))
            return max(cl + 4.0, 6.0)  # capacitor oriented: length = horizontal

        # Resistor: length = horizontal span
        if dev_name.startswith("XR") or model.startswith("rm"):
            rl = parse_micrometer(params.get("r_length", params.get("l", "10u")))
            return max(rl + 4.0, 6.0)

        # MOSFET
        l = parse_micrometer(params.get("l", "0u"))
        ng_raw = params.get("nf", "1")
        ng = int(parse_micrometer(ng_raw)) if ng_raw not in ("-", "", None) else 1
        return max(((l + 1.65) * ng) + (4 * (l + 1.65)), 3.0)

    def cell_height(dev):
        params = dev.get("parameters", {})
        dev_name = dev.get("name", "").upper()
        model = dev.get("model", "").lower()

        # Capacitor: height from c_length or l parameter
        if dev_name.startswith("XC") or model.startswith("cap"):
            cl = parse_micrometer(params.get("c_length", params.get("l", "10u")))
            return max(cl + 4.0, 6.0)

        # Resistor: height = width of resistor strip
        if dev_name.startswith("XR") or model.startswith("rm"):
            rw = parse_micrometer(params.get("r_width", params.get("w", "2u")))
            return max(rw + 4.0, 4.0)

        # MOSFET
        w = parse_micrometer(params.get("w", "0u"))
        return max(w + (4*w), 3.0)

    # --- Connectivity ordering within each row ---
    # Build cross-row connection graph
    all_names = {d["name"] for devlist in rows.values() for d in devlist}
    row_of = {}
    for rank, devlist in rows.items():
        for d in devlist:
            row_of[d["name"]] = rank

    # For each row, determine ideal X based on connections to adjacent rows
    device_ideal_x = {}
    for rank in sorted_ranks:
        devlist = rows[rank]
        # Find which rows are adjacent (connected nets)
        connected_ranks = set()
        for net, dev_names in net_to_devices.items():
            devs_in_this = [n for n in dev_names if n in {d["name"] for d in devlist}]
            if devs_in_this:
                for dn in dev_names:
                    if dn in row_of and row_of[dn] != rank:
                        connected_ranks.add(row_of[dn])

        if not devlist:
            continue

        # Place this row with center-alignment and connectivity ordering
        # Sort by connection score (higher = more connected)
        for d in devlist:
            d["_conn_score"] = device_connections.get(d["name"], 0)
        devlist.sort(key=lambda d: -d["_conn_score"])

    # Calculate row widths and max width
    row_widths = {rank: sum(cell_width(d) for d in devlist)
                  for rank, devlist in rows.items()}
    max_row_w = max(row_widths.values()) if row_widths else 0.0

    # Calculate row heights and cumulative Y positions
    row_heights = {rank: max((cell_height(d) for d in devlist), default=3.0)
                   for rank, devlist in rows.items()}

    # --- ASSIGN KOORDINAT ---
    # Rows stacked from Y=0 upward, centered
    def place_row(row_list, y_base, total_w):
        offset_x = (max_row_w - total_w) / 2.0
        x_cursor = offset_x
        for dev in row_list:
            cw = cell_width(dev)
            dev["position"] = {
                "x_um": f"{x_cursor}u",
                "y_um": f"{y_base}u"
            }
            x_cursor += cw

    total_height = sum(row_heights[r] for r in sorted_ranks)
    y_cursor = total_height  # start from top
    for rank in sorted_ranks:
        y_cursor -= row_heights[rank]
        devlist = rows[rank]
        place_row(devlist, y_cursor, row_widths[rank])
        


def matrix_port_init(config):
    port_matrix = {}
    arah_mata_angin = ["N", "S", "E", "W"]
    
    for comp in config.get('components', []):
        if comp['type'] == 'device':
            nama_device = comp['name']
            port_matrix[nama_device] = {}
            
            # Ambil terminal yang terhubung saja
            for terminal, net in comp.get('nodes', {}).items():
                if net != "-":  # Pastikan pin ini memang dipakai
                    port_matrix[nama_device][terminal] = {}
                    
                    # Isi dengan nilai default 0.0 untuk semua arah
                    for arah in arah_mata_angin:
                        port_matrix[nama_device][terminal][arah] = {
                            "param": port.Port,  
                            "layer": 0
                        }
                        
    return port_matrix

# ══════════════════════════════════════════════════════════════════════
#  Constraint extraction  →  DesignContext
#  (§11 parser responsibilities, §21 analog matching, §57 clusters)
#
#  This section *adds* to the parser above; the original ``config`` dict
#  and its row/position assignment are untouched so every existing caller
#  keeps working.
# ══════════════════════════════════════════════════════════════════════

_POWER_NAMES = {"vdd", "vpwr", "vcc", "vddio", "vdda", "avdd"}
_GROUND_NAMES = {"vss", "gnd", "vgnd", "vssio", "vssa", "agnd", "0"}


def _device_kind(model, name=""):
    m = (model or "").lower()
    n = (name or "").upper()
    if "pfet" in m or "pmos" in m:
        return "pmos"
    if "nfet" in m or "nmos" in m:
        return "nmos"
    if n.startswith("XC") or "mimcap" in m or "cap" in m:
        return "cap"
    if n.startswith("XR") or "res" in m or m.startswith("rm") or "poly" in m:
        return "res"
    return "other"


def _num(val, default=None):
    """'4u' -> 4.0, '1e-6' -> 1e-6 (already um-normalised by caller)."""
    if val in (None, "-", ""):
        return default
    s = str(val).strip().lower()
    mult = 1.0
    for suf, f in (("u", 1.0), ("n", 1e-3), ("p", 1e-6), ("m", 1e3)):
        if s.endswith(suf):
            try:
                return float(s[:-1]) * f
            except ValueError:
                return default
    try:
        return float(s) * mult
    except ValueError:
        return default


def build_design_context(config, pdk=None, name=None):
    """Turn a parsed netlist ``config`` into a DesignContext (§11).

    Extracts, in addition to the plain device/net lists:
      * power / ground nets
      * differential pairs   (same type, shared source, matched geometry)
      * current mirrors      (shared gate, one device diode-connected)
      * generic matched sets (identical model + geometry on a shared gate)
      * critical / sensitive nets
      * placement clusters

    Nothing here invents geometry; it only reads what the netlist states.
    """
    from mbg.design_context import (
        DesignContext, Device, Net, MatchingGroup, SymmetryConstraint,
    )

    subckt = next((c for c in config.get("components", [])
                   if c.get("type") == "subcircuit"), None)
    ctx = DesignContext(name=name or (subckt or {}).get("subcir", "top"))
    ctx.pdk = pdk
    if pdk is not None:
        from mbg.pdk_rules import get_rules
        ctx.rules = get_rules(pdk)
    if subckt:
        ctx.top_ports = list(subckt.get("port", []))

    # ── devices ─────────────────────────────────────────────────────
    for comp in config.get("components", []):
        if comp.get("type") != "device":
            continue
        p = comp.get("parameters", {}) or {}
        kind = _device_kind(comp.get("model"), comp.get("name"))
        nf = int(_num(p.get("nf"), 1) or 1)
        m = int(_num(p.get("m"), 1) or 1)
        w_total = _num(p.get("w") or p.get("r_width") or p.get("c_width"))
        l_val = _num(p.get("l") or p.get("r_length") or p.get("c_length"))
        dev = Device(
            name=comp["name"],
            model=comp.get("model", ""),
            kind=kind,
            terminals={t: n for t, n in (comp.get("nodes") or {}).items() if n != "-"},
            width=w_total,
            length=l_val,
            fingers=max(1, nf),
            multipliers=max(1, m),
            params=dict(p),
        )
        # SPICE W is the TOTAL device width; glayout wants per-finger width.
        if dev.is_mos and w_total:
            dev.finger_width = w_total / float(max(1, nf) * max(1, m))
        else:
            dev.finger_width = w_total
        ctx.add_device(dev)

    # ── nets ────────────────────────────────────────────────────────
    for dev in ctx.devices.values():
        for term, net_name in dev.terminals.items():
            net = ctx.nets.get(net_name)
            if net is None:
                low = net_name.lower()
                net = Net(name=net_name,
                          is_power=low in _POWER_NAMES,
                          is_ground=low in _GROUND_NAMES)
                ctx.add_net(net)
            net.terminals.append((dev.name, term))

    for net in ctx.nets.values():
        if net.is_power:
            ctx.power_nets.add(net.name)
            net.weight = 1.5
        elif net.is_ground:
            ctx.ground_nets.add(net.name)
            net.weight = 1.5

    # ── deep n-well isolation ───────────────────────────────────────
    # GF180MCU has no separate DNW transistor model, so isolation cannot be
    # requested by model name. It is visible in the connectivity instead: an
    # NMOS whose bulk sits on something other than the global ground can only
    # be built with a deep n-well, and that is exactly the case where someone
    # is using the body effect on purpose.
    ground_like = {g.lower() for g in ctx.ground_nets} | {"0", "gnd", "vss"}
    for dev in ctx.devices.values():
        if dev.kind != "nmos":
            continue
        body = (dev.terminals.get("body") or "").lower()
        if body and body not in ground_like:
            dev.needs_dnwell = True
            ctx.deep_nwell_flags[dev.name] = True

    # ── analog structure recognition ────────────────────────────────
    def _geom_key(d):
        return (d.kind, d.model.lower(), d.width, d.length, d.fingers, d.multipliers)

    mos = [d for d in ctx.devices.values() if d.is_mos]

    # differential pairs: same type + geometry, shared SOURCE, distinct gates
    by_source = {}
    for d in mos:
        by_source.setdefault(d.terminals.get("source"), []).append(d)
    pair_id = 0
    paired = set()
    for src, devs in by_source.items():
        if not src or src.lower() in _POWER_NAMES | _GROUND_NAMES:
            continue                     # a shared rail is not a tail node
        for i in range(len(devs)):
            for j in range(i + 1, len(devs)):
                a, b = devs[i], devs[j]
                if a.name in paired or b.name in paired:
                    continue
                if _geom_key(a) != _geom_key(b):
                    continue
                if a.terminals.get("gate") == b.terminals.get("gate"):
                    continue
                if a.terminals.get("drain") == b.terminals.get("drain"):
                    continue
                pair_id += 1
                gname = f"diffpair_{pair_id}"
                ctx.matching_groups[gname] = MatchingGroup(
                    gname, "diff_pair", [a.name, b.name], symmetric=True)
                ctx.symmetry_constraints.append(
                    SymmetryConstraint(gname, a.name, b.name, "vertical"))
                ctx.clusters[gname] = [a.name, b.name]
                ctx.differential_pairs.append(
                    (a.terminals.get("gate"), b.terminals.get("gate")))
                paired.update({a.name, b.name})
                # gate nets of a diff pair are the sensitive inputs
                for g in (a.terminals.get("gate"), b.terminals.get("gate")):
                    if g and not ctx.is_power_or_ground(g):
                        ctx.sensitive_nets.add(g)
                        ctx.nets[g].is_sensitive = True
                        ctx.nets[g].weight = max(ctx.nets[g].weight, 2.0)

    # current mirrors: shared gate net where one device is diode-connected
    by_gate = {}
    for d in mos:
        by_gate.setdefault(d.terminals.get("gate"), []).append(d)
    mir_id = 0
    for gate, devs in by_gate.items():
        if not gate or len(devs) < 2:
            continue
        diode = [d for d in devs if d.terminals.get("drain") == gate]
        if not diode:
            continue
        same_kind = [d for d in devs if d.kind == diode[0].kind]
        if len(same_kind) < 2:
            continue
        mir_id += 1
        gname = f"mirror_{mir_id}"
        names = [d.name for d in same_kind]
        ctx.matching_groups[gname] = MatchingGroup(
            gname, "current_mirror", names,
            symmetric=len({_geom_key(d) for d in same_kind}) == 1)
        ctx.clusters[gname] = names
        ctx.critical_nets.add(gate)
        ctx.nets[gate].is_critical = True
        ctx.nets[gate].weight = max(ctx.nets[gate].weight, 2.0)

    # generic matched sets: identical devices sharing a gate, not yet grouped
    grouped = {n for g in ctx.matching_groups.values() for n in g.devices}
    gen_id = 0
    for gate, devs in by_gate.items():
        cand = [d for d in devs if d.name not in grouped]
        if len(cand) < 2:
            continue
        buckets = {}
        for d in cand:
            buckets.setdefault(_geom_key(d), []).append(d)
        for key, group in buckets.items():
            if len(group) < 2:
                continue
            gen_id += 1
            gname = f"matched_{gen_id}"
            names = [d.name for d in group]
            ctx.matching_groups[gname] = MatchingGroup(gname, "generic", names, True)
            ctx.clusters[gname] = names
            grouped.update(names)

    # critical nets: every internal (non-rail) net with fan-out >= 3
    for net in ctx.nets.values():
        if ctx.is_power_or_ground(net.name):
            continue
        if net.degree >= 3:
            ctx.critical_nets.add(net.name)
            net.is_critical = True

    return ctx
