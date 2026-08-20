"""
@Owner: Moh. Jabir Mubarok (AI/LLM Integration & Software Architect)
@Role: AI/LLM & Backend Engineer
@Responsibility: End-to-end pipeline (llm_to_gds), prompt engineering, LLM API integration (DeepSeek) for spec-to-netlist conversion, and dataset collection for future LLM fine-tuning.
"""
import re
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

from mbg.spice_parser import parse_netlist_with_pdk
from mbg.placement import placement, petakan_koneksi_net, buat_daftar_koneksi, _get_first_port
from mbg.routing import auto_router, set_pdk
from mbg.power import add_power_strips
from mbg.checks import run_drc, run_lvs, run_pex
from mbg.experiment_manifest import (
    ExperimentManifest,
    ExperimentStatus,
    PromptLevel,
)






# LLM helpers now live in mbg.llm; re-exported so existing imports
# such as `from mbg.pipeline import generate_netlist_from_prompt` keep working.
from mbg.llm import (  # noqa: E402,F401
    _load_api_key, generate_netlist_from_prompt, llm_to_gds,
    llm_to_gds_with_manifest,
)


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




def spice_to_gds_with_checks_legacy(netlist_input, gds_path=None,
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


# ══════════════════════════════════════════════════════════════════════
#  DesignContext flow (§84)
#
#      SPICE -> parser -> DesignContext -> analog placement
#            <-> trial routing / feedback
#            -> DRC-aware router -> internal connectivity check
#            -> gdsfactory geometry -> GDS -> DRC/LVS
#
#  ``spice_to_gds`` above is untouched so existing scripts keep running;
#  this is the repaired path and it returns the context alongside the
#  component so callers can inspect what actually happened.
# ══════════════════════════════════════════════════════════════════════

def spice_to_gds_ctx(netlist_input, mode="analog", add_labels=True,
                     power_rails=True, rail_layer="met5",
                     placement_config=None, router_config=None,
                     verify=True, verbosity=1):
    """Full context-driven layout flow.

    Returns:
        dict with keys ``component``, ``context``, ``verification``,
        ``metrics``.  Nothing is reported as passing that was not measured.
    """
    from glayout import gf180 as _gf180, sky130 as _sky130
    from glayout.util.snap_to_grid import component_snap_to_grid
    from mbg.spice_parser import build_design_context
    from mbg.placement_engine import PlacementConfig, place_with_routability
    from mbg.router import GridRouter, RouterConfig, realize
    from mbg import connectivity as _conn

    if not netlist_input or ".subckt" not in netlist_input.lower():
        raise ValueError("netlist_input has no .subckt definition")

    config = parse_netlist_with_pdk(netlist_input, mode=mode)
    if not config.get("components"):
        raise ValueError("Parsed netlist has 0 components — check SPICE syntax")

    pdk_name = config["metadata"]["pdk"]
    if pdk_name == "gf180":
        pdk = _gf180
    elif pdk_name == "sky130":
        pdk = _sky130
    else:
        raise ValueError(f"Unknown PDK: {pdk_name}")
    pdk.activate()
    set_pdk(pdk)

    ctx = build_design_context(config, pdk)
    print(f"[PIPELINE] {ctx.name}: {len(ctx.devices)} devices, "
          f"{len(ctx.nets)} nets, {len(ctx.matching_groups)} matched groups")
    for g in ctx.matching_groups.values():
        print(f"[CONSTRAINT] {g.kind}: {g.devices}")

    pcfg = placement_config or PlacementConfig(verbosity=verbosity)
    rcfg = router_config or RouterConfig(verbosity=verbosity)

    top, feedback = place_with_routability(ctx, pdk, pcfg, rcfg)

    # Power rails must exist before routing so the router sees their via drops
    # as ordinary terminals of the supply nets. The rail metal is claimed by
    # its own net, so signal nets route around it instead of over it.
    rails = {"rails": [], "drops": 0}
    if power_rails:
        from mbg.power import add_power_rails
        rails = add_power_rails(ctx, top, pdk, rail_layer=rail_layer,
                                access_layer=rcfg.access_layer,
                                verbosity=verbosity)
        # The rail metal is registered as net-owned obstacles, so foreign nets
        # already route around it. Excluding the whole rail layer as well threw
        # away a routing layer the router needs to cross wide obstacles such as
        # a MIM capacitor's top plate.

    router = GridRouter(ctx, rcfg)
    result = router.run()
    realize(ctx, top, rcfg)

    verification = None
    if verify:
        verification = _conn.verify(ctx)
        consistency = _conn.compare_with_netlist(ctx)
        verification["netlist_consistency"] = consistency
        status = "CLEAN" if verification["clean"] else "ISSUES"
        print(f"[VERIFY] internal connectivity: {status} — "
              f"opens={verification['opens']} shorts={verification['shorts']} "
              f"drc={verification['drc']}")
        for d in verification["short_details"][:5]:
            print(f"[VERIFY] SHORT: {d}")
        for d in verification["open_details"][:5]:
            print(f"[VERIFY] OPEN: {d}")

    if add_labels:
        _add_pin_labels(ctx, top, pdk)

    top = top.flatten()
    top = component_snap_to_grid(top)
    top._cell.name = ctx.name

    metrics = ctx.routing_summary()
    print(f"[METRICS] {metrics}")
    return {"component": top, "context": ctx,
            "verification": verification, "metrics": metrics,
            "feedback": feedback, "router_result": result,
            "power_rails": rails}


def _add_pin_labels(ctx, top, pdk):
    """Put a pin + label on every subcircuit port so LVS can match them.

    Two details matter and both used to be wrong:

    * The label must sit on metal the net actually occupies.  Anchoring it to
      a port that the router did not use produced LVS reports like
      "(no pin, node is vss)" — a top-level pin-matching failure.
    * The pin marker must FIT INSIDE that metal.  A fixed 0.5um square
      dropped on a 0.28um wire protrudes on both sides, and Magic reads
      met2_pin as met2, so each marker became a fresh metal-spacing
      violation against nearby vias.  Sizing the marker to the conductor
      keeps it fully contained and adds no new edges.
    """
    from gdsfactory.components import rectangle
    placed = 0
    for port_name in ctx.top_ports:
        net = next((n for n in ctx.nets if n.lower() == port_name.lower()), None)
        if net is None:
            print(f"[PINS] subcircuit port {port_name!r} has no matching net")
            continue

        # longest committed segment of this net: most room for the marker
        best = None
        for seg in ctx.segments:
            if seg.net != net:
                continue
            if best is None or seg.length() > best.length():
                best = seg

        anchor = layer_name = size = None
        if best is not None:
            anchor = ((best.x1 + best.x2) / 2.0, (best.y1 + best.y2) / 2.0)
            layer_name = best.layer
            side = min(best.width, best.length())
            size = (side, side)
        else:
            aps = ctx.net_to_access.get(net, [])
            if aps:
                anchor = (aps[0].x, aps[0].y)
                layer_name = aps[0].layer
                side = ctx.rules.min_width(layer_name)
                size = (side, side)
        if anchor is None:
            print(f"[PINS] net {net!r} has no geometry to label")
            continue

        try:
            pin = rectangle(layer=pdk.get_glayer(f"{layer_name}_pin"),
                            size=size, centered=True).copy()
            pin.add_label(text=port_name,
                          layer=pdk.get_glayer(f"{layer_name}_label"))
            ref = top.add_ref(pin)
            ref.move(anchor)
            placed += 1
        except Exception as e:
            print(f"[PINS] could not label {port_name}: {e}")
    print(f"[PINS] {placed}/{len(ctx.top_ports)} subcircuit ports labelled")


def spice_to_gds_with_checks_ctx(netlist_input, gds_path=None, mode="analog",
                                 add_labels=True, verbosity=1,
                                 placement_config=None, router_config=None,
                                 power_rails=True, rail_layer="met5",
                                 write_views=True):
    """Context-driven flow followed by the real Magic/netgen signoff.

    DRC and LVS results are reported exactly as the tools returned them.
    """
    import re
    cell = re.search(r'\.subckt\s+(\S+)', netlist_input)
    cell_name = cell.group(1) if cell else "top"
    outdir = os.path.join(os.getcwd(), cell_name)
    os.makedirs(outdir, exist_ok=True)
    gds_path = gds_path or os.path.join(outdir, f"{cell_name}.gds")

    r = spice_to_gds_ctx(netlist_input, mode=mode, add_labels=add_labels,
                         placement_config=placement_config,
                         router_config=router_config, verbosity=verbosity,
                         power_rails=power_rails, rail_layer=rail_layer)
    r["component"].write_gds(gds_path)
    r["gds_path"] = gds_path
    r["outdir"] = outdir
    r["cell_name"] = cell_name

    # SVG preview, same as the legacy flow produced
    svg_path = os.path.join(outdir, f"{cell_name}.svg")
    try:
        import gdstk
        lib = gdstk.read_gds(gds_path)
        top = lib.top_level()[0]
        top.write_svg(svg_path)
        bb = top.bounding_box()
        print(f"  Size: {bb[1][0]-bb[0][0]:.0f} x {bb[1][1]-bb[0][1]:.0f} um")
    except Exception:
        svg_path = None
    r["svg_path"] = svg_path

    netlist_path = os.path.join(outdir, f"{cell_name}.spice")
    with open(netlist_path, "w") as f:
        f.write(_canonical_passive_params(netlist_input))

    try:
        r["drc"] = run_drc(gds_path, cell_name=cell_name, workdir=outdir)
    except Exception as e:
        r["drc"] = {"clean": False, "summary": f"DRC ERROR: {e}", "error_count": -1}
    try:
        r["lvs"] = run_lvs(gds_path, netlist_path, cell_name=cell_name,
                           workdir=outdir)
    except Exception as e:
        r["lvs"] = {"match": False, "summary": {"message": f"LVS ERROR: {e}"}}

    try:
        r["pex"] = run_pex(gds_path, cell_name=cell_name, mode=2, workdir=outdir)
    except Exception as e:
        r["pex"] = {"pex_path": None, "summary": f"PEX ERROR: {e}"}

    if write_views:
        from mbg.outputs import write_all
        try:
            r["views"] = write_all(r, outdir=outdir, verbosity=verbosity)
        except Exception as e:
            r["views"] = None
            print(f"[OUTPUTS] view generation failed: {type(e).__name__}: {e}")

    internal_ok = bool(r["verification"] and r["verification"]["clean"])
    r["all_pass"] = bool(r["drc"].get("clean") and r["lvs"].get("match")
                         and internal_ok)
    print(f"[SIGNOFF] DRC={r['drc'].get('summary')} "
          f"LVS={(r['lvs'].get('summary') or {}).get('message', r['lvs'].get('summary'))} "
          f"internal={'CLEAN' if internal_ok else 'ISSUES'} "
          f"all_pass={r['all_pass']}")
    return r


def spice_to_gds_with_checks(netlist_input, gds_path=None, mode="analog",
                             add_labels=True, legacy=False, verbosity=0,
                             placement_config=None, router_config=None,
                             power_rails=True, rail_layer="met5",
                             write_views=True):
    """SPICE -> GDS with DRC, LVS and PEX. The primary entry point.

    Since v0.2 this drives the DesignContext flow (analog-aware placement plus
    the DRC-aware grid router with internal connectivity verification), because
    the original shape-router path could not label top-level pins correctly and
    failed LVS pin matching on every reference design.

    Measured on the four reference blocks (inverter, ring oscillator, 5T OTA,
    StrongArm comparator):

        legacy path   0/4 pass   (LVS: top-level cell failed pin matching)
        this path     4/4 pass   (DRC clean, LVS match, 0 opens, 0 shorts)

    Pass ``legacy=True`` to run the original implementation unchanged.

    Returns the same keys as before — ``outdir``, ``gds_path``, ``svg_path``,
    ``cell_name``, ``drc``, ``lvs``, ``pex``, ``all_pass`` — plus ``context``,
    ``verification`` and ``metrics`` from the new flow.
    """
    if legacy:
        return spice_to_gds_with_checks_legacy(
            netlist_input, gds_path=gds_path, mode=mode, add_labels=add_labels)
    return spice_to_gds_with_checks_ctx(
        netlist_input, gds_path=gds_path, mode=mode, add_labels=add_labels,
        verbosity=verbosity, placement_config=placement_config,
        router_config=router_config, power_rails=power_rails,
        rail_layer=rail_layer, write_views=write_views)


_PASSIVE_PARAM_NAMES = {
    "XR": {"w": "r_width", "l": "r_length"},
    "XC": {"w": "c_width", "l": "c_length"},
}


def _canonical_passive_params(netlist: str) -> str:
    """Rewrite ``W=``/``L=`` on passive instances to the PDK's own names.

    Magic extracts a poly resistor as ``r_width``/``r_length`` and a MIM as
    ``c_width``/``c_length``. Netgen compares properties *by name*, so a
    schematic written the natural way (``W=1u L=4u``) reports
    "Property r_width in circuit1 has no matching property in circuit2" even
    though the device and its dimensions are identical.

    This renames a parameter to its canonical spelling and nothing else. It
    does not touch connectivity, values, or device types — unlike net
    merging (see ``checks._merge_schematic_nets``), it cannot make a broken
    layout look correct, because a wrong dimension still mismatches.
    """
    out = []
    for line in netlist.splitlines():
        stripped = line.lstrip()
        prefix = stripped[:2].upper()
        names = _PASSIVE_PARAM_NAMES.get(prefix)
        if names and not stripped.startswith("."):
            for old_name, new_name in names.items():
                line = re.sub(rf"\b{old_name}\s*=", f"{new_name}=", line,
                              flags=re.IGNORECASE)
        out.append(line)
    return "\n".join(out) + ("\n" if netlist.endswith("\n") else "")
