"""
@Owner: Huda (Lead Analog / Mixed-Signal Designer)
@Role: Analog Layout Strategist
@Responsibility: Parsing SPICE netlists into a data structure understood by the layout generator.
"""
import re
from collections import defaultdict
from gdsfactory import port

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
                param_dict = { "c_width": params['c_width'], "c_length": params['c_length'] }
            elif device_type_linear_dev == 'XR':
                param_dict = { "r_width": params['r_width'], "r_length": params['r_length'] }
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
    # Rank 0: PMOS (source=VDD)
    # Rank 1: NMOS with source=internal net (not VDD/VSS)
    # Rank 2: NMOS with source=VSS
    # Higher ranks for other source nets (general n-row)

    def _dev_source_net(dev):
        """Return the source net of a device."""
        nodes = dev.get("nodes", {})
        return nodes.get("source", "").lower()

    def _dev_rank(dev):
        model = dev.get("model", "").lower()
        src = _dev_source_net(dev)
        if "p" in model[:2]:
            return 0
        if src in ("vss", "gnd", "vss"):
            return 2
        return 1  # NMOS with non-VSS source

    rows = defaultdict(list)
    for dev in devices:
        rows[_dev_rank(dev)].append(dev)

    # Sort ranks ascending
    sorted_ranks = sorted(rows.keys())

    # --- UKURAN CELL PER DEVICE ---
    def cell_width(dev):
        l = parse_micrometer(dev["parameters"].get("l", "0u"))
        ng_raw = dev["parameters"].get("nf", "1")
        ng = int(parse_micrometer(ng_raw)) if ng_raw not in ("-", "", None) else 1
        return max(((l + 1.65) * ng) + (4 * (l + 1.65)), 3.0)

    def cell_height(dev):
        w = parse_micrometer(dev["parameters"].get("w", "0u"))
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
            
    return final_output

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