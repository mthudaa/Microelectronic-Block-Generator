"""
@Owner: Huda (Lead Analog / Mixed-Signal Designer)
@Role: Analog Layout Strategist
@Responsibility: Parsing SPICE netlists into a data structure understood by the layout generator.
"""
import re
import json
from collections import defaultdict
from gdsfactory import port

def parse_netlist_with_pdk(file_content, manual_pdk="Tidak Terdeteksi", mode="analog"):
    parsed_components = []
    lines = file_content.strip().split('\n')
    
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
        
        params = {"w": "-", "l": "-", "m": "-", "ng": "-"}
        param_dict = None
        model_name = "-"
        nodes_dict = {}
        
        # MOSFET
        if device_type == 'M': 
            nodes_dict = {
                "drain": parts[1] if len(parts) > 1 else "-",
                "gate": parts[2] if len(parts) > 2 else "-",
                "source": parts[3] if len(parts) > 3 else "-",
                "body": parts[4] if len(parts) > 4 else "-"
            }
            if len(parts) > 5:
                model_name = parts[5]
            remaining = " ".join(parts[6:])
            
        # R, C, L, dll
        elif device_type in ['R', 'C', 'L', 'V', 'I', 'D']: 
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

            if device_type == 'M':
                param_dict = { "w": params['w'], "l": params['l'], "m": params['m'], "ng": params['ng'] }
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
    # --- LOGIKA MATRIKS: PMOS ATAS, NMOS BAWAH (ALIGN-inspired) ---
    # =========================================================
    pmos_row = []
    nmos_row = []

    for dev in devices:
        if 'p' in dev.get('model', '').lower()[:2]:
            pmos_row.append(dev)
        else:
            nmos_row.append(dev)

    def get_conn_score(d):
        return device_connections[d["name"]]

    pmos_row.sort(key=get_conn_score, reverse=True)

    # --- UKURAN CELL PER DEVICE ---
    # tinggi = W + 4*W + 7, lebar = ((L+1.65)*finger) + 8*(L+1.65)
    def cell_width(dev):
        l = parse_micrometer(dev["parameters"].get("l", "0u"))
        ng_raw = dev["parameters"].get("ng", "1")
        ng = int(parse_micrometer(ng_raw)) if ng_raw not in ("-", "", None) else 1
        return max(((l + 1.65) * ng) + (8 * (l + 1.65)), 3.0)

    def cell_height(dev):
        w = parse_micrometer(dev["parameters"].get("w", "0u"))
        return max(w + (4*w) + 7.0, 3.0)

    # --- ALIGN-inspired: connectivity-driven NMOS ordering ---
    # Hitung bobot koneksi PMOS-NMOS per pasangan device
    pmos_nmos_edges = defaultdict(float)
    for net, dev_list in net_to_devices.items():
        p_devs = [d for d in dev_list if d in pmos_row]
        n_devs = [d for d in dev_list if d in nmos_row]
        for pd in p_devs:
            for nd in n_devs:
                pmos_nmos_edges[(pd["name"], nd["name"])] += 1.0

    # Place PMOS dulu, catat posisi X per device
    pmos_x_map = {}
    x_cursor = 0.0
    for dev in pmos_row:
        pmos_x_map[dev["name"]] = x_cursor + cell_width(dev) / 2.0  # center X
        x_cursor += cell_width(dev)

    # Urutkan NMOS berdasarkan rata-rata X PMOS yang terhubung
    def nmos_ideal_x(dev):
        total_w = 0.0
        total_x = 0.0
        for pd_name, nd_name, w in [(k[0], k[1], v) for k, v in pmos_nmos_edges.items()]:
            if nd_name == dev["name"] and pd_name in pmos_x_map:
                total_w += w
                total_x += pmos_x_map[pd_name] * w
        if total_w > 0:
            return total_x / total_w  # weighted average X
        return float('inf')  # no connection -> place at end

    nmos_row.sort(key=nmos_ideal_x)

    # Hitung total lebar tiap baris
    pmos_total_w = sum(cell_width(d) for d in pmos_row) if pmos_row else 0.0
    nmos_total_w = sum(cell_width(d) for d in nmos_row) if nmos_row else 0.0
    max_row_w = max(pmos_total_w, nmos_total_w)

    pmos_row_h = max((cell_height(d) for d in pmos_row), default=3.0)
    nmos_row_h = max((cell_height(d) for d in nmos_row), default=3.0)

    # --- ASSIGN KOORDINAT (center alignment) ---
    # PMOS row di atas (Y = nmos_row_h), NMOS row di bawah (Y = 0)
    def place_row(row_list, y_base, total_w):
        offset_x = (max_row_w - total_w) / 2.0  # center alignment
        x_cursor = offset_x
        for dev in row_list:
            cw = cell_width(dev)
            dev["position"] = {
                "x_um": f"{x_cursor}u",
                "y_um": f"{y_base}u"
            }
            x_cursor += cw

    place_row(nmos_row, 0.0, nmos_total_w)
    place_row(pmos_row, nmos_row_h, pmos_total_w)
            
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