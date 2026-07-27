"""
@Owner: Moh. Jabir Mubarok (AI/LLM Integration & Software Architect)
@Role: AI/LLM & Backend Engineer
@Responsibility: End-to-end pipeline (llm_to_gds), prompt engineering, LLM API integration (DeepSeek) for spec-to-netlist conversion, and dataset collection for future LLM fine-tuning.
"""
import os
import urllib.request
import json as _json
import urllib.error

from glayout import gf180, sky130
from glayout import rename_ports_by_orientation
from glayout.util.snap_to_grid import component_snap_to_grid
from glayout.util.port_utils import add_ports_perimeter
from glayout.util.comp_utils import align_comp_to_port
from gdsfactory.components import rectangle

from core.spice_parser import parse_netlist_with_pdk
from core.placement import placement, petakan_koneksi_net, buat_daftar_koneksi, _get_first_port
from core.routing import auto_router, set_pdk
from core.power import add_power_strips
from core.checks import run_drc, run_lvs, run_pex


def _load_api_key():
    """Load DeepSeek API key from env or .env file."""
    key = os.environ.get("DEEPSEEK_API_KEY")
    if key:
        return key
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    if os.path.isfile(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line.startswith("DEEPSEEK_API_KEY="):
                    return line.split("=", 1)[1].strip().strip("\"'")
    return None


def generate_netlist_from_prompt(user_prompt, model="deepseek-v4-flash",
                                 api_key=None,
                                 api_url="https://api.deepseek.com/v1/chat/completions",
                                 llm_feedback=None):
    api_key = api_key or _load_api_key()
    if not api_key:
        raise RuntimeError(
            "DEEPSEEK_API_KEY not set. "
            "Export it or create .env file with DEEPSEEK_API_KEY=sk-..."
        )
    context = """You are an analog IC design expert. Generate ONLY a SPICE subcircuit netlist.
Respond with NOTHING except the netlist -- no explanations, no markdown, no comments.

STRICT RULES:
1. First line MUST be: .lib "/path/to/gf180mcu/libs.tech/ngspice/sm141064.ngspice" typical
2. Second line MUST be: .subckt <name> <ports...>
3. Last line MUST be: .ends
4. ONLY use these models: nfet_03v3 (NMOS) and pfet_03v3 (PMOS).
5. Format EXACTLY: M<name> <drain> <gate> <source> <body> <model> W=<w>u L=<l>u
6. SUPPLY: Use VDD=1.8V. Connect PMOS body to vdd, NMOS body to vss.
7. NO empty lines between devices. NO markdown fences. NO other text.
8. Choose net names that reflect circuit function (e.g., n1, n2 for internal, vin/vout for I/O).
9. Keep W between 1u and 50u. Keep L=1u for analog. Use ng=1 (no multi-finger)."""

    messages = [
        {"role": "system", "content": context},
        {"role": "user", "content": user_prompt}
    ]
    
    if llm_feedback:
        messages.append({
            "role": "user", 
            "content": f"Here is the feedback from the previous simulation:\n{llm_feedback}\n\nPlease revise and output the new corrected SPICE netlist based on this feedback."
        })

    payload = _json.dumps({
        "model": model,
        "messages": messages,
        "temperature": 0.1,
        "max_tokens": 2000,
        "stream": False
    }).encode()

    req = urllib.request.Request(
        api_url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
    )

    max_retries = 3
    for attempt in range(max_retries):
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                raw = resp.read()
                print(f"[LLM] Response: {len(raw)} bytes (attempt {attempt+1}/{max_retries})")
                result = _json.loads(raw)
                if "choices" not in result:
                    print(f"[LLM] Unexpected: {str(result)[:200]}")
                    if attempt < max_retries - 1:
                        continue
                    return None
                netlist = result["choices"][0]["message"]["content"].strip()
                lines = []
                for line in netlist.split('\n'):
                    line = line.strip()
                    if line and not line.startswith('*') and not line.startswith('//') and not line.startswith('#'):
                        if not line.startswith('```'):
                            lines.append(line)
                cleaned = '\n'.join(lines)
                # Validate: must have .subckt and at least one device
                if '.subckt' not in cleaned:
                    print(f"[LLM] No .subckt found — retrying ({attempt+1}/{max_retries})")
                    continue
                try:
                    parsed = parse_netlist_with_pdk(cleaned)
                    if not parsed.get("components"):
                        print(f"[LLM] Parsed netlist has no devices — retrying")
                        continue
                    print(f"[LLM] Validated: {len(parsed['components'])} devices, PDK={parsed['metadata']['pdk']}")
                except Exception as parse_err:
                    print(f"[LLM] Parse failed: {parse_err} — retrying ({attempt+1}/{max_retries})")
                    continue
                print(f"[LLM] Cleaned ({len(lines)} lines):\n{cleaned[:400]}")
                return cleaned
        except urllib.error.HTTPError as e:
            body = e.read().decode()[:500] if e.fp else ""
            print(f"[LLM] HTTP {e.code}: {e.reason}\n{body}")
            if attempt < max_retries - 1:
                print(f"[LLM] Retrying ({attempt+1}/{max_retries})...")
                continue
            return None
        except (urllib.error.URLError, ConnectionError) as e:
            print(f"[LLM] Network error: {e} — retrying ({attempt+1}/{max_retries})")
            continue
        except Exception as e:
            print(f"[LLM] {type(e).__name__}: {e}")
            if attempt < max_retries - 1:
                continue
            return None
    return None


def spice_to_gds(netlist_input, mode="analog", add_labels=True, run_checks=False, gds_path=None):
    if not netlist_input or not isinstance(netlist_input, str):
        raise ValueError(f"netlist_input must be a non-empty string, got {type(netlist_input).__name__}: {netlist_input!r}")
    if ".subckt" not in netlist_input.lower():
        raise ValueError("netlist_input has no .subckt definition — cannot generate layout")
    config = parse_netlist_with_pdk(netlist_input, mode=mode)
    if not config.get("components"):
        raise ValueError("Parsed netlist has 0 components — check SPICE syntax")

    PDK = config["metadata"]["pdk"]
    print(f"[PIPELINE] PDK: {PDK}")
    if PDK == "gf180":
        pdk = gf180
    elif PDK == "sky130":
        pdk = sky130
    else:
        raise ValueError(f"Unknown PDK: {PDK}")
    pdk.activate()

    set_pdk(pdk)

    top_level, port_map = placement(config, pdk)

    for dev_name in port_map:
        if "body" in port_map[dev_name]:
            for arah in ["N", "S", "E", "W"]:
                if port_map[dev_name]["body"][arah].get("layer", 0) == 0:
                    src = port_map[dev_name].get("source", {}).get(arah, {})
                    if src.get("layer", 0) != 0:
                        port_map[dev_name]["body"][arah] = dict(src)

    top_level, vdd_strip_ports, vss_strip_ports = add_power_strips(top_level, pdk, strip_width=1.0)
    if not vdd_strip_ports:
        print("[WARN] No VDD strip ports created — routing may be incomplete")
    else:
        vport = vdd_strip_ports[0]
        port_map["VDD_STRIP"] = {"power": {}}
        for arah in ["N", "S", "E", "W"]:
            port_map["VDD_STRIP"]["power"][arah] = {"param": vport, "layer": 5}
        print(f"[POWER] VDD strip registered in port_map (port: {vport.name})")
    if not vss_strip_ports:
        print("[WARN] No VSS strip ports created — routing may be incomplete")
    else:
        vport = vss_strip_ports[0]
        port_map["VSS_STRIP"] = {"power": {}}
        for arah in ["N", "S", "E", "W"]:
            port_map["VSS_STRIP"]["power"][arah] = {"param": vport, "layer": 5}
        print(f"[POWER] VSS strip registered in port_map (port: {vport.name})")

    peta_koneksi = petakan_koneksi_net(config)
    vdd_key = next((k for k in peta_koneksi if k.upper() == "VDD"), "VDD")
    vss_key = next((k for k in peta_koneksi if k.upper() in ("VSS", "GND")), "VSS")
    if "VDD_STRIP" in port_map:
        peta_koneksi.setdefault(vdd_key, []).append({"device": "VDD_STRIP", "terminal": "power"})
        print(f"[POWER] VDD net '{vdd_key}': {len(peta_koneksi[vdd_key])} connections")
    if "VSS_STRIP" in port_map:
        peta_koneksi.setdefault(vss_key, []).append({"device": "VSS_STRIP", "terminal": "power"})
        print(f"[POWER] VSS net '{vss_key}': {len(peta_koneksi[vss_key])} connections")
    daftar_koneksi_final = buat_daftar_koneksi(peta_koneksi, port_map)
    power_nets = [(n, len(pins)) for n, pins in daftar_koneksi_final if n.upper() in ("VDD", "VSS")]
    print(f"[POWER] Nets in routing: {power_nets}")

    top_level = auto_router(top_level, daftar_koneksi_final)

    if add_labels:
        for comp in config["components"]:
            if comp["type"] == "device":
                dev_name = comp["name"]
                model = comp.get("model", "").lower()
                prefix = "P_" if "p" in model[:2] else "N_"
                for ref in top_level.references:
                    if hasattr(ref, 'name') and ref.name == dev_name:
                        if hasattr(ref, 'get_ports_list'):
                            try:
                                top_level.add_ports(ref.get_ports_list(), prefix=prefix)
                            except Exception:
                                pass
                        break

        top_level = component_snap_to_grid(rename_ports_by_orientation(top_level))

        net_to_best_port = {}
        for net_key in peta_koneksi:
            for koneksi in peta_koneksi[net_key]:
                dev_name = koneksi['device']
                terminal = koneksi['terminal']
                if terminal == "body":
                    if net_key.upper() not in ("VDD", "VPWR", "VSS", "VGND", "GND"):
                        continue
                result = _get_first_port(port_map, dev_name, terminal)
                if result is not None:
                    net_to_best_port[net_key.upper()] = result[0]
                    break

        psize = (0.5, 0.5)
        move_info = []
        subcircuit_ports = config["components"][0].get("port", [])

        for port_name in subcircuit_ports:
            net_key = port_name.upper()
            target_port = net_to_best_port.get(net_key) or \
                          net_to_best_port.get(port_name.lower()) or \
                          net_to_best_port.get(port_name)

            if target_port is not None:
                try:
                    name = port_name
                    draw_layer = pdk.get_glayer("met2")
                    draw_rect = rectangle(layer=draw_layer, size=psize, centered=True).copy()
                    pin_rect = rectangle(
                        layer=pdk.get_glayer("met2_pin"),
                        size=psize, centered=True
                    ).copy()
                    pin_rect.add_label(text=name, layer=pdk.get_glayer("met2_label"))
                    move_info.append((draw_rect, target_port, None))
                    move_info.append((pin_rect, target_port, None))
                except Exception:
                    pass

        for comp, prt, alignment in move_info:
            try:
                alignment = ('c', 'b') if alignment is None else alignment
                compref = align_comp_to_port(comp, prt, alignment=alignment)
                top_level.add(compref)
            except Exception:
                pass

        print(f"[PIPELINE] {len(move_info)} pin labels added")

    top_level = top_level.flatten()
    top_level = component_snap_to_grid(top_level)

    top_level._cell.name = config["components"][0]["subcir"]
    print(f"[PIPELINE] Done: {top_level.name}")

    if run_checks:
        _run_post_processing(top_level, gds_path, netlist_input, PDK)

    return top_level


def _run_post_processing(top_level, gds_path, netlist_input, pdk_name):
    cell_name = top_level.name.split("$")[0]

    workdir = os.path.dirname(os.path.abspath(gds_path)) if gds_path else os.getcwd()
    gds_path = os.path.join(workdir, f"{cell_name}.gds")
    top_level.write_gds(gds_path)
    print(f"[CHECKS] GDS written to {gds_path}")

    if pdk_name == "gf180":
        os.environ.setdefault("PDK", "gf180mcuD")
        os.environ.setdefault("STD_CELL_LIBRARY", "gf180mcu_fd_sc_mcu7t5v0")
    elif pdk_name == "sky130":
        os.environ.setdefault("PDK", "sky130A")
        os.environ.setdefault("STD_CELL_LIBRARY", "sky130_fd_sc_hd")

    os.environ.setdefault("PDK_ROOT", os.path.expanduser("~/.volare"))
    os.environ.setdefault("PDKPATH", f"{os.environ['PDK_ROOT']}/{os.environ['PDK']}")

    print("=" * 60)
    print("[CHECKS] Running DRC...")
    print("=" * 60)
    try:
        drc_result = run_drc(gds_path, cell_name=cell_name, engine="magic", workdir=workdir)
        print(drc_result["log"][-2000:] if len(drc_result["log"]) > 2000 else drc_result["log"])
        if drc_result["clean"]:
            print("[CHECKS] DRC: CLEAN")
        else:
            print(f"[CHECKS] DRC: ERRORS FOUND (report: {drc_result['report_path']})")
    except Exception as e:
        print(f"[CHECKS] DRC skipped: {e}")

    if netlist_input:
        print("=" * 60)
        print("[CHECKS] Running LVS...")
        print("=" * 60)
        netlist_path = os.path.join(workdir, f"{cell_name}.spice")
        with open(netlist_path, "w") as f:
            f.write(netlist_input)
        try:
            lvs_result = run_lvs(gds_path, netlist_path, cell_name=cell_name, workdir=workdir)
            print(lvs_result["log"][-2000:] if len(lvs_result["log"]) > 2000 else lvs_result["log"])
            if lvs_result["match"]:
                print("[CHECKS] LVS: MATCH")
            else:
                print(f"[CHECKS] LVS: MISMATCH (report: {lvs_result['report_path']})")
        except Exception as e:
            print(f"[CHECKS] LVS skipped: {e}")

    print("=" * 60)
    print("[CHECKS] Running PEX...")
    print("=" * 60)
    try:
        pex_result = run_pex(gds_path, cell_name=cell_name, mode=2, workdir=workdir)
        print(pex_result["log"][-2000:] if len(pex_result["log"]) > 2000 else pex_result["log"])
        if pex_result["pex_path"]:
            print(f"[CHECKS] PEX done: {pex_result['pex_path']} ({pex_result['mode']})")
        else:
            print("[CHECKS] PEX: no output produced")
    except Exception as e:
        print(f"[CHECKS] PEX skipped: {e}")


def llm_to_gds(user_prompt, model="deepseek-v4-flash",
               api_key=None,
               mode="analog"):
    print(f"[LLM] Generating netlist for: {user_prompt[:80]}...")
    netlist = generate_netlist_from_prompt(user_prompt, model=model, api_key=api_key)
    if netlist is None:
        raise RuntimeError("LLM gagal menghasilkan netlist")
    print(f"[LLM] Netlist generated:\n{netlist}")
    return spice_to_gds(netlist, mode=mode)


def spice_to_gds_with_checks(netlist_input, gds_path=None,
                             mode="analog", add_labels=True):
    """Full flow: SPICE → GDS + DRC + LVS + PEX.

    All output files are placed in a directory named after the cell
    (e.g. ``ota_5t/``).

    Args:
        netlist_input: SPICE subcircuit netlist string.
        gds_path: Output GDS path (default: ``<cell_name>/<cell_name>.gds``).
        mode: Layout mode (default "analog").
        add_labels: Add pin labels (default True).

    Returns:
        dict: {
            "outdir": str,       output directory path
            "gds_path": str,     GDS file path
            "svg_path": str,     SVG preview path
            "cell_name": str,
            "drc": dict from run_drc(),
            "lvs": dict from run_lvs(),
            "pex": dict from run_pex(),
            "all_pass": bool   (True if DRC+LVS+PEX all pass)
        }
    """
    import re
    cell = re.search(r'\.subckt\s+(\S+)', netlist_input)
    cell_name = cell.group(1) if cell else "top"

    outdir = os.path.join(os.getcwd(), cell_name)
    os.makedirs(outdir, exist_ok=True)

    gds_path = gds_path or os.path.join(outdir, f"{cell_name}.gds")
    svg_path = os.path.join(outdir, f"{cell_name}.svg")

    # 1. Generate layout
    result = spice_to_gds(netlist_input, mode=mode, add_labels=add_labels)
    result.write_gds(gds_path)

    # SVG preview
    try:
        import gdstk
        lib = gdstk.read_gds(gds_path)
        lib.top_level()[0].write_svg(svg_path)
        bb = lib.top_level()[0].bounding_box()
        print(f"  Size: {bb[1][0]-bb[0][0]:.0f} x {bb[1][1]-bb[0][1]:.0f} um")
    except Exception:
        svg_path = None
    print(f"[PIPELINE] Output: {outdir}/")

    # 2. DRC
    print("=" * 60)
    print("[CHECKS] DRC...")
    print("=" * 60)
    try:
        drc = run_drc(gds_path, cell_name=cell_name, workdir=outdir)
    except Exception as e:
        drc = {"clean": False, "summary": f"DRC ERROR: {e}"}
    print(f"  {drc.get('summary', '?')}")

    # 3. LVS
    print("=" * 60)
    print("[CHECKS] LVS...")
    print("=" * 60)
    try:
        lvs = run_lvs(gds_path, netlist_content=netlist_input,
                      cell_name=cell_name, workdir=outdir)
    except Exception as e:
        lvs = {"match": False, "summary": {"message": f"LVS ERROR: {e}"}}
    lvs_msg = "MATCH" if lvs.get("match") else "MISMATCH"
    print(f"  LVS: {lvs_msg}")

    # 4. PEX
    print("=" * 60)
    print("[CHECKS] PEX...")
    print("=" * 60)
    try:
        pex = run_pex(gds_path, cell_name=cell_name, mode=2, workdir=outdir)
    except Exception as e:
        pex = {"pex_path": None, "summary": f"PEX ERROR: {e}"}
    pex_msg = "OK" if pex.get("pex_path") else "FAILED"
    print(f"  PEX: {pex.get('summary', '?')}")

    all_pass = (
        drc.get("clean", False)
        and lvs.get("match", False)
        and pex.get("pex_path") is not None
    )
    print(f"\n{'='*60}")
    print(f"  RESULT: {'ALL PASS' if all_pass else 'SOME CHECKS FAILED'}")
    print(f"{'='*60}")

    return {
        "outdir": outdir,
        "gds_path": gds_path,
        "svg_path": svg_path,
        "cell_name": cell_name,
        "drc": drc,
        "lvs": lvs,
        "pex": pex,
        "all_pass": all_pass,
    }
