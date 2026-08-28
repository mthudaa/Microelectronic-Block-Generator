"""N-well spacing between PFETs — the placement side of NW.2b_LV.

Every gLayout PMOS carries its own n-well, so two PFETs side by side are two
wells. The GF180 deck checks well spacing by EXTRACTED CONNECTIVITY
(rule_decks/nwell.rb: `conn_space(nwell, 0.6, 1.4, euclidian)`): joined wells
get 0.6um (NW.2a_LV), isolated wells get 1.4um (NW.2b_LV). Placement cannot
know whether the supply will reach a well tap, so it assumes the strict case.

The default `intra_cluster_gap` is 1.0um — BELOW 1.4 — which is exactly how a
matched PFET pair lands in NW.2b_LV.
"""

import os
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
os.environ.setdefault("PDK_ROOT", os.path.expanduser("~/.volare"))
os.environ.setdefault("PDK", "gf180mcuD")
os.environ.setdefault("PDKPATH", os.path.join(os.environ["PDK_ROOT"],
                                              os.environ["PDK"]))

NETLIST = """.lib "{PDK_LIB}" typical
.subckt nwtest vdd vss inp inm out
XM1 out inp tail vss nfet_03v3 W=2u L=1u
XM2 o2 inm tail vss nfet_03v3 W=2u L=1u
XM3 out out vdd vdd pfet_03v3 W=4u L=1u
XM4 o2 out vdd vdd pfet_03v3 W=4u L=1u
XM5 tail inm vss vss nfet_03v3 W=2u L=1u
.ends
"""


def netlist():
    lib = os.path.join(os.environ["PDKPATH"], "libs.tech", "ngspice",
                       "sm141064.ngspice")
    return NETLIST.replace("{PDK_LIB}", lib)


class TestNWellRule(unittest.TestCase):
    def test_the_rule_comes_from_the_deck_not_a_literal(self):
        from glayout import gf180
        from mbg.pdk_rules import get_rules
        gf180.activate()
        r = get_rules(gf180)
        self.assertAlmostEqual(r.nwell_spacing(), 1.4, places=6)
        self.assertAlmostEqual(r.nwell_spacing(equipotential=True), 0.6,
                               places=6)

    def test_equipotential_is_not_forced_up_to_the_strict_value(self):
        """glayout reports one nwell min_separation (the strict 1.4). Taking
        max() against it would make NW.2a unreachable."""
        from glayout import gf180
        from mbg.pdk_rules import get_rules
        gf180.activate()
        r = get_rules(gf180)
        self.assertLess(r.nwell_spacing(equipotential=True), r.nwell_spacing())


class TestPFETSpacingIsApplied(unittest.TestCase):
    """The measured well-to-well gap, not the device coordinates."""

    FLOOR = 1.5

    @classmethod
    def setUpClass(cls):
        from mbg.pipeline import spice_to_gds_ctx
        from mbg.placement_engine import PlacementConfig
        cls.default = spice_to_gds_ctx(
            netlist(), verbosity=0,
            placement_config=PlacementConfig(verbosity=0))["context"]

    def test_adjacent_pfets_clear_the_deck_rule(self):
        gap = self.default.metrics.get("nwell_min_gap_um")
        self.assertIsNotNone(gap, "n-well gap was never measured")
        self.assertGreaterEqual(gap, 1.4,
                                f"PFET wells {gap}um apart — NW.2b_LV needs 1.4")

    def test_every_island_pair_clears_the_1_5um_floor(self):
        """The floor is 1.5um between ANY two islands, not just the deck's
        1.4um: the extra 0.1um absorbs the gap between a device bounding box
        and its n-well edge after grid snapping."""
        self.assertGreaterEqual(self.default.metrics["nwell_min_gap_um"],
                                self.FLOOR)
        self.assertTrue(self.default.metrics["nwell_spacing_ok"])

    def test_the_measurement_is_recorded_for_evidence(self):
        for key in ("nwell_islands", "nwell_min_gap_um", "nwell_spacing_ok"):
            self.assertIn(key, self.default.metrics)

    def test_there_is_no_exemption_to_switch_off_the_floor(self):
        """Nothing in this flow merges n-wells, so an exemption could only
        ever promise a merge that does not happen. There must be no config
        knob that drops the gap below the floor."""
        from mbg.placement_engine import PlacementConfig
        cfg = PlacementConfig()
        self.assertFalse(hasattr(cfg, "shared_pfet_nwell"),
                         "the shared-well exemption is back; it cannot be "
                         "honoured until a device generator merges wells")

    def test_an_unknown_legacy_kwarg_cannot_weaken_the_floor(self):
        """A caller still passing the removed flag must not get 1.0um."""
        from mbg.pipeline import spice_to_gds_ctx
        from mbg.placement_engine import PlacementConfig
        ctx = spice_to_gds_ctx(
            netlist(), verbosity=0,
            placement_config=PlacementConfig(verbosity=0,
                                             shared_pfet_nwell=True))["context"]
        self.assertGreaterEqual(ctx.metrics["nwell_min_gap_um"], self.FLOOR)


class TestNoRegressionForNMOS(unittest.TestCase):
    def test_nmos_pairs_are_not_spaced_by_the_well_rule(self):
        """NMOS share the p-substrate; there is no n-well between them."""
        from mbg.placement_engine import PlacementConfig, _needs_nwell_gap
        from mbg.spice_parser import build_design_context, parse_netlist_with_pdk
        from glayout import gf180
        gf180.activate()
        ctx = build_design_context(parse_netlist_with_pdk(netlist()), gf180)
        cfg = PlacementConfig(verbosity=0)
        self.assertTrue(_needs_nwell_gap(ctx, "XM3", "XM4", cfg))   # pmos/pmos
        self.assertFalse(_needs_nwell_gap(ctx, "XM1", "XM2", cfg))  # nmos/nmos
        self.assertFalse(_needs_nwell_gap(ctx, "XM1", "XM3", cfg))  # mixed

    def test_the_pfet_gap_is_unconditional(self):
        """No config makes two PFETs skip the well gap."""
        from mbg.placement_engine import PlacementConfig, _needs_nwell_gap
        from mbg.spice_parser import build_design_context, parse_netlist_with_pdk
        from glayout import gf180
        gf180.activate()
        ctx = build_design_context(parse_netlist_with_pdk(netlist()), gf180)
        for kw in ({}, {"shared_pfet_nwell": True}, {"intra_cluster_gap": 0.1}):
            with self.subTest(cfg=kw):
                self.assertTrue(
                    _needs_nwell_gap(ctx, "XM3", "XM4",
                                     PlacementConfig(verbosity=0, **kw)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
