"""Complexity ladder: where does this framework actually stop working?

Two things are measured here, and they answer different questions.

**Metrics** (always run, milliseconds) characterise every regression netlist:
device count, net count, max/avg net degree, matched groups, and how many
DISTINCT (W, L) pairs the design uses. That last column is the one that
matters, and it is the reason this file exists.

When the 12-MOS clocked comparator was found to fail, the obvious readings
were "too many devices" and "supply net too highly connected". Both are wrong,
and the numbers say so plainly: the 11-MOS StrongArm comparator has the SAME
maximum net degree -- 12 device terminals on vdd, 16 counting the power-rail
taps -- and it passed throughout. What separated them was device GEOMETRY.
Every one of the seven original reference designs used one or two distinct
(W, L) pairs; StrongArm used exactly one, eleven times. The clocked comparator
uses seven across twelve devices, which is what real analog sizing looks like.
Heterogeneous devices produce heterogeneous tap rings and row heights, and it
was that placement -- not the device count -- in which some body terminals
could find no legal via landing.

So no scalar threshold predicts failure, and a ladder that only grows device
count would have kept missing it. The ladder has to widen COVERAGE: more
topologies, more sizing diversity, more placements.

**Layout** (opt-in, minutes) runs each rung through the real flow.

    python tests/test_complexity_ladder.py              # metrics only
    MBG_LADDER=layout python tests/test_complexity_ladder.py
    MBG_LADDER=full   python tests/test_complexity_ladder.py   # + DRC/LVS

`layout` and `full` are opt-in because they invoke gLayout, Magic, netgen and
KLayout; the whole ladder at `full` costs several minutes, which does not
belong in a suite people run on every edit.
"""

import os
import sys
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "tests"))

os.environ.setdefault("PDK_ROOT", os.path.expanduser("~/.volare"))
os.environ.setdefault("PDK", "gf180mcuD")
os.environ.setdefault("PDKPATH", os.path.join(os.environ["PDK_ROOT"],
                                              os.environ["PDK"]))

import fixtures                                                # noqa: E402

#: How many via drops power.py puts on each supply rail. Counted into the
#: effective degree because they are real terminals the router must reach.
RAIL_TAPS = 4

MODE = os.environ.get("MBG_LADDER", "metrics").lower()


def complexity(name):
    """Structural metrics for one netlist. No layout, no PDK tools."""
    from glayout import gf180
    from mbg.spice_parser import build_design_context, parse_netlist_with_pdk
    gf180.activate()
    ctx = build_design_context(parse_netlist_with_pdk(fixtures.load(name)), gf180)
    degrees = {n: len(net.terminals) for n, net in ctx.nets.items()}
    supply = set(ctx.power_nets) | set(ctx.ground_nets)
    effective = {n: d + (RAIL_TAPS if n in supply else 0)
                 for n, d in degrees.items()}
    sizes = {(d.width, d.length) for d in ctx.devices.values() if d.is_mos}
    return {
        "name": name,
        "mos": sum(1 for d in ctx.devices.values() if d.is_mos),
        "devices": len(ctx.devices),
        "nets": len(ctx.nets),
        "max_degree": max(degrees.values()) if degrees else 0,
        "max_degree_with_rails": max(effective.values()) if effective else 0,
        "avg_degree": (sum(degrees.values()) / len(degrees)) if degrees else 0.0,
        "groups": len(ctx.matching_groups),
        "size_diversity": len(sizes),
    }


def run_layout(name, with_checks):
    """One rung through the real flow. Returns a result row."""
    from mbg.pipeline import spice_to_gds_ctx, spice_to_gds_with_checks
    netlist = fixtures.load(name)
    t0 = time.time()
    if with_checks:
        r = spice_to_gds_with_checks(netlist, verbosity=0)
        signoff = (r.get("drc_signoff") or {}).get("verdict", "NOT RUN")
        drc = "CLEAN" if r["drc"].get("clean") else "FAIL"
        lvs = "MATCH" if r["lvs"].get("match") else "MISMATCH"
    else:
        r = spice_to_gds_ctx(netlist, verbosity=0)
        signoff = drc = lvs = "-"
    v = r.get("verification") or {}
    m = r.get("metrics") or {}
    return {
        "name": name, "seconds": time.time() - t0,
        "opens": v.get("opens", -1), "shorts": v.get("shorts", -1),
        "routed": m.get("routed_nets", -1), "total": m.get("total_nets", -1),
        "wire": m.get("wire_length", 0.0), "vias": m.get("via_count", 0),
        "drc": drc, "signoff": signoff, "lvs": lvs,
    }


def _workspace():
    ws = os.environ.get("MBG_TEST_OUTPUT") or str(REPO / "outputs" / "ladder")
    os.makedirs(ws, exist_ok=True)
    return ws


class TestComplexityMetrics(unittest.TestCase):
    """Always-on: characterise every netlist and print the ladder."""

    def test_ladder_is_ordered_and_printed(self):
        rows = sorted((complexity(n) for n in fixtures.names()),
                      key=lambda r: (r["mos"], r["max_degree_with_rails"]))
        print(f"\n  {'design':18s} {'MOS':>4s} {'nets':>5s} {'maxdeg':>7s} "
              f"{'+rails':>7s} {'avgdeg':>7s} {'groups':>7s} {'sizes':>6s}")
        print("  " + "-" * 66)
        for r in rows:
            print(f"  {r['name']:18s} {r['mos']:4d} {r['nets']:5d} "
                  f"{r['max_degree']:7d} {r['max_degree_with_rails']:7d} "
                  f"{r['avg_degree']:7.2f} {r['groups']:7d} "
                  f"{r['size_diversity']:6d}")
        self.assertGreaterEqual(len(rows), 8)
        for r in rows:
            with self.subTest(design=r["name"]):
                self.assertGreater(r["nets"], 0)
                self.assertGreaterEqual(r["max_degree_with_rails"], r["max_degree"])

    def test_the_ladder_covers_more_than_one_device_geometry(self):
        """The suite must contain a design with heterogeneous sizing.

        This is the coverage gap that let the comparator through: with every
        design built from one or two (W, L) pairs, no test ever produced the
        kind of irregular floorplan in which a terminal loses its via landing.
        If this assertion ever fails, the ladder has drifted back to uniform
        arrays and stopped covering the case it exists for.
        """
        diversity = {n: complexity(n)["size_diversity"] for n in fixtures.names()}
        best = max(diversity.values())
        self.assertGreaterEqual(
            best, 4,
            "no regression netlist uses 4+ distinct (W, L) pairs; the ladder "
            f"has lost its heterogeneous-sizing coverage. Have: {diversity}")

    def test_device_count_alone_does_not_order_difficulty(self):
        """Guard the finding itself, so nobody re-derives 'too many devices'.

        strongarm (11 MOS) and cmp_2stage_clk (12 MOS) have the same maximum
        net degree. If a future change makes them differ, the explanation in
        this file's docstring needs revisiting rather than quietly rotting.
        """
        sa, cmp_ = complexity("strongarm"), complexity("cmp_2stage_clk")
        self.assertEqual(sa["max_degree"], cmp_["max_degree"])
        self.assertLess(sa["size_diversity"], cmp_["size_diversity"])


@unittest.skipUnless(MODE in ("layout", "full"),
                     "set MBG_LADDER=layout or MBG_LADDER=full to run the "
                     "real flow (minutes, needs gLayout + PDK tools)")
class TestLadderLayout(unittest.TestCase):
    """Opt-in: take every rung through layout, and report a capability table."""

    @classmethod
    def setUpClass(cls):
        cls.cwd = os.getcwd()
        os.chdir(_workspace())
        cls.rows = []

    @classmethod
    def tearDownClass(cls):
        os.chdir(cls.cwd)
        if not cls.rows:
            return
        print(f"\n  {'design':18s} {'MOS':>4s} {'nets':>5s} {'maxdeg':>7s} "
              f"{'routed':>8s} {'opens':>6s} {'shorts':>7s} "
              f"{'DRC':>6s} {'signoff':>9s} {'LVS':>9s} {'sec':>7s}")
        print("  " + "-" * 96)
        for c, r in cls.rows:
            print(f"  {r['name']:18s} {c['mos']:4d} {c['nets']:5d} "
                  f"{c['max_degree_with_rails']:7d} "
                  f"{str(r['routed']) + '/' + str(r['total']):>8s} "
                  f"{r['opens']:6d} {r['shorts']:7d} {r['drc']:>6s} "
                  f"{r['signoff']:>9s} {r['lvs']:>9s} {r['seconds']:7.1f}")

    def test_every_rung_lays_out_with_clean_internal_connectivity(self):
        full = MODE == "full"
        order = sorted(fixtures.names(),
                       key=lambda n: complexity(n)["mos"])
        for name in order:
            with self.subTest(design=name):
                c = complexity(name)
                r = run_layout(name, with_checks=full)
                type(self).rows.append((c, r))
                self.assertEqual(r["opens"], 0, f"{name}: {r['opens']} open(s)")
                self.assertEqual(r["shorts"], 0, f"{name}: {r['shorts']} short(s)")
                self.assertEqual(r["routed"], r["total"],
                                 f"{name}: only {r['routed']}/{r['total']} nets routed")
                if full:
                    self.assertEqual(r["lvs"], "MATCH", f"{name}: LVS {r['lvs']}")
                    self.assertEqual(r["signoff"], "PASS",
                                     f"{name}: DRC sign-off {r['signoff']}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
