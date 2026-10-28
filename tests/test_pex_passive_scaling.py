"""PEX netlists: subcircuit passives get their geometry in real units.

Magic writes `.option scale=5n` and device geometry in those units. ngspice
scales MOSFET geometry but not parameters passed to a subcircuit, so a gf180
ppolyf_u_1k extracted as r_width=200 r_length=5000 was simulated in metres.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from mbg.checks import rescale_subckt_passives  # noqa: E402

PEX = """* NGSPICE file created from x.ext - technology: gf180mcuD

.option scale=5n

.subckt x A B VSS
X0 A n1 VSS ppolyf_u_1k r_width=200 r_length=5000
X1 A B cap_mim_2f0_m4m5_noshield c_width=1000 c_length=1000
X2 A B VSS VSS nfet_03v3 ad=48n pd=1.04m as=48n ps=1.04m w=400 l=1600
X3 n1 B VSS ppolyf_u r_width=1u r_length=4u
C0 A VSS 1.2f
.ends
"""


class PexPassiveScaling(unittest.TestCase):

    def test_passives_rescaled_mos_untouched(self):
        out, n = rescale_subckt_passives(PEX)
        self.assertEqual(n, 2)
        self.assertIn("ppolyf_u_1k r_width=1u r_length=25u", out)
        self.assertIn("c_width=5u c_length=5u", out)
        self.assertIn("w=400 l=1600", out)                 # MOS: ngspice scales these
        self.assertIn("r_width=1u r_length=4u", out)       # already in units

    def test_no_scale_option_is_a_no_op(self):
        text = PEX.replace(".option scale=5n\n", "")
        out, n = rescale_subckt_passives(text)
        self.assertEqual((out, n), (text, 0))


if __name__ == "__main__":
    unittest.main(verbosity=2)
