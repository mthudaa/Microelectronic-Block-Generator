#!/usr/bin/env python3
"""End-to-end regression over the reference analog blocks.

Drives the public pipeline entry point, spice_to_gds_with_checks(), and
reports DRC / LVS for each design.

Run:  python tests/test_all_designs.py
      python tests/test_all_designs.py --only 5T-OTA
"""

import os
import sys
import time


def _repo_src():
    """Walk up from this file until the src/mbg package is found."""
    d = os.path.dirname(os.path.abspath(__file__))
    for _ in range(8):
        cand = os.path.join(d, "src")
        if os.path.isdir(os.path.join(cand, "mbg")):
            return cand
        d = os.path.dirname(d)
    raise RuntimeError("could not locate src/mbg from " + __file__)


sys.path.insert(0, _repo_src())

os.environ['PDK_ROOT'] = os.environ.get('PDK_ROOT', os.path.expanduser('~/.volare'))
os.environ['PDK'] = os.environ.get('PDK', 'gf180mcuD')
pdkpath = f"{os.environ['PDK_ROOT']}/{os.environ['PDK']}"
os.environ['PDKPATH'] = os.environ.get('PDKPATH', pdkpath)
os.environ['STD_CELL_LIBRARY'] = os.environ.get('STD_CELL_LIBRARY', 'gf180mcu_fd_sc_mcu7t5v0')

from mbg.pipeline import spice_to_gds_with_checks

PDK_LIB = os.path.join(os.environ['PDKPATH'], 'libs.tech', 'ngspice', 'sm141064.ngspice')

# Designs come from tests/netlists/*.spice via tests/fixtures.py. They used to
# be a dict literal here, which meant the notebook's own circuit -- the one
# that actually found the complexity boundary -- was not reachable from any
# test. Ordered smallest first so a failure reads as a scalability boundary
# rather than an unordered list.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fixtures                                             # noqa: E402

ORDER = ["inverter", "ring_osc_3", "ota_5t", "ota_bb", "vref_1v2",
         "rc_filter", "strongarm", "cmp_2stage_clk"]

TITLES = {
    "inverter": "Inverter",
    "ring_osc_3": "3-stage Ring Oscillator",
    "ota_5t": "5T-OTA",
    "ota_bb": "DNW Body-Biased OTA",
    "vref_1v2": "VREF Beta-Multiplier",
    "rc_filter": "RC Filter (native passives)",
    "strongarm": "StrongArm-Comparator",
    "cmp_2stage_clk": "2-Stage Clocked Comparator (12 MOS)",
}

_missing = set(fixtures.names()) - set(ORDER)
assert not _missing, f"netlist fixtures not listed in ORDER: {sorted(_missing)}"

DESIGNS = {TITLES[n]: fixtures.load(n) for n in ORDER}

def _workspace():
    """Run inside a results directory.

    spice_to_gds_with_checks() writes <cwd>/<cell_name>/, so running this
    suite from the repository root used to scatter design directories across
    it. Everything now lands under outputs/regression/ instead.
    """
    root = os.path.dirname(_repo_src())
    ws = os.environ.get("MBG_TEST_OUTPUT") or os.path.join(root, "outputs", "regression")
    os.makedirs(ws, exist_ok=True)
    return ws


def main():
    print("============================================================")
    print("  VERIFYING DESIGNS")
    print("============================================================")

    ws = _workspace()
    os.chdir(ws)
    print(f"  output directory: {ws}")

    results = {}

    for name, netlist in DESIGNS.items():
        print(f"\n--- Testing: {name} ---")
        t0 = time.time()
        try:
            res = spice_to_gds_with_checks(netlist)
            t_elapsed = time.time() - t0
            results[name] = res
            print(f"  Routing time: {t_elapsed:.2f}s")
            print(f"  Magic DRC:    {res['drc'].get('summary', '?')}")
            sg = res.get("drc_signoff") or {}
            for eng in (sg.get("results") or []):
                if eng.get("engine") == "klayout":
                    top = sorted((eng.get("rules") or {}).items(),
                                 key=lambda kv: -kv[1])[:3]
                    detail = "  " + ", ".join(f"{r} x{n}" for r, n in top) if top else ""
                    print(f"  KLayout DRC:  {eng.get('status')} "
                          f"({eng.get('violations')} violation(s)){detail}")
            print(f"  DRC sign-off: {sg.get('verdict', 'NOT RUN')}")
            print(f"  LVS:          {'MATCH' if res['lvs'].get('match') else 'MISMATCH'}")
        except Exception as e:
            print(f"  FAILED: {e}")
            results[name] = {'drc': {}, 'lvs': {}}

    print("\n============================================================")
    print("  FINAL SUMMARY")
    print("============================================================")
    def _kl(res):
        for eng in ((res.get("drc_signoff") or {}).get("results") or []):
            if eng.get("engine") == "klayout":
                return eng.get("status", "?"), eng.get("violations", -1)
        return "NOT RUN", -1

    w = max((len(n) for n in results), default=10)
    print(f"  {'design':<{w}}  {'Magic':<7} {'KLayout':<16} {'sign-off':<22} "
          f"{'LVS':<9} internal")
    print("  " + "-" * (w + 62))
    for name, res in results.items():
        magic = "CLEAN" if res["drc"].get("clean") else "FAIL"
        ks, kv = _kl(res)
        klay = f"{ks}" + (f" ({kv})" if kv > 0 else "")
        sign = (res.get("drc_signoff") or {}).get("verdict", "NOT RUN")
        lvs = "MATCH" if res["lvs"].get("match") else "MISMATCH"
        v = res.get("verification") or {}
        internal = ("CLEAN" if v.get("clean") else
                    f"opens={v.get('opens', '?')} shorts={v.get('shorts', '?')} "
                    f"missing={v.get('missing_access', '?')}")
        print(f"  {name:<{w}}  {magic:<7} {klay:<16} {sign:<22} {lvs:<9} {internal}")
    print("============================================================")

    n = len(results)
    magic_lvs = sum(1 for r in results.values() if _passed(r))
    signoff = sum(1 for r in results.values()
                  if (r.get("drc_signoff") or {}).get("verdict") == "PASS")
    print(f"  {magic_lvs}/{n} designs pass all four legs (Magic + KLayout + LVS + internal)")
    print(f"  {signoff}/{n} designs pass dual-DRC sign-off (Magic + KLayout)")

    # Reported separately on purpose. Magic-only "7/7" reads as a complete
    # result while hiding a design that fails the foundry deck, which is
    # exactly the false confidence dual-DRC exists to remove.
    if signoff < n:
        print("\n  Designs failing dual-DRC sign-off:")
        for name, res in results.items():
            sg = res.get("drc_signoff") or {}
            if sg.get("verdict") != "PASS":
                ks, kv = _kl(res)
                print(f"    {name}: {sg.get('verdict', 'NOT RUN')} — "
                      f"{sg.get('reason', '')[:70]}")
        print("  (see outputs/regression/<design>/verification/drc_summary.json)")

    # Magic + LVS alone was the old criterion, and it is exactly the false
    # confidence dual-DRC exists to remove: it passes a design the foundry
    # deck rejects. All four legs are the gate now -- the same four
    # spice_to_gds_with_checks() itself uses for all_pass, so this script and
    # the library can no longer disagree about what "passing" means.
    ok = all(_passed(r) for r in results.values())
    return 0 if ok and results else 1


def _passed(res):
    """The four legs of sign-off, as pipeline.all_pass defines them."""
    return bool(res.get("drc", {}).get("clean")
                and (res.get("drc_signoff") or {}).get("verdict") == "PASS"
                and res.get("lvs", {}).get("match")
                and (res.get("verification") or {}).get("clean"))


# ── pytest entry point ────────────────────────────────────────────────
#
# This file used to define only main(), so `pytest tests/` collected ZERO
# items from it and never ran the end-to-end regression at all -- including
# the fixture that found the complexity boundary. It is opt-in rather than
# always-on because it drives real gLayout, Magic, KLayout and netgen and
# takes minutes; the gate matches the env-var convention the rest of the
# suite already uses for tool-dependent tests.

import unittest                                            # noqa: E402


@unittest.skipUnless(os.environ.get("MBG_RUN_DESIGNS") == "1",
                     "opt-in: real gLayout + Magic + KLayout + netgen, "
                     "several minutes. Set MBG_RUN_DESIGNS=1.")
class TestReferenceDesigns(unittest.TestCase):
    """Every reference design, through the real flow, all four legs."""

    def test_every_design_signs_off(self):
        ws = _workspace()
        cwd = os.getcwd()
        os.chdir(ws)
        try:
            for name, netlist in DESIGNS.items():
                with self.subTest(design=name):
                    res = spice_to_gds_with_checks(netlist)
                    v = res.get("verification") or {}
                    self.assertTrue(res["drc"].get("clean"),
                                    f"{name}: Magic DRC {res['drc'].get('summary')}")
                    self.assertEqual(
                        (res.get("drc_signoff") or {}).get("verdict"), "PASS",
                        f"{name}: {(res.get('drc_signoff') or {}).get('reason')}")
                    self.assertTrue(res["lvs"].get("match"), f"{name}: LVS mismatch")
                    self.assertTrue(v.get("clean"),
                                    f"{name}: internal connectivity "
                                    f"opens={v.get('opens')} shorts={v.get('shorts')} "
                                    f"missing={v.get('missing_access')}")
        finally:
            os.chdir(cwd)


class TestDesignInventory(unittest.TestCase):
    """Cheap checks that always run: the harness is wired to the fixtures."""

    def test_every_fixture_is_covered(self):
        self.assertEqual(sorted(ORDER), fixtures.names())
        self.assertEqual(len(DESIGNS), len(ORDER))

    def test_the_complexity_fixture_is_present(self):
        # the design that found the boundary must never silently drop out
        self.assertIn("cmp_2stage_clk", ORDER)
        self.assertIn(".subckt cmp_2stage_clk",
                      fixtures.load("cmp_2stage_clk"))


if __name__ == "__main__":
    sys.exit(main())
