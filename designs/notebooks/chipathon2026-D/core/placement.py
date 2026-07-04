from collections import defaultdict
from gdsfactory import Component
from gdsfactory import port
import gdsfactory as gf
from glayout import nmos, pmos
from core.spice_parser import matrix_port_init
from core.utils import clean_param


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
            ng = int(clean_param(params.get("ng"))) if params.get("ng") != "-" else 1

            device = None

            if "pfet" in model or "pmos" in model:
                device = pmos(
                    pdk,
                    width=w,
                    length=l,
                    fingers=ng,
                    multipliers=m,
                    with_substrate_tap=False,
                    with_tie=True
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
                    width=w,
                    length=l,
                    fingers=ng,
                    multipliers=m,
                    with_substrate_tap=False,
                    with_dnwell=False,
                    with_tie=True
                )
                device_ref = top_level << device
                device_ref.name = dev_name
                x_coord = clean_param(position.get("x_um", "0u"))
                y_coord = clean_param(position.get("y_um", "0u"))

                device_ref.movex(x_coord)
                device_ref.movey(y_coord)
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
