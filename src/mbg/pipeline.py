"""Public flat-SPICE layout pipeline: conventional placement and Magic/netgen checks."""
import os
import re
from pathlib import Path

from mbg.checks import run_drc, run_lvs, run_pex
from mbg.utils import write_gds_foundry

_PASSIVE_PARAM_NAMES = {
    "XR": {"w": "r_width", "l": "r_length"},
    "XC": {"w": "c_width", "l": "c_length"},
}


def spice_to_gds_ctx(netlist_input, mode="analog", add_labels=True,
                     power_rails=True, rail_layer="met5", placement_config=None,
                     router_config=None, verify=True, verbosity=1, pdk=None,
                     macro_config=None):
    import copy
    import glayout
    from glayout.util.snap_to_grid import component_snap_to_grid
    from mbg import pdk_profile
    from mbg.spice_parser import parse_netlist_with_pdk, build_design_context
    from mbg.placement_engine import PlacementConfig, place_with_routability
    from mbg.router import RouterConfig, GridRouter, realize
    from mbg import connectivity
    from mbg.macro import MacroConfig, resolve_interface, prepare_macro, label_macro_pins
    from mbg.macro_transform import normalize_macro
    from mbg.power import add_power_rails

    if not isinstance(netlist_input,str) or not netlist_input.strip():
        raise ValueError('a nonempty flat SPICE subcircuit is required')
    config = parse_netlist_with_pdk(netlist_input,mode=mode)
    profile = pdk_profile.for_netlist(netlist_input,pdk)
    pdk = getattr(glayout,profile.glayout_pdk)
    pdk.activate()
    macro = MacroConfig.from_dict(macro_config)
    interface_source = {}
    if macro.enabled:
        if profile.name != 'gf180mcuD':
            raise ValueError('ordinary macro framing is supported only for gf180mcuD')
        if not add_labels:
            raise ValueError('ordinary macro framing requires physical pin labels')
        macro, interface_source = resolve_interface(netlist_input,macro)
    ctx = build_design_context(config,pdk,profile=profile)
    pcfg = copy.copy(placement_config or PlacementConfig(verbosity=verbosity))
    rcfg = router_config or RouterConfig(verbosity=verbosity)
    original_terms = {name:list(net.terminals) for name,net in ctx.nets.items()}
    rails = {'rails':[], 'drops':0}

    def before_route(current,top):
        nonlocal rails
        # Trial placement retries discard old references and APs in place().
        # Restore only real circuit terminals before adding this attempt's
        # rail, ring and macro-pin terminals.
        for name,net in current.nets.items():
            net.terminals[:] = original_terms.get(name,[])
        if power_rails:
            rails = add_power_rails(current,top,pdk,rail_layer=rail_layer,
                                    access_layer=rcfg.access_layer,verbosity=verbosity)
        if macro.enabled:
            prepare_macro(current,top,pdk,macro,rcfg)
            current.macro_interface['dut'] = interface_source

    top,feedback = place_with_routability(ctx,pdk,pcfg,rcfg,before_route=before_route)
    router = GridRouter(ctx,rcfg)
    routed = router.run()
    realize(ctx,top,rcfg)
    verification = connectivity.verify(ctx) if verify else None
    if add_labels:
        if macro.enabled:
            label_macro_pins(ctx,top,pdk)
        else:
            _add_pin_labels(ctx,top,pdk)
    top = top.flatten()
    if macro.enabled:
        top = normalize_macro(ctx,top)
        bb = ctx.macro_bbox
        top.add_polygon([(0,0),(bb.width,0),(bb.width,bb.height),(0,bb.height)],layer=(0,0))
    top = component_snap_to_grid(top)
    top._cell.name = ctx.name
    return {'component':top,'context':ctx,'verification':verification,
            'metrics':ctx.routing_summary(),'feedback':feedback,'router_result':routed,
            'power_rails':rails,'macro_config':macro.as_dict(),
            'macro_interface':getattr(ctx,'macro_interface',None)}


def _with_checks_ctx(netlist_input,profile,*,gds_path,mode,add_labels,verbosity,
                     placement_config,router_config,power_rails,rail_layer,
                     write_views,outdir,macro_config=None):
    from mbg.macro import validate_identifier
    cell = re.search(r'^\s*\.subckt\s+(\S+)',netlist_input,re.I|re.M)
    if cell is None:
        raise ValueError('SPICE subcircuit header is required')
    name = validate_identifier(cell.group(1),'cell')
    if outdir is None:
        if gds_path is not None:
            outdir = str(Path(gds_path).expanduser().resolve().parent)
        else:
            from mbg.output_paths import new_run_directory
            outdir = str(new_run_directory('layouts',name))
    outdir = str(Path(outdir).expanduser().resolve())
    Path(outdir).mkdir(parents=True,exist_ok=True)
    gds_path = str(Path(gds_path).expanduser().resolve()) if gds_path else str(Path(outdir)/(name+'.gds'))
    r = spice_to_gds_ctx(netlist_input,mode=mode,add_labels=add_labels,
                        placement_config=placement_config,router_config=router_config,
                        verbosity=verbosity,power_rails=power_rails,rail_layer=rail_layer,
                        pdk=profile.name,macro_config=macro_config)
    write_gds_foundry(r['component'],gds_path)
    r.update(pdk=profile.name,gds_path=gds_path,outdir=outdir,cell_name=name)
    Path(outdir,name+'.spice').write_text(_canonical_passive_params(netlist_input))
    r['svg_path'] = None
    try:
        import gdstk
        svg = str(Path(outdir)/(name+'.svg'))
        gdstk.read_gds(gds_path).top_level()[0].write_svg(svg)
        r['svg_path'] = svg
    except Exception:
        pass
    for key,call in (('drc',lambda:run_drc(gds_path,cell_name=name,workdir=outdir)),
                     ('lvs',lambda:run_lvs(gds_path,str(Path(outdir)/(name+'.spice')),cell_name=name,workdir=outdir)),
                     ('pex',lambda:run_pex(gds_path,cell_name=name,mode=2,workdir=outdir))):
        try:
            r[key] = call()
        except Exception as exc:
            r[key] = {'clean':False,'match':False,'pex_path':None,'status':'FAIL','message':str(exc)}
    pex = (r.get('pex') or {}).get('pex_path')
    r['all_pass'] = bool((r.get('drc') or {}).get('clean') and
                         (r.get('lvs') or {}).get('match') and
                         (r.get('verification') or {}).get('clean') and pex and Path(pex).is_file())
    r['verification_scope'] = 'Magic DRC, netgen LVS, internal connectivity and PEX extraction'
    if write_views:
        from mbg.outputs import write_all
        r['views'] = write_all(r,outdir=outdir,verbosity=verbosity)
    return r


def spice_to_gds_with_checks_ctx(netlist_input,gds_path=None,mode='analog',
                                add_labels=True,verbosity=1,placement_config=None,
                                router_config=None,power_rails=True,rail_layer='met5',
                                write_views=True,pdk=None,outdir=None,macro_config=None):
    from mbg import pdk_profile
    from mbg.netlist_check import check_netlist
    profile = pdk_profile.for_netlist(netlist_input,pdk)
    static = check_netlist(netlist_input,profile)
    errors = [i['message'] for i in static.get('issues',[]) if i.get('severity') == 'error']
    if errors:
        raise ValueError('static netlist checks failed: '+'; '.join(errors))
    with profile.env():
        return _with_checks_ctx(netlist_input,profile,gds_path=gds_path,mode=mode,
            add_labels=add_labels,verbosity=verbosity,placement_config=placement_config,
            router_config=router_config,power_rails=power_rails,rail_layer=rail_layer,
            write_views=write_views,outdir=outdir,macro_config=macro_config)


def spice_to_gds_with_checks(*args,legacy=False,**kwargs):
    if legacy:
        raise ValueError('the public release supports only the conventional context pipeline')
    return spice_to_gds_with_checks_ctx(*args,**kwargs)


def spice_to_gds(netlist_input,**kwargs):
    return spice_to_gds_ctx(netlist_input,**kwargs)['component']


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
            # No committed segment. That is legitimate only when the net had
            # nothing to route -- a single terminal is already one conductor,
            # so its access point IS the net. When the net has several
            # terminals and the router did not connect them, the terminals are
            # separate conductors and NONE of them is "the net": dropping the
            # port's name on whichever access point happens to be first in
            # insertion order asserts a connection that does not exist.
            #
            # That is not a cosmetic problem. Magic names the extracted node
            # after the label, so an unrouted supply whose terminals happen to
            # share device metal would extract under the port's own name and
            # LVS could report MATCH on a net that was never routed. Refusing
            # to label turns a possible false MATCH into a loud, diagnosable
            # one. Verified on the 12-MOS clocked comparator: the fallback put
            # the `vdd` label on XM3's source while the vdd net was entirely
            # unrouted.
            aps = ctx.net_to_access.get(net, [])
            # Count LOGICAL terminals, not access points: one gLayout MOS
            # terminal exposes N/E/S/W ports that are already tied together
            # inside the device, so a single-terminal net such as a bare gate
            # input has four access points and is still one conductor.
            terminals = {(a.instance, a.terminal) for a in aps}
            rn = ctx.routed_nets.get(net)
            connected = (rn is not None and rn.complete) or len(terminals) <= 1
            if aps and connected:
                anchor = (aps[0].x, aps[0].y)
                layer_name = aps[0].layer
                side = ctx.rules.min_width(layer_name)
                size = (side, side)
            elif aps:
                print(f"[PINS] REFUSING to label port {port_name!r}: net "
                      f"{net!r} has {len(terminals)} terminals and no routed "
                      f"geometry joining them — labelling one of them would "
                      f"claim a connection the layout does not have")
                continue
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
