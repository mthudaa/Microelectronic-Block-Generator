"""Fixed foundry cells (vertical PNP) and the geometry helpers behind them."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from mbg import pdk_profile  # noqa: E402
from mbg.fixed_cells import rect_decompose  # noqa: E402


def _area(rects):
    return sum((x1 - x0) * (y1 - y0) for x0, y0, x1, y1 in rects)


class RectDecompose(unittest.TestCase):

    def test_ring_does_not_cover_its_hole(self):
        # A 10x10 ring of width 2, stored GDS-style as one boundary with a cut
        ring = [(0, 0), (10, 0), (10, 10), (0, 10), (0, 2), (2, 2), (2, 8),
                (8, 8), (8, 2), (0, 2)]
        rects = rect_decompose(ring)
        self.assertAlmostEqual(_area(rects), 100 - 36)
        for x0, y0, x1, y1 in rects:
            self.assertFalse(x0 < 5 < x1 and y0 < 5 < y1, "a rectangle covers the hole")

    def test_rectangle_and_l_shape(self):
        self.assertEqual(rect_decompose([(0, 0), (4, 0), (4, 2), (0, 2)]), [(0, 0, 4, 2)])
        ell = [(0, 0), (4, 0), (4, 1), (1, 1), (1, 3), (0, 3)]
        self.assertAlmostEqual(_area(rect_decompose(ell)), 4 + 2)


GF = pdk_profile.load("gf180mcuD")


@unittest.skipUnless(GF.installed(), "gf180mcuD not installed")
class PnpCell(unittest.TestCase):

    def test_ports_and_no_labels(self):
        try:
            from mbg.fixed_cells import build_fixed_device
            c = build_fixed_device(GF, "pnp_10p00x10p00")
        except ImportError as e:                                  # no gdsfactory
            self.skipTest(str(e))
        for t in ("c", "b", "e"):
            for d in ("N", "E", "S", "W"):
                p = c.ports[f"{t}_{d}"]
                self.assertEqual(tuple(p.layer), (36, 0))         # metal2 landing
        self.assertEqual(len(c.labels), 0)                        # labels stripped
        # base ports sit on the base ring, outside the emitter plate
        e = c.ports["e_N"].center
        b = c.ports["b_N"].center
        self.assertGreater(b[1] - e[1], 5.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
