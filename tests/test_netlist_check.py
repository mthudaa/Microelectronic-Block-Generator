"""Static netlist checks (mbg.netlist_check). Pure Python."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from mbg import pdk_profile  # noqa: E402
from mbg.netlist_check import check_netlist  # noqa: E402

HERE = os.path.dirname(__file__)


def codes(out):
    return {i["code"] for i in out["issues"]}


class NetlistCheckTests(unittest.TestCase):

    def setUp(self):
        self.gf = pdk_profile.load("gf180mcuD")
        self.sky = pdk_profile.load("sky130A")

    def test_regression_netlists_have_no_errors(self):
        d = os.path.join(HERE, "netlists")
        for name in sorted(os.listdir(d)):
            if not name.endswith(".spice"):
                continue
            with self.subTest(name=name):
                text = open(os.path.join(d, name)).read()
                out = check_netlist(text, self.gf)
                errs = [i for i in out["issues"] if i["severity"] == "error"]
                self.assertEqual(errs, [], name)

    def test_each_mistake_has_its_code(self):
        text = """.subckt bad VDD VSS OUT IN
M1 OUT IN VSS VSS nfet_03v3 W=2 L=0.5u
XM3 OUT IN VDD OUT pfet_03v3 W=2u L=0.5u
XM2 OUT IN VDD VDD pfet_03v3 W=12u L=0.1u m=2
XQ1 VDD VSS OUT pnp_10p00x10p00
XR1 OUT n1 VSS ppolyf_u_2k W=1u L=10u
.ends"""
        c = codes(check_netlist(text, self.gf))
        for code in ("UNIT_MISSING", "BODY_TIE", "SIZE_RANGE", "UNKNOWN_MODEL",
                     "INSTANCE_PREFIX", "MULTIPLIER", "FLOATING_NET",
                     "SUBSTRATE_TERMINAL"):
            self.assertIn(code, c)

    def test_sky130_units_are_microns(self):
        text = """.subckt inv VDD VSS A Y
XM1 Y A VDD VDD sky130_fd_pr__pfet_01v8 W=2u L=0.15u
XM2 Y A VSS VSS sky130_fd_pr__nfet_01v8 W=1 L=0.15
.ends"""
        out = check_netlist(text, self.sky)
        self.assertIn("UNIT_SUFFIX", codes(out))
        self.assertNotIn("SIZE_RANGE", codes(out))

    def test_sky130_passives_are_simulation_only(self):
        text = """.subckt r VDD VSS
XR1 VDD VSS VSS sky130_fd_pr__res_xhigh_po_0p35 L=10 W=0.35
.ends"""
        out = check_netlist(text, self.sky)
        self.assertIn("LAYOUT_UNSUPPORTED", codes(out))
        self.assertFalse(out["metrics"]["layout_supported"])

    def test_complexity_ceiling_is_reported(self):
        lines = [".subckt big VDD VSS " + " ".join(f"n{i}" for i in range(14))]
        for i in range(13):
            lines.append(f"XM{i} n{i} n{i + 1} VSS VSS nfet_03v3 W=1u L=0.5u")
        lines.append(".ends")
        out = check_netlist("\n".join(lines), self.gf)
        self.assertIn("ABOVE_TESTED_CEILING", codes(out))


if __name__ == "__main__":
    unittest.main(verbosity=2)
