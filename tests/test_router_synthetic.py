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
    print(f"{'PASS' if ok else 'FAIL'}  {name}\n"
          f"      expected: {expected}\n      actual:   {actual}")
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


ALL = [test_single_net, test_crossing_nets, test_via_conflict,
       test_blocked_path, test_congested_channel, test_differential_pair,
       test_current_mirror, test_deep_nwell]

if __name__ == "__main__":
    results = []
    for t in ALL:
        try:
            results.append(t())
        except Exception as e:
            import traceback
            print(f"FAIL  {t.__name__} raised {type(e).__name__}: {e}")
            traceback.print_exc()
            results.append(False)
        print()
    print(f"=== {sum(results)}/{len(results)} PASS ===")
    sys.exit(0 if all(results) else 1)
