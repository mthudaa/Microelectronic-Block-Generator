"""
@Owner: Huda (Lead Analog / Mixed-Signal Designer)
@Role: Analog Layout Strategist
@Responsibility: Component placement logic for GDSII layout to meet analog design principles (matching, symmetry).
"""
from collections import defaultdict
from gdsfactory import Component
from gdsfactory import port
import gdsfactory as gf
from glayout import nmos, pmos, resistor, mimcap, mimcap_array, multiplier
from mbg.spice_parser import matrix_port_init
from mbg.utils import clean_param


def placement(config, pdk):
    top_level = Component(name=config["components"][0]["subcir"])
    port_map = matrix_port_init(config)
    for comp in config["components"]:
        if comp["type"] == "device":
            dev_name = comp["name"]
            model = comp["model"].lower()
            params = comp["parameters"]
            position = comp.get("position", {"x_um": "0u", "y_um": "0u"})

            w = clean_param(params.get("w"))
            l = clean_param(params.get("l"))
            m = int(clean_param(params.get("m"))) if params.get("m") != "-" else 1
            nf = int(clean_param(params.get("nf"))) if params.get("nf") != "-" else 1

            # SPICE W is the TOTAL device width; gLayout's `width` argument is
            # PER FINGER ("fingers: introduces additional fingers ... of
            # width=width").  Passing the SPICE W straight through built every
            # multi-finger device nf*m times too wide — which is what LVS was
            # reporting as "w circuit1: 1.6e-05 circuit2: 4e-06".
            w_finger = w / float(max(1, nf) * max(1, m)) if w else w

            device = None

            if "pfet" in model or "pmos" in model:
                device = pmos(
                    pdk,
                    width=w_finger,
                    length=l,
                    fingers=nf,
                    multipliers=m,
                    with_substrate_tap=False,
                    with_tie=True,
                    with_dummy=False
                )
                device_ref = top_level << device
                device_ref.name = dev_name
                x_coord = clean_param(position.get("x_um", "0u"))
                y_coord = clean_param(position.get("y_um", "0u"))

                device_ref.movex(x_coord)
                device_ref.movey(y_coord)

                daftar_terminal = ["drain", "gate", "source"]
                arah_mata_angin = ["N", "E", "S", "W"]

                for terminal in daftar_terminal:
                    for arah in arah_mata_angin:
                        nama_port = f"multiplier_0_{terminal}_{arah}"
                        if nama_port in device_ref.ports:
                            port_map[dev_name][terminal][arah]["param"] = device_ref.ports[nama_port]
                            if device_ref.ports[nama_port].layer == "34/0":
                                port_map[dev_name][terminal][arah]["layer"] = 1
                            elif device_ref.ports[nama_port].layer == "36/0":
                                port_map[dev_name][terminal][arah]["layer"] = 2
                            elif device_ref.ports[nama_port].layer == "38/0":
                                port_map[dev_name][terminal][arah]["layer"] = 3
                            elif device_ref.ports[nama_port].layer == "40/0":
                                port_map[dev_name][terminal][arah]["layer"] = 4
                            elif device_ref.ports[nama_port].layer == "42/0":
                                port_map[dev_name][terminal][arah]["layer"] = 5

                arah_mata_angin_tap = ["W"]
                for arah in arah_mata_angin_tap:
                    nama_tie = f"tie_{arah}_top_met_{arah}"
                    if nama_tie in device_ref.ports:
                        port_map[dev_name]["body"][arah]["param"] = device_ref.ports[nama_tie]
                        if device_ref.ports[nama_tie].layer == "34/0":
                            port_map[dev_name]["body"][arah]["layer"] = 1
                        elif device_ref.ports[nama_tie].layer == "36/0":
                            port_map[dev_name]["body"][arah]["layer"] = 2
                        elif device_ref.ports[nama_tie].layer == "38/0":
                            port_map[dev_name]["body"][arah]["layer"] = 3
                        elif device_ref.ports[nama_tie].layer == "40/0":
                            port_map[dev_name]["body"][arah]["layer"] = 4
                        elif device_ref.ports[nama_tie].layer == "42/0":
                            port_map[dev_name]["body"][arah]["layer"] = 5

                print(f"[LAYOUT] Sukses menempatkan {dev_name} ({model}) di posisi X: {x_coord}u, Y: {y_coord}u")

            elif "nfet" in model or "nmos" in model:
                device = nmos(
                    pdk,
                    width=w_finger,
                    length=l,
                    fingers=nf,
                    multipliers=m,
                    with_substrate_tap=False,
                    with_dnwell=False,
                    with_tie=True,
                    with_dummy=False
                )
                device_ref = top_level << device
                device_ref.name = dev_name
                x_coord = clean_param(position.get("x_um", "0u"))
                y_coord = clean_param(position.get("y_um", "0u"))

                device_ref.movex(x_coord)
                device_ref.movey(y_coord)
                if "tie_W_top_met_W" in device_ref.ports:
                    print(device_ref.ports["tie_W_top_met_W"])

                daftar_terminal = ["drain", "gate", "source", "body"]
                arah_mata_angin = ["N", "E", "S", "W"]

                for terminal in daftar_terminal:
                    for arah in arah_mata_angin:
                        nama_port = f"multiplier_0_{terminal}_{arah}"
                        if nama_port in device_ref.ports:
                            port_map[dev_name][terminal][arah]["param"] = device_ref.ports[nama_port]
                            if device_ref.ports[nama_port].layer == "34/0":
                                port_map[dev_name][terminal][arah]["layer"] = 1
                            elif device_ref.ports[nama_port].layer == "36/0":
                                port_map[dev_name][terminal][arah]["layer"] = 2
                            elif device_ref.ports[nama_port].layer == "38/0":
                                port_map[dev_name][terminal][arah]["layer"] = 3
                            elif device_ref.ports[nama_port].layer == "40/0":
                                port_map[dev_name][terminal][arah]["layer"] = 4
                            elif device_ref.ports[nama_port].layer == "42/0":
                                port_map[dev_name][terminal][arah]["layer"] = 5

                arah_mata_angin_tap = ["W"]
                for arah in arah_mata_angin_tap:
                    nama_tie = f"tie_{arah}_top_met_{arah}"
                    if nama_tie in device_ref.ports:
                        port_map[dev_name]["body"][arah]["param"] = device_ref.ports[nama_tie]
                        if device_ref.ports[nama_tie].layer == "34/0":
                            port_map[dev_name]["body"][arah]["layer"] = 1
                        elif device_ref.ports[nama_tie].layer == "36/0":
                            port_map[dev_name]["body"][arah]["layer"] = 2
                        elif device_ref.ports[nama_tie].layer == "38/0":
                            port_map[dev_name]["body"][arah]["layer"] = 3
                        elif device_ref.ports[nama_tie].layer == "40/0":
                            port_map[dev_name]["body"][arah]["layer"] = 4
                        elif device_ref.ports[nama_tie].layer == "42/0":
                            port_map[dev_name]["body"][arah]["layer"] = 5

                print(f"[LAYOUT] Sukses menempatkan {dev_name} ({model}) di posisi X: {x_coord}u, Y: {y_coord}u")

            elif "res" in model or "rpoly" in model or model in ("ppolyf_u", "npolyf_u", "nwell", "rm1", "rm2", "rm3"):
                rw = clean_param(params.get("r_width", params.get("w", "5u")))
                rl = clean_param(params.get("r_length", params.get("l", "1u")))
                device = resistor(pdk, width=rw, length=rl, multipliers=m,
                                  with_substrate_tap=False, with_tie=False)
                device_ref = top_level << device
                device_ref.name = dev_name
                x_coord = clean_param(position.get("x_um", "0u"))
                y_coord = clean_param(position.get("y_um", "0u"))
                device_ref.movex(x_coord)
                device_ref.movey(y_coord)
                # Map spice_parser "p"/"n" → device terminals "1"/"2"
                port_map[dev_name] = {}
                for spice_term, dev_term in [("p", "1"), ("n", "2")]:
                    port_map[dev_name][spice_term] = {}
                    for direc in ["N", "E", "S", "W"]:
                        pname = f"multiplier_0_{dev_term}_{direc}"
                        if pname in device_ref.ports:
                            port_map[dev_name][spice_term][direc] = {"param": device_ref.ports[pname], "layer": 2}
                        else:
                            port_map[dev_name][spice_term][direc] = {"param": gf.port.Port, "layer": 0}
                print(f"[LAYOUT] Resistor {dev_name} @ ({x_coord},{y_coord}) W={rw} L={rl}")

            elif "mimcap" in model or "cap_mim" in model:
                cw = clean_param(params.get("c_width", params.get("w", "5u")))
                cl = clean_param(params.get("c_length", params.get("l", "5u")))
                size = (max(cw, cl), max(cw, cl))
                device = mimcap(pdk, size=size)
                device_ref = top_level << device
                device_ref.name = dev_name
                x_coord = clean_param(position.get("x_um", "0u"))
                y_coord = clean_param(position.get("y_um", "0u"))
                device_ref.movex(x_coord)
                device_ref.movey(y_coord)
                # Map spice_parser "p"/"n" to MIMCAP's two terminals
                port_map[dev_name] = {"p": {}, "n": {}}
                cap_ports = sorted([p for p in device_ref.ports if not p.startswith("cap_")])
                for spice_term, dev_pname in zip(["p", "n"], cap_ports[:2]):
                    for direc in ["N", "E", "S", "W"]:
                        # MIMCAP ports are typically single-direction; fill all with same port
                        port_map[dev_name][spice_term][direc] = {
                            "param": device_ref.ports[dev_pname],
                            "layer": 2
                        }
                # Fallback: if no named ports found, try all ports
                if not cap_ports:
                    all_ps = list(device_ref.ports)
                    for i, spice_term in enumerate(["p", "n"]):
                        if i < len(all_ps):
                            for direc in ["N", "E", "S", "W"]:
                                port_map[dev_name][spice_term][direc] = {
                                    "param": device_ref.ports[all_ps[i]],
                                    "layer": 2
                                }
                print(f"[LAYOUT] MIMCAP {dev_name} @ ({x_coord},{y_coord}) size={size}")

            else:
                print(f"[WARNING] Model {model} untuk device {dev_name} belum terpetakan di generator.")

    return top_level, port_map


def petakan_koneksi_net(config):
    koneksi_net = defaultdict(list)

    for comp in config.get('components', []):
        if comp['type'] == 'device':
            nama_device = comp['name']

            for terminal, nama_net in comp.get('nodes', {}).items():
                if nama_net != "-":
                    koneksi_net[nama_net].append({
                        'device': nama_device,
                        'terminal': terminal
                    })

    return dict(koneksi_net)


def _get_all_ports(port_map, dev_name, terminal):
    results = []
    for arah in ["N", "S", "E", "W"]:
        try:
            data = port_map[dev_name][terminal][arah]
            if data["param"] != gf.port.Port and data["param"] is not None:
                results.append((data["param"], data["layer"]))
        except (KeyError, TypeError):
            continue
    return results


def _get_first_port(port_map, dev_name, terminal):
    for arah in ["N", "S", "E", "W"]:
        try:
            data = port_map[dev_name][terminal][arah]
            if data["param"] != gf.port.Port and data["param"] is not None:
                return (data["param"], data["layer"])
        except (KeyError, TypeError):
            continue
    return None


def buat_daftar_koneksi(peta_koneksi, port_map):
    daftar_koneksi = []

    for nama_net, list_device_terhubung in peta_koneksi.items():
        koordinat_pin_net_ini = []

        for koneksi in list_device_terhubung:
            dev_name = koneksi['device']
            terminal = koneksi['terminal']

            all_ports = _get_all_ports(port_map, dev_name, terminal)
            if all_ports:
                koordinat_pin_net_ini.append(all_ports)
            else:
                print(f"[WARNING] Port untuk {dev_name}.{terminal} tidak ditemukan di port_map!")

        if len(koordinat_pin_net_ini) >= 2:
            daftar_koneksi.append((nama_net, koordinat_pin_net_ini))

    return daftar_koneksi


def manual_placement(devices, pdk, top_cell_name="top"):
    """AI-agent-friendly manual placement.
    
    Raises:
        ValueError: If devices list is empty or missing required keys.
        TypeError: If pdk is not a MappedPDK object.
    

    Creates devices at explicit (x, y) coordinates and returns the
    port_map needed by the auto-router. Does NOT require a pre-parsed
    SPICE config — the AI agent specifies everything directly.

    Args:
        devices: List of dicts, each with:
            name: str                  — Device instance name (e.g. "XM1")
            model: str                 — "nfet_03v3" or "pfet_03v3"
            width: float               — Width in um
            length: float              — Length in um
            fingers: int               — Number of gate fingers (nf)
            multipliers: int           — Number of multiplier copies
            x: float                   — X placement coordinate (um)
            y: float                   — Y placement coordinate (um)
        pdk: MappedPDK object          — from glayout (gf180 / sky130)
        top_cell_name: str             — Top-level cell name

    Returns:
        (top_level, port_map, device_map)
        top_level: gdsfactory.Component with all devices placed
        port_map:  dict[dev_name][terminal][direction] = {"param": Port, "layer": int}
        device_map: dict[dev_name] = {"width":..., "length":..., "model":...,
                                       "x":..., "y":...} for AI reference
    """
    if not devices:
        raise ValueError("devices list is empty — provide at least one device dict")
    required = {"name", "model", "width", "length", "x", "y"}
    for i, dev in enumerate(devices):
        missing = required - set(dev.keys())
        if missing:
            raise KeyError(f"Device[{i}] ({dev.get('name', '?')}) missing keys: {missing}")

    top_level = Component(name=top_cell_name)
    port_map = {}
    device_map = {}

    for dev in devices:
        name = dev["name"]
        model = dev["model"].lower()
        w = float(dev["width"])
        l = float(dev["length"])
        nf = int(dev.get("fingers", 1))
        m = int(dev.get("multipliers", 1))
        x = float(dev["x"])
        y = float(dev["y"])

        is_mos = "pfet" in model or "pmos" in model or "nfet" in model or "nmos" in model
        is_res = any(x in model for x in ["res", "rpoly", "rm1", "rm2", "rm3", "nwell", "ppolyf", "npolyf", "nplus", "pplus", "tm"])
        is_cap = any(x in model for x in ["mimcap", "cap_", "moscap"])

        try:
            if is_mos:
                is_pmos = "pfet" in model or "pmos" in model
                gen_fn = pmos if is_pmos else nmos
                # per-finger width, see note in placement() above
                w_finger = w / float(max(1, nf) * max(1, m))
                kwargs = dict(pdk=pdk, width=w_finger, length=l, fingers=nf, multipliers=m,
                              with_substrate_tap=False, with_tie=True, with_dummy=False)
                if not is_pmos:
                    kwargs["with_dnwell"] = False
                device = gen_fn(**kwargs)
            elif is_res:
                device = resistor(pdk, width=w, length=l, multipliers=m,
                                  with_substrate_tap=False, with_tie=False)
            elif is_cap:
                size = (max(w, l), max(w, l))
                if m > 1:
                    device = mimcap_array(pdk, rows=1, columns=m, size=size)
                else:
                    device = mimcap(pdk, size=size)
            else:
                print(f"[PLACEMENT] Unknown model {model} for {name}, trying as NMOS")
                device = nmos(pdk, width=w, length=l, fingers=nf, multipliers=m,
                              with_substrate_tap=False, with_dnwell=False,
                              with_tie=True, with_dummy=False)
        except Exception as e:
            print(f"[PLACEMENT] Error creating {name} ({model}): {e}")
            continue

        ref = top_level << device
        ref.name = name
        ref.movex(x)
        ref.movey(y)

        device_map[name] = {"width": w, "length": l, "model": model,
                             "fingers": nf if is_mos else 1,
                             "multipliers": m, "x": x, "y": y}

        # Initialize port_map
        port_map[name] = {}
        if is_mos:
            for term in ["drain", "gate", "source", "body"]:
                port_map[name][term] = {}
                for direc in ["N", "E", "S", "W"]:
                    port_map[name][term][direc] = {"param": gf.port.Port, "layer": 0}
            for term in ["drain", "gate", "source"]:
                for direc in ["N", "E", "S", "W"]:
                    pname = f"multiplier_0_{term}_{direc}"
                    if pname in ref.ports:
                        p = ref.ports[pname]
                        port_map[name][term][direc]["param"] = p
                        port_map[name][term][direc]["layer"] = _layer_num(p.layer)
            for direc in ["W"]:
                pname = f"tie_{direc}_top_met_{direc}"
                if pname in ref.ports:
                    p = ref.ports[pname]
                    port_map[name]["body"][direc]["param"] = p
                    port_map[name]["body"][direc]["layer"] = _layer_num(p.layer)
        elif is_res:
            for term in ["p", "n"]:
                port_map[name][term] = {}
                for direc in ["N", "E", "S", "W"]:
                    port_map[name][term][direc] = {"param": gf.port.Port, "layer": 0}
            for spice_term, dev_term in [("p", "1"), ("n", "2")]:
                for direc in ["N", "E", "S", "W"]:
                    pname = f"multiplier_0_{dev_term}_{direc}"
                    if pname in ref.ports:
                        p = ref.ports[pname]
                        port_map[name][spice_term][direc]["param"] = p
                        port_map[name][spice_term][direc]["layer"] = _layer_num(p.layer)
        elif is_cap:
            port_map[name] = {"p": {}, "n": {}}
            cap_ports = [pn for pn in ref.ports if not pn.startswith("cap_")]
            for spice_term, dev_pname in zip(["p", "n"], cap_ports[:2]):
                for direc in ["N", "E", "S", "W"]:
                    port_map[name][spice_term][direc] = {
                        "param": ref.ports[dev_pname],
                        "layer": _layer_num(ref.ports[dev_pname].layer)
                    }

        print(f"[PLACEMENT] {name} ({model}) @ ({x:.1f}, {y:.1f})")

    return top_level, port_map, device_map


def _layer_num(layer_spec):
    """Convert a gdsfactory layer spec to routing-layer number (1-5)."""
    lyr = layer_spec[0] if isinstance(layer_spec, (tuple, list)) else layer_spec
    lyr = int(lyr)
    if lyr == 34: return 1  # met1
    if lyr == 36: return 2  # met2
    if lyr == 38: return 3
    if lyr == 40: return 4
    if lyr == 42: return 5
    return 0
