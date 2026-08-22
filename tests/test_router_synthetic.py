"""Deterministic synthetic tests for the repaired placement + router (§65).

Tests 1-5 build a DesignContext directly, so they run in milliseconds and do
not depend on device generation.  Tests 6-8 use real gLayout devices because
what they check (matching, symmetry, DNW) only exists in real geometry.

Run:  python -m pytest tests/test_router_synthetic.py -v
      python tests/test_router_synthetic.py          # plain runner
"""

import os
import sys


def _repo_src():
    """Walk up from this file until the src/mbg package is found.

    The engine lives at <repo>/src/mbg while this test lives under
    designs/notebooks/chipathon2026-D/tests, so the path is discovered
    rather than counted in "..".
    """
    d = os.path.dirname(os.path.abspath(__file__))
    for _ in range(8):
        cand = os.path.join(d, "src")
        if os.path.isdir(os.path.join(cand, "mbg")):
            return cand
        d = os.path.dirname(d)
    raise RuntimeError("could not locate src/mbg from " + __file__)


sys.path.insert(0, _repo_src())


os.environ.setdefault("PDK_ROOT", os.path.expanduser("~/.volare"))
os.environ.setdefault("PDK", "gf180mcuD")
os.environ.setdefault("PDKPATH", os.path.join(os.environ["PDK_ROOT"], "gf180mcuD"))

from glayout import gf180

from mbg import connectivity as conn
from mbg.design_context import (
    BoundingBox, DesignContext, Device, Net, Obstacle, PinAccessPoint,
)
from mbg.pdk_rules import get_rules
from mbg.router import GridRouter, RouterConfig

QUIET = RouterConfig(verbosity=0)


# ── helpers ────────────────────────────────────────────────────────────

def make_ctx(name="t"):
    gf180.activate()
    ctx = DesignContext(name=name)
    ctx.pdk = gf180
    ctx.rules = get_rules(gf180)
    return ctx


def add_terminal(ctx, inst, term, net, x, y, layer="met2", orientation=0.0,
                 width=0.5):
    """Register one logical terminal with one physical access point."""
    if net not in ctx.nets:
        ctx.add_net(Net(name=net))
    ctx.nets[net].terminals.append((inst, term))
    if inst not in ctx.devices:
        ctx.add_device(Device(name=inst, model="synthetic", kind="nmos"))
    ctx.devices[inst].terminals[term] = net
    ctx.add_access_point(PinAccessPoint(
        instance=inst, terminal=term, net=net, layer=layer,
        x=x, y=y, orientation=orientation, width=width))
    ctx.device_bboxes[inst] = BoundingBox(x - 1, y - 1, x + 1, y + 1)


def route(ctx, cfg=None):
    r = GridRouter(ctx, cfg or QUIET)
    return r, r.run()


def report(name, expected, actual, ok):
    """Print the verdict, then FAIL LOUDLY if it is bad.

    These tests used to end with `return report(...)`, and pytest treats a
    test that returns a value -- including False -- as a PASS, warning about
    the return but not failing. Every test in this file was therefore unable
    to fail under `pytest tests/`; only an uncaught exception could stop one.
    Raising here makes the same `return report(...)` line a real assertion for
    pytest, while the plain-script runner below still catches it and reports
    the failure the way it always did.
    """
    print(f"{'PASS' if ok else 'FAIL'}  {name}\n"
          f"      expected: {expected}\n      actual:   {actual}")
    if not ok:
        raise AssertionError(
            f"{name}\n      expected: {expected}\n      actual:   {actual}")
    return ok


# ── Test 1 — single net ────────────────────────────────────────────────

def test_single_net():
    ctx = make_ctx("t1")
    add_terminal(ctx, "A", "p", "N1", 0.0, 0.0, orientation=0)
    add_terminal(ctx, "B", "p", "N1", 12.0, 0.0, orientation=180)
    _r, res = route(ctx)
    v = conn.verify(ctx)
    owned = all(s.net for s in ctx.segments) and all(x.net for x in ctx.vias)
    ok = (res["failed"] == [] and v["opens"] == 0 and v["shorts"] == 0
          and v["drc"] == 0 and owned and len(ctx.segments) > 0)
    return report("Test 1 single net A->B",
                  "connected, no DRC, every conductor owned",
                  f"routed={res['routed']} opens={v['opens']} shorts={v['shorts']} "
                  f"drc={v['drc']} owned={owned}", ok)


# ── Test 2 — crossing nets ─────────────────────────────────────────────

def test_crossing_nets():
    ctx = make_ctx("t2")
    add_terminal(ctx, "A", "p", "N1", 0.0, 6.0, orientation=0)
    add_terminal(ctx, "B", "p", "N1", 12.0, 6.0, orientation=180)
    add_terminal(ctx, "C", "p", "N2", 6.0, 0.0, orientation=90)
    add_terminal(ctx, "D", "p", "N2", 6.0, 12.0, orientation=270)
    _r, res = route(ctx)
    v = conn.verify(ctx)
    ok = (res["failed"] == [] and v["shorts"] == 0 and v["opens"] == 0
          and v["drc"] == 0)
    return report("Test 2 crossing nets",
                  "both routed, layer separation, no short",
                  f"routed={res['routed']} shorts={v['shorts']} drc={v['drc']}", ok)


# ── Test 3 — via conflict ──────────────────────────────────────────────

def test_via_conflict():
    """Two unrelated terminals close enough that their via PADS cannot both
    be legal, while the ports themselves are legally separated.

    Pads are 0.5um and need 0.36um of cut spacing, so two landings need
    0.86um between them; the ports here sit 0.6um apart.  The router must
    either relocate one landing or refuse it — never stack both.
    """
    ctx = make_ctx("t3")
    add_terminal(ctx, "A", "p", "N1", 0.0, 0.0, orientation=90)
    add_terminal(ctx, "A2", "p", "N1", 10.0, 0.0, orientation=270)
    add_terminal(ctx, "B", "p", "N2", 0.60, 0.0, orientation=90)
    add_terminal(ctx, "B2", "p", "N2", 10.0, 6.0, orientation=270)
    r, res = route(ctx)
    v = conn.verify(ctx)

    sep = 0.36
    bad_pairs = []
    for i, a in enumerate(ctx.vias):
        for b in ctx.vias[i + 1:]:
            if a.net == b.net:
                continue
            need = (a.size + b.size) / 2.0 + sep
            if abs(a.x - b.x) < need and abs(a.y - b.y) < need:
                bad_pairs.append((a.net, b.net))
    ok = v["shorts"] == 0 and not bad_pairs and v["drc"] == 0
    return report("Test 3 via conflict",
                  "no illegal via committed, no pad clash, no short",
                  f"shorts={v['shorts']} pad_clashes={bad_pairs} drc={v['drc']} "
                  f"failures={[f.cause for f in ctx.failures]}", ok)


# ── Test 4 — blocked path ──────────────────────────────────────────────

def test_blocked_path():
    ctx = make_ctx("t4")
    add_terminal(ctx, "A", "p", "N1", 0.0, 0.0, orientation=0)
    add_terminal(ctx, "B", "p", "N1", 16.0, 0.0, orientation=180)
    # a wall on the direct met3 path, leaving room above and below
    for layer in ("met3",):
        ctx.add_obstacle(Obstacle(layer=layer,
                                  bbox=BoundingBox(7.0, -4.0, 9.0, 4.0),
                                  owner="WALL", kind="blockage"))
    _r, res = route(ctx)
    v = conn.verify(ctx)
    wall = BoundingBox(7.0, -4.0, 9.0, 4.0)
    through = [s for s in ctx.segments if s.layer == "met3"
               and s.bbox().overlaps(wall)]
    ok = (res["failed"] == [] and v["shorts"] == 0 and v["opens"] == 0
          and not through)
    return report("Test 4 blocked path",
                  "connected without any met3 crossing the blockage",
                  f"routed={res['routed']} met3_through_wall={len(through)} "
                  f"opens={v['opens']} shorts={v['shorts']}", ok)


# ── Test 5 — congested channel ─────────────────────────────────────────

def test_congested_channel():
    """Six nets that must share one narrow corridor."""
    ctx = make_ctx("t5")
    for i in range(6):
        y = i * 1.0
        add_terminal(ctx, f"L{i}", "p", f"N{i}", 0.0, y, orientation=0)
        add_terminal(ctx, f"R{i}", "p", f"N{i}", 20.0, y, orientation=180)
    for layer in ("met3", "met4", "met5"):
        ctx.add_obstacle(Obstacle(layer=layer,
                                  bbox=BoundingBox(8.0, 6.5, 12.0, 40.0),
                                  owner="W1", kind="blockage"))
        ctx.add_obstacle(Obstacle(layer=layer,
                                  bbox=BoundingBox(8.0, -40.0, 12.0, -2.0),
                                  owner="W2", kind="blockage"))
    _r, res = route(ctx, RouterConfig(verbosity=0, ripup_iterations=8))
    v = conn.verify(ctx)
    ok = v["shorts"] == 0 and len(res["routed"]) >= 5
    return report("Test 5 congested channel",
                  "nets negotiate the corridor, no shorts",
                  f"routed={len(res['routed'])}/6 failed={res['failed']} "
                  f"shorts={v['shorts']} drc={v['drc']}", ok)


# ── Tests 6-8 — real devices ───────────────────────────────────────────

def _build(netlist, cfgkw=None):
    from mbg.spice_parser import build_design_context, parse_netlist_with_pdk
    from mbg.placement_engine import PlacementConfig, place
    gf180.activate()
    ctx = build_design_context(parse_netlist_with_pdk(netlist), gf180)
    place(ctx, gf180, PlacementConfig(verbosity=0, **(cfgkw or {})))
    return ctx


def test_differential_pair():
    ctx = _build("""
.lib gf180 typical
.subckt dp vdd vss inp inm o1 o2 tail
XM1 o1 inp t vss nfet_03v3 L=1u W=4u nf=2
XM2 o2 inm t vss nfet_03v3 L=1u W=4u nf=2
XM3 t  tail vss vss nfet_03v3 L=1u W=4u nf=2
XM4 o1 o1  vdd vdd pfet_03v3 L=1u W=4u nf=2
XM5 o2 o1  vdd vdd pfet_03v3 L=1u W=4u nf=2
.ends
""")
    grp = [g for g in ctx.matching_groups.values() if g.kind == "diff_pair"]
    a, b = ctx.device_bboxes["XM1"], ctx.device_bboxes["XM2"]
    same_size = abs(a.width - b.width) < 1e-6 and abs(a.height - b.height) < 1e-6
    same_row = abs(a.ymin - b.ymin) < 1e-6
    _r, res = route(ctx)
    lens, vias = {}, {}
    for net in ("o1", "o2"):
        rn = ctx.routed_nets.get(net)
        lens[net] = round(rn.wire_length(), 2) if rn else None
        vias[net] = rn.via_count() if rn else None
    both_routed = all(lens[n] is not None for n in ("o1", "o2"))
    ok = (bool(grp) and same_size and same_row and res["failed"] == []
          and both_routed)
    return report("Test 6 differential pair",
                  "pair detected, identical geometry, same row, both outputs routed",
                  f"group={[g.devices for g in grp]} same_size={same_size} "
                  f"same_row={same_row} lengths={lens} vias={vias} "
                  f"failed={res['failed']}", ok)


def test_current_mirror():
    ctx = _build("""
.lib gf180 typical
.subckt cm vdd vss iin iout
XM1 iin  iin  vdd vdd pfet_03v3 L=1u W=4u nf=2
XM2 iout iin  vdd vdd pfet_03v3 L=1u W=4u nf=2
XM3 iin  vss  vss vss nfet_03v3 L=1u W=4u nf=2
.ends
""")
    grp = [g for g in ctx.matching_groups.values() if g.kind == "current_mirror"]
    a, b = ctx.device_bboxes["XM1"], ctx.device_bboxes["XM2"]
    same_size = abs(a.width - b.width) < 1e-6 and abs(a.height - b.height) < 1e-6
    adjacent = abs(a.ymin - b.ymin) < 1e-6
    _r, res = route(ctx)
    v = conn.verify(ctx)
    ok = bool(grp) and same_size and adjacent and v["shorts"] == 0
    return report("Test 7 current mirror",
                  "mirror detected, matched geometry, adjacent, no shorts",
                  f"group={[g.devices for g in grp]} same_size={same_size} "
                  f"adjacent={adjacent} shorts={v['shorts']} failed={res['failed']}", ok)


def test_deep_nwell():
    ctx = _build("""
.lib gf180 typical
.subckt dnw vdd vss a b
XM1 a vss vss vss nfet_03v3 L=1u W=4u nf=2
XM2 b a   vss vss nfet_03v3 L=1u W=4u nf=2
.ends
""", cfgkw={"with_dnwell": True})
    flagged = [d for d, f in ctx.deep_nwell_flags.items() if f]
    dnw_shapes = [o for o in ctx.obstacles if o.layer == "dnwell"]
    _r, res = route(ctx)
    v = conn.verify(ctx)
    ok = len(flagged) == 2 and res["failed"] == [] and v["shorts"] == 0
    return report("Test 8 deep n-well",
                  "both NFETs flagged for DNW, layout still routes cleanly",
                  f"flagged={flagged} dnw_obstacles={len(dnw_shapes)} "
                  f"failed={res['failed']} shorts={v['shorts']}", ok)




# ── Tests 9-13 — the complexity boundary (12-MOS clocked comparator) ───
#
# Each of these reproduces, in isolation and in milliseconds, one defect that
# only became visible on a circuit large enough to have a high-degree supply
# net. They are written against the mechanism, not against the comparator, so
# they keep guarding once the comparator itself is long green.


def test_escape_on_tap_ring():
    """A port sitting on a device's own tap ring must find an escape.

    gLayout stores a tap ring as several polygons: a wide band plus the
    contact pads the band contains. An escape drawn on the band overlaps it
    (same net, legal) and then passes within min_spacing of two of those
    pads. Judged polygon by polygon that is a notch; after the boolean merge
    any mask operation sees, the band fills the slot and no gap exists.
    Rejecting it stranded every `body` terminal of the 12-MOS comparator, and
    route_net then dropped both supply nets whole.

    Geometry below is the real XM6.body case, translated to the origin.
    """
    ctx = make_ctx("t9")
    add_terminal(ctx, "RING", "body", "N1", 0.0, 0.0, layer="met2",
                 orientation=90, width=3.38)
    add_terminal(ctx, "FAR", "p", "N1", 0.0, 14.0, layer="met2",
                 orientation=270, width=0.5)
    band = BoundingBox(-1.69, -0.50, 1.69, 0.0)          # the wide band
    ctx.add_obstacle(Obstacle(layer="met2", bbox=band, owner="RING",
                              kind="device_geometry", net="N1"))
    for x0 in (-0.65, 0.15):                              # pads inside it
        ctx.add_obstacle(Obstacle(
            layer="met2", bbox=BoundingBox(x0, -0.50, x0 + 0.50, 0.0),
            owner="RING", kind="device_geometry", net="N1"))
    r = GridRouter(ctx, QUIET)
    chosen = r.select_access_points()
    ring = chosen[("RING", "body")]
    _res = r.run()
    v = conn.verify(ctx)
    ok = ring.legal and v["opens"] == 0 and v["shorts"] == 0
    return report("Test 9 escape from a tap ring",
                  "the ring's own sub-polygons do not block its escape",
                  f"legal={ring.legal} opens={v['opens']} shorts={v['shorts']}",
                  ok)


def test_same_net_notch_still_rejected():
    """The tap-ring exemption must not become "same net, anything goes".

    A same-net slot that nothing fills is a real spacing violation. Here two
    same-net shapes stand apart with open space between them and no third
    shape bridging the gap, so metal laid in that gap is still illegal.
    Without this test the fix for Test 9 would silently legalise real notches.
    """
    ctx = make_ctx("t10")
    add_terminal(ctx, "A", "p", "N1", 0.0, 0.0, layer="met2", orientation=90)
    r = GridRouter(ctx, QUIET)
    probe = BoundingBox(-0.14, 2.20, 0.14, 2.80)
    # a same-net shape 0.02um to the right of the probe, bridged by nothing
    ctx.add_obstacle(Obstacle(layer="met2",
                              bbox=BoundingBox(0.16, 2.00, 1.00, 3.00),
                              owner="B", kind="device_geometry", net="N1"))
    r._shape_cache = {}
    unbridged = r._metal_legal(probe, "N1", ["met2"])
    # the same probe, once same-net metal spans the whole facing slot and
    # merges the two into one conductor
    ctx.add_obstacle(Obstacle(layer="met2",
                              bbox=BoundingBox(-0.30, 2.10, 1.00, 2.90),
                              owner="B", kind="device_geometry", net="N1"))
    r._shape_cache = {}
    bridged = r._metal_legal(probe, "N1", ["met2"])
    # ... and a foreign-net shape in that same position stays illegal, bridge
    # or no bridge: the exemption is about merged geometry, never about being
    # near enough to something friendly
    ctx.add_obstacle(Obstacle(layer="met2",
                              bbox=BoundingBox(-1.00, 3.00, 1.00, 3.20),
                              owner="C", kind="device_geometry", net="N2"))
    r._shape_cache = {}
    foreign = r._metal_legal(probe, "N1", ["met2"])
    ok = (not unbridged) and bridged and (not foreign)
    return report("Test 10 same-net notch",
                  "unbridged same-net slot rejected, bridged one accepted, "
                  "foreign net always rejected",
                  f"unbridged_legal={unbridged} bridged_legal={bridged} "
                  f"foreign_legal={foreign}", ok)


def test_high_degree_net_survives_one_stranded_terminal():
    """One unreachable terminal must not throw away the whole net.

    This is the scalability cliff itself. On a two-pin net, losing one
    terminal leaves nothing to route, so abandoning the net looked correct.
    A supply net grows a terminal per device, so the same rule discarded 17
    vdd terminals because 4 could not land a via -- the blast radius scaled
    with net degree, which is what scales with circuit size.

    The stranded terminal is walled in on every layer, so it genuinely has no
    landing; the other five must still be connected to each other, and the
    net must still be reported as FAILED rather than quietly complete.
    """
    ctx = make_ctx("t11")
    for i in range(5):
        add_terminal(ctx, f"D{i}", "p", "VDD", i * 6.0, 0.0, orientation=90)
    add_terminal(ctx, "WALLED", "p", "VDD", 12.0, 14.0, orientation=90)
    for layer in ("met1", "met2", "met3", "met4", "met5"):
        for bb in (BoundingBox(10.0, 13.6, 11.7, 14.4),
                   BoundingBox(12.3, 13.6, 14.0, 14.4),
                   BoundingBox(10.0, 14.4, 14.0, 15.2),
                   BoundingBox(10.0, 12.8, 14.0, 13.6)):
            ctx.add_obstacle(Obstacle(layer=layer, bbox=bb, owner="CAGE",
                                      kind="blockage", net="OTHER"))
    r, res = route(ctx)
    reached = [k for (k, ch) in r._chosen_access.items() if ch.legal]
    seg_nets = {s.net for s in ctx.segments}
    complete = ctx.routed_nets["VDD"].complete if "VDD" in ctx.routed_nets else False
    v = conn.verify(ctx)
    ok = ("VDD" in seg_nets              # the reachable terminals ARE routed
          and len(reached) >= 5
          and "VDD" in res["failed"]     # ... and the loss is still reported
          and not complete
          and v["shorts"] == 0)
    return report("Test 11 partial route of a high-degree net",
                  "reachable terminals routed, stranded one reported, "
                  "net not marked complete",
                  f"segments_for_VDD={'VDD' in seg_nets} legal={len(reached)}/6 "
                  f"failed={res['failed']} complete={complete} "
                  f"shorts={v['shorts']}", ok)


def test_top_metal_rules_match_the_pdk_deck():
    """The top-metal rule table must still agree with the shipped decks.

    glayout's get_grule reports 0.28/0.30 for every GF180 metal including the
    top one; the foundry decks do not agree, and they are what sign the design
    off. Those numbers are therefore carried in pdk_rules.TOP_METAL_RULES --
    so this test re-reads the decks and fails if the table drifts from them,
    rather than letting a hardcoded constant quietly rot.
    """
    import re as _re
    from mbg.pdk_rules import TOP_METAL_RULES, top_metal_rules
    pdkpath = os.environ["PDKPATH"]
    deck = os.path.join(pdkpath, "libs.tech", "klayout", "tech", "drc",
                        "rule_decks", "metaltop.rb")
    tech = os.path.join(pdkpath, "libs.tech", "magic",
                        f"{os.environ.get('PDK', 'gf180mcuD')}.tech")
    if not os.path.isfile(deck) or not os.path.isfile(tech):
        return report("Test 12 top-metal rules vs deck",
                      "decks present", f"deck={os.path.isfile(deck)} "
                      f"tech={os.path.isfile(tech)}", False)

    text = open(deck).read()
    # each "when '<thickness>'" branch carries its own MT.1 / MT.2a numbers
    found = {}
    for m in _re.finditer(r"when ((?:'[0-9]+K'(?:,\s*)?)+)(.*?)(?=\n  when |\Z)",
                          text, _re.S):
        widths = _re.search(r"width\((\d+\.\d+)\.um", m.group(2))
        spaces = _re.search(r"space\((\d+\.\d+)\.um", m.group(2))
        if not (widths and spaces):
            continue
        for th in _re.findall(r"'([0-9]+K)'", m.group(1)):
            found[th] = (float(widths.group(1)), float(spaces.group(1)))

    bad = []
    for th, (w, sp) in found.items():
        want = TOP_METAL_RULES.get(th)
        if want is None:
            bad.append(f"{th}: deck has it, TOP_METAL_RULES does not")
        elif (want["min_width"], want["min_spacing"]) != (w, sp):
            bad.append(f"{th}: deck says {w}/{sp}, table says "
                       f"{want['min_width']}/{want['min_spacing']}")

    # and the Magic techfile, in centi-nanometres, for the project's variant
    top_layer, rules_for_variant = top_metal_rules(os.environ.get("PDK", "gf180mcuD"))
    mw = _re.search(r"width \*m5,rm5 (\d+)", open(tech).read())
    if mw and rules_for_variant:
        magic_um = int(mw.group(1)) / 1000.0
        if abs(magic_um - rules_for_variant["min_width"]) > 1e-9:
            bad.append(f"magic techfile says {magic_um}, table says "
                       f"{rules_for_variant['min_width']}")

    ok = not bad and bool(found)
    return report("Test 12 top-metal rules vs deck",
                  "TOP_METAL_RULES agrees with metaltop.rb and the magic tech",
                  f"deck_branches={found} mismatches={bad}", ok)


def test_segment_width_respects_its_layer():
    """Every emitted segment must be at least its own layer's minimum width.

    width_for(net) is chosen before a path exists, so it returns the access
    layer's width for the whole net. Minimum width is a per-layer rule, and
    GF180's top metal is the one that differs (0.44um vs 0.28um). A net routed
    at the access width and then sent over met5 is a guaranteed MT.1
    violation -- which is exactly what both DRC engines reported once the
    supply nets started reaching met5.
    """
    from mbg.pdk_rules import get_rules
    ctx = make_ctx("t13")
    # far apart, with the lower layers walled off, so the router must climb
    add_terminal(ctx, "A", "p", "N1", 0.0, 0.0, orientation=0)
    add_terminal(ctx, "B", "p", "N1", 30.0, 0.0, orientation=180)
    for layer in ("met3", "met4"):
        ctx.add_obstacle(Obstacle(layer=layer,
                                  bbox=BoundingBox(12.0, -30.0, 16.0, 30.0),
                                  owner="WALL", kind="blockage"))
    _r, res = route(ctx)
    rules = get_rules(gf180)
    thin = [(s.layer, s.width, rules.min_width(s.layer)) for s in ctx.segments
            if s.width < rules.min_width(s.layer) - 1e-9]
    by_layer = sorted({s.layer for s in ctx.segments})
    ok = not thin and "met5" in by_layer and res["failed"] == []
    return report("Test 13 per-layer segment width",
                  "no segment thinner than its layer minimum, met5 exercised",
                  f"layers={by_layer} too_thin={thin} failed={res['failed']}", ok)




def test_grid_pitch_is_per_layer():
    """One layer's rule must not set the pitch for layers that do not share it.

    The pitch decides the area of every design. Combining the widest minimum
    width found on any routing layer with the largest spacing found on any
    routing layer describes a wire that exists on no layer -- and once met5's
    minimum width was corrected to the foundry deck's 0.44um, that
    cross-product pushed the pitch from 0.87um to 1.34um on every design,
    including ones that never touch met5.

    Two things must hold: dropping met5 from the layer list must return the
    pitch to the value the met3/met4 rules alone justify, and a stack whose
    layers all share one rule must give the same answer under either formula.
    """
    from mbg.pdk_rules import get_rules
    from mbg.router import grid_params
    ctx = make_ctx("t14")
    ctx.device_bboxes["d"] = BoundingBox(0, 0, 10, 10)
    rules = get_rules(gf180)
    with_top = grid_params(ctx, RouterConfig(routing_layers=["met3", "met4", "met5"]))[1]
    no_top = grid_params(ctx, RouterConfig(routing_layers=["met3", "met4"]))[1]

    # what met3/met4 alone actually need, computed from the rules directly
    mult = max(RouterConfig().width_multiplier, RouterConfig().power_width_multiplier)
    base = rules.routing_width("met3", mult)
    want = max(max(base, rules.min_width(l)) + rules.min_spacing(l)
               for l in ("met3", "met4"))
    # And the router must lay wire on exactly the grid grid_params describes.
    # power.py snaps its rail via drops with snap_to_grid(), which is
    # grid_params(); while GridRouter kept a second formula of its own, the
    # two drifted apart and the rails landed off the router's grid. That is
    # the one thing the pitch cannot keep legal, and both DRC engines said so.
    add_terminal(ctx, "A", "p", "N1", 0.0, 0.0)
    add_terminal(ctx, "B", "p", "N1", 12.0, 0.0, orientation=180)
    cfg = RouterConfig(verbosity=0)
    r = GridRouter(ctx, cfg)
    o_gp, p_gp = grid_params(ctx, cfg)
    same_grid = abs(r.pitch - p_gp) < 1e-12 and r.origin == o_gp

    ok = (abs(no_top - rules.snap(want + rules.manufacturing_grid())) < 1e-9
          and with_top > no_top                      # met5 genuinely is wider
          and with_top < 1.30                        # but not by the old margin
          and same_grid)
    return report("Test 14 per-layer grid pitch",
                  "met3/met4 pitch unaffected by met5's rule, and the router "
                  "uses exactly the grid grid_params reports",
                  f"with_met5={with_top} without={no_top} "
                  f"met3/4_requirement={rules.snap(want + rules.manufacturing_grid())} "
                  f"router_grid_matches={same_grid} "
                  f"(router {r.origin}@{r.pitch} vs {o_gp}@{p_gp})", ok)




def test_notch_against_net_owned_metal_is_filled():
    """A route may end short of its own net's NON-segment metal.

    Power-rail via drops and device tap metal are registered as net-owned
    obstacles, never as segments. The notch-filling pass only looked at
    segments, so a route stopping a fraction of a micron from a rail drop of
    the SAME net left a sub-spacing gap nothing could see -- reported by both
    engines as "Metal3 spacing < 0.28um" on the inverter, the ring oscillator
    and the RC filter. It was latent rather than new: the gap only opens at
    some grid alignments, and the historical routing pitch happened to miss it.

    The second half matters as much as the first: a fill must never bridge
    into another net. That would manufacture a short and hide it under a
    DRC-clean result, which is worse than the notch.
    """
    from mbg.router import _same_net_notch_fills
    from mbg.design_context import Segment

    def build(pad_net, intruder=None):
        ctx = make_ctx("t15")
        add_terminal(ctx, "A", "p", "N1", 0.0, 0.0)
        # a met3 route, and a rail-drop pad 0.27um above it (spacing is 0.30)
        ctx.segments.append(Segment(net="N1", layer="met3",
                                    x1=0.0, y1=0.0, x2=4.0, y2=0.0, width=0.56))
        ctx.add_obstacle(Obstacle(
            layer="met3", bbox=BoundingBox(1.0, 0.55, 1.5, 1.20),
            owner=f"RAIL_{pad_net}", kind="power_via", net=pad_net))
        if intruder is not None:
            ctx.add_obstacle(Obstacle(layer="met3", bbox=intruder,
                                      owner="OTHER", kind="blockage", net="N2"))
        return len(_same_net_notch_fills(ctx, QUIET))

    same_net = build("N1")
    # a pad belonging to a different net is not this net's metal at all, so it
    # is never a fill partner
    other_net = build("N2")
    # and a same-net gap with a FOREIGN shape standing inside it must not be
    # filled either: bridging there would manufacture a short and then hide it
    # behind a DRC-clean result, which is worse than the notch
    with_intruder = build("N1", intruder=BoundingBox(1.1, 0.35, 1.3, 0.48))

    ok = same_net >= 1 and other_net == 0 and with_intruder == 0
    return report("Test 15 notch against net-owned metal",
                  "same-net gap filled; foreign pad not a partner; a gap with "
                  "foreign metal inside it left alone",
                  f"same_net={same_net} other_net={other_net} "
                  f"with_intruder={with_intruder}", ok)




def test_notch_predicate_accepts_a_joint_merge_and_an_exact_abutment():
    """The tap-ring exemption must survive the shapes real devices produce.

    Requiring ONE same-net shape to contain the whole gap was too strict in
    two ways that a multi-finger device hits routinely: a ring corner arrives
    as two abutting rectangles that jointly cover a gap neither covers alone,
    and grid-snapped router metal meeting device metal EXACTLY has a
    zero-width gap and no third shape to act as a witness. Both are one
    polygon after merge; rejecting them re-strands the terminal, which is the
    original failure one level deeper.

    The rejecting cases are checked in the same breath, because an exemption
    that accepts everything is worse than one that accepts nothing.
    """
    from mbg.design_context import Net, Device
    from mbg.router import _rects_cover

    def probe(shapes, box=BoundingBox(0, 0, 1.0, 1.0), net="N1"):
        ctx = make_ctx("t16")
        add_terminal(ctx, "A", "p", "N1", 0.0, 0.0, layer="met2")
        for bb, n in shapes:
            ctx.add_obstacle(Obstacle(layer="met2", bbox=bb, owner="R",
                                      kind="device_geometry", net=n))
        r = GridRouter(ctx, QUIET)
        r._shape_cache = {}
        return r._metal_legal(box, net, ["met2"])

    joint = probe([(BoundingBox(0, 0, 1.3, 1.0), "N1"),
                   (BoundingBox(0, 1.0, 1.3, 2.0), "N1"),
                   (BoundingBox(1.3, 0, 2.3, 2.0), "N1")])
    abutting = probe([(BoundingBox(1.0, 0, 2.0, 1.0), "N1")])
    real_notch = probe([(BoundingBox(1.02, 0, 2.0, 1.0), "N1")])
    foreign = probe([(BoundingBox(1.0, 0, 2.0, 1.0), "N2")])

    cover_ok = _rects_cover(BoundingBox(0, 0, 2, 2),
                            [BoundingBox(0, 0, 1, 2), BoundingBox(1, 0, 2, 2)])
    cover_hole = _rects_cover(BoundingBox(0, 0, 2, 2),
                              [BoundingBox(0, 0, 1, 2), BoundingBox(1.1, 0, 2, 2)])

    ok = (joint and abutting and not real_notch and not foreign
          and cover_ok and not cover_hole)
    return report("Test 16 joint merge and exact abutment",
                  "jointly covered gap and zero-width gap accepted; "
                  "a real gap and any foreign net rejected",
                  f"joint={joint} abutting={abutting} "
                  f"real_notch={real_notch} foreign={foreign} "
                  f"cover_ok={cover_ok} cover_hole={cover_hole}", ok)


def test_a_congestion_failure_keeps_what_it_already_routed():
    """A blocked terminal must not discard the ones already connected.

    The stranded-terminal path was fixed first, but the Steiner growth loop
    had the same all-or-nothing shape: if a LATER terminal group could not be
    reached, route_net returned None and threw away every group attached
    earlier in the same call. That is the half driven by congestion rather
    than device geometry, so it is the half that grows with design size.
    """
    ctx = make_ctx("t17")
    for i, x in enumerate((0.0, 8.0, 16.0)):
        add_terminal(ctx, f"D{i}", "p", "N1", x, 0.0, orientation=90)
    add_terminal(ctx, "WALLED", "p", "N1", 8.0, 16.0, orientation=90)
    for layer in ("met1", "met2", "met3", "met4", "met5"):
        for bb in (BoundingBox(6.0, 15.6, 7.7, 16.4),
                   BoundingBox(8.3, 15.6, 10.0, 16.4),
                   BoundingBox(6.0, 16.4, 10.0, 17.2),
                   BoundingBox(6.0, 14.8, 10.0, 15.6)):
            ctx.add_obstacle(Obstacle(layer=layer, bbox=bb, owner="CAGE",
                                      kind="blockage", net="OTHER"))
    _r, res = route(ctx)
    v = conn.verify(ctx)
    routed_geometry = [s for s in ctx.segments if s.net == "N1"]
    complete = ctx.routed_nets["N1"].complete if "N1" in ctx.routed_nets else False
    ok = (routed_geometry               # the reachable ones ARE connected
          and "N1" in res["failed"]     # the loss is still reported
          and not complete              # and the net is not called routed
          and v["shorts"] == 0)
    return report("Test 17 congestion failure keeps partial geometry",
                  "reachable terminals stay routed, failure still reported",
                  f"segments={len(routed_geometry)} failed={res['failed']} "
                  f"complete={complete} shorts={v['shorts']}", ok)


def test_a_terminal_with_no_access_point_fails_the_internal_gate():
    """A terminal that never reached the router is not silently clean.

    check_opens works on shapes, and a terminal with no access point produces
    no shape -- so it joins no cluster and no open is ever reported for it.
    compare_with_netlist is what sees that class, and its verdict was computed,
    printed, and then left out of the pass/fail decision, so a completely
    unconnected device terminal could pass the internal check and let external
    LVS be the first thing that noticed.
    """
    from mbg.design_context import Device, Net, PinAccessPoint
    ctx = make_ctx("t18")
    ctx.add_net(Net(name="vss"))
    ctx.add_net(Net(name="n1"))
    dev = Device(name="A", model="nfet_03v3", kind="nmos")
    dev.terminals = {"drain": "n1", "gate": "n1", "source": "vss", "body": "vss"}
    ctx.add_device(dev)
    for term, x in (("drain", 0.0), ("gate", 2.0), ("source", 4.0)):
        ctx.add_access_point(PinAccessPoint(
            instance="A", terminal=term, net=dev.terminals[term],
            layer="met2", x=x, y=0.0, orientation=0.0, width=0.5))
    ctx.device_bboxes["A"] = BoundingBox(-1, -1, 5, 1)
    v = conn.verify(ctx)
    ok = (v["opens"] == 0 and v["missing_access"] == 1 and not v["clean"]
          and "A.body" in " ".join(v["missing_access_details"]))
    return report("Test 18 terminal with no access point",
                  "reported and fails the internal gate even with 0 opens",
                  f"opens={v['opens']} missing={v['missing_access']} "
                  f"clean={v['clean']} details={v['missing_access_details']}", ok)


ALL = [test_single_net, test_crossing_nets, test_via_conflict,
       test_blocked_path, test_congested_channel, test_differential_pair,
       test_current_mirror, test_deep_nwell,
       test_escape_on_tap_ring, test_same_net_notch_still_rejected,
       test_high_degree_net_survives_one_stranded_terminal,
       test_top_metal_rules_match_the_pdk_deck,
       test_segment_width_respects_its_layer,
       test_grid_pitch_is_per_layer,
       test_notch_against_net_owned_metal_is_filled,
       test_notch_predicate_accepts_a_joint_merge_and_an_exact_abutment,
       test_a_congestion_failure_keeps_what_it_already_routed,
       test_a_terminal_with_no_access_point_fails_the_internal_gate]

if __name__ == "__main__":
    results = []
    for t in ALL:
        try:
            results.append(t())
        except AssertionError:
            results.append(False)          # report() already printed it
        except Exception as e:
            import traceback
            print(f"FAIL  {t.__name__} raised {type(e).__name__}: {e}")
            traceback.print_exc()
            results.append(False)
        print()
    print(f"=== {sum(results)}/{len(results)} PASS ===")
    sys.exit(0 if all(results) else 1)
