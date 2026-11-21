"""Device multiplicity (SPICE nf x m) must always be buildable and correct.

bias_ctat has ``XM1 ... W=10u L=1u nf=1 m=24``.  SPICE semantics: W is one
instance's width and m copies run in parallel, so the device is 240 um wide.
The parser hands over finger_width = W / (nf * m) = 0.42 um, below the
active-to-met1 contact (0.46 um), and gLayout's via_array raised.
"""
import os
import re
import unittest
from types import SimpleNamespace as NS

from mbg.design_context import Device

# (kind, W_per_instance, L, nf, m)
CASES = [
    ("nmos", 10.0, 1.0, 1, 24),     # bias_ctat XM1: crashed in via_array
    ("nmos", 10.0, 1.0, 1, 8),
    ("nmos", 2.0, 0.5, 1, 6),       # crashed (W/(nf m) = 0.33 um)
    ("nmos", 4.0, 1.0, 2, 12),      # crashed
    ("nmos", 2.0, 1.0, 1, 3),
    ("nmos", 8.0, 0.5, 2, 40),      # more than one row of fingers
    ("pmos", 10.0, 1.0, 1, 24),     # crashed
    ("pmos", 4.0, 0.5, 2, 8),       # crashed
]


def _dev(kind, w, l, nf, m):
    model = "nfet_03v3" if kind == "nmos" else "pfet_03v3"
    d = Device(name="XM1", model=model, kind=kind, terminals={}, width=w,
               length=l, fingers=nf, multipliers=m)
    d.finger_width = w / (nf * m)       # what spice_parser sets
    return d


class TestDrawnGeometry(unittest.TestCase):
    def test_units_and_total_width_are_preserved(self):
        from mbg.placement_engine import drawn_geometry, MAX_FOLDED_FINGERS
        for kind, w, l, nf, m in CASES:
            with self.subTest(kind=kind, w=w, nf=nf, m=m):
                fw, fingers, mult = drawn_geometry(_dev(kind, w, l, nf, m))
                self.assertEqual(fingers * mult, nf * m)
                self.assertAlmostEqual(fw * fingers * mult, w * m)
                self.assertAlmostEqual(fw, w / nf)
                self.assertGreaterEqual(fw, 0.46)
                self.assertLessEqual(fingers, max(nf, MAX_FOLDED_FINGERS))

    def test_m1_is_unchanged(self):
        from mbg.placement_engine import drawn_geometry
        d = Device(name="XM1", model="nfet_03v3", kind="nmos", terminals={},
                   width=8.0, length=1.0, fingers=2, multipliers=1)
        d.finger_width = 4.0
        self.assertEqual(drawn_geometry(d), (4.0, 2, 1))

    def test_m_folds_into_one_row_when_it_fits(self):
        from mbg.placement_engine import drawn_geometry
        self.assertEqual(drawn_geometry(_dev("nmos", 10.0, 1.0, 1, 24)),
                         (10.0, 24, 1))


class TestDeviceMultiplicity(unittest.TestCase):
    def test_builds(self):
        from glayout import gf180
        from mbg.placement_engine import build_device, PlacementConfig
        for kind, w, l, nf, m in CASES:
            with self.subTest(kind=kind, w=w, l=l, nf=nf, m=m):
                c = build_device(gf180, _dev(kind, w, l, nf, m),
                                 PlacementConfig(verbosity=0))
                self.assertGreater(c.xmax - c.xmin, 0)


class TestParsedMultiplicity(unittest.TestCase):
    """A parsed ``m=24`` device is 24 full-width copies (netgen semantics)."""
    NETLIST = (".subckt mtest d g s b\n"
               "XM1 d g s b nfet_03v3 W=10u L=1u nf=1 m=24\n"
               ".ends\n")

    def test_parsed_device_builds_as_240um(self):
        from glayout import gf180
        from mbg.spice_parser import parse_netlist_with_pdk, build_design_context
        from mbg.placement_engine import (build_device, drawn_geometry,
                                          PlacementConfig)
        ctx = build_design_context(
            parse_netlist_with_pdk(self.NETLIST, mode="analog"), None)
        dev = ctx.devices["XM1"]
        self.assertAlmostEqual(dev.finger_width, 10.0)      # W/nf, not W/(nf*m)
        fw, fingers, mult = drawn_geometry(dev)
        self.assertAlmostEqual(fw * fingers * mult, 240.0)
        c = build_device(gf180, dev, PlacementConfig(verbosity=0))
        self.assertGreater(c.xmax - c.xmin, 0)


if __name__ == "__main__":
    unittest.main()
