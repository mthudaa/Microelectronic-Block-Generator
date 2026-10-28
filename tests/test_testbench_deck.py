"""Testbench deck construction: unchanged for MOS-only gf180, extended otherwise.

Uses a throwaway fake PDK directory, so ngspice and a real PDK are not
needed: only the text of the deck is checked.
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from mbg.analysis import Testbench  # noqa: E402

MOS = """.subckt amp vdd vss in out
XM1 out in vss vss nfet_03v3 W=2u L=0.5u
XM2 out out vdd vdd pfet_03v3 W=4u L=0.5u
.ends
"""

BGR = """.subckt ref VDD VSS VREF
XQ1 VSS VSS e1 pnp_10p00x10p00
XR1 VREF e1 VSS ppolyf_u_1k r_width=1u r_length=20u
XM1 VREF VREF VDD VDD pfet_03v3 W=2u L=1u
.ends
"""

SECTIONS = ["typical", "ff", "ss", "fs", "sf", "bjt_typical", "bjt_ss", "bjt_ff",
            "res_typical", "res_ss", "res_ff", "mimcap_typical", "statistical"]


class DeckTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        ng = os.path.join(self.tmp.name, "libs.tech", "ngspice")
        os.makedirs(ng)
        with open(os.path.join(ng, "sm141064.ngspice"), "w") as f:
            for s in SECTIONS:
                f.write(f".lib {s}\n* body\n.endl {s}\n")
        with open(os.path.join(ng, "design.ngspice"), "w") as f:
            f.write("* design\n")
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def _old_deck(self, tb, analysis_lines, control):
        """The deck exactly as Testbench built it before PDK profiles."""
        head = [f".include '{tb.pdk_design}'", f".lib '{tb.pdk_models}' {tb.corner}"]
        inst = f"Xdut {' '.join(tb.ports)} {tb.cell}"
        body = head + ["", tb._core(), ""] + tb._stimulus() + [inst, ""]
        body += list(analysis_lines)
        body += [".control"] + list(control) + [".endc", ".end", ""]
        return "\n".join(body)

    def test_mos_only_gf180_deck_is_byte_identical(self):
        tb = Testbench(MOS, "amp", supplies={"vdd": 3.3, "vss": 0}, sources={"in": 1.0},
                       probes=["out"], pdk_root=self.root, corner="typical")
        ctrl = ["op", "print v(out)"]
        self.assertEqual(tb.build_deck([], ctrl), self._old_deck(tb, [], ctrl))

    def test_bandgap_loads_bjt_and_res_sections(self):
        tb = Testbench(BGR, "ref", supplies={"VDD": 3.3, "VSS": 0}, pdk_root=self.root,
                       corner="ss")
        deck = tb.build_deck([], ["op"])
        self.assertIn(f".lib '{tb.pdk_models}' ss", deck)
        self.assertIn(f".lib '{tb.pdk_models}' bjt_ss", deck)
        self.assertIn(f".lib '{tb.pdk_models}' res_ss", deck)
        # fs has no bjt section in gf180: falls back to typical
        tb.corner = "fs"
        deck = tb.build_deck([], ["op"])
        self.assertIn("bjt_typical", deck)

    def test_temperature_current_sources_and_extras(self):
        tb = Testbench(BGR, "ref", supplies={"VDD": 3.3, "VSS": 0}, pdk_root=self.root,
                       temp=85, isources={"VREF": "20u", "VSS": ("VDD", "1u")},
                       extra_lines=["* extra"])
        deck = tb.build_deck([], ["op"])
        self.assertIn(".temp 85", deck)
        self.assertIn("Iisrc0 0 VREF 20u", deck)
        self.assertIn("Iisrc1 VDD VSS 1u", deck)
        self.assertIn("* extra", deck)

    def test_supply_and_temperature_sweep_names(self):
        tb = Testbench(MOS, "amp", supplies={"vdd": 3.3, "vss": 0}, sources={"in": 1.0},
                       pdk_root=self.root)
        self.assertEqual(tb._source_name("temp"), "temp")
        self.assertEqual(tb._source_name("vdd"), "Vsupply0")
        self.assertEqual(tb._source_name("in"), "Vsrc0")

    def test_missing_section_names_the_available_ones(self):
        with open(os.path.join(self.root, "libs.tech", "ngspice", "sm141064.ngspice"), "w") as f:
            f.write(".lib typical\n.endl typical\n")
        Testbench._SECTION_CACHE.clear()
        tb = Testbench(BGR, "ref", supplies={"VDD": 3.3, "VSS": 0}, pdk_root=self.root)
        with self.assertRaises(ValueError) as cm:
            tb.build_deck([], ["op"])
        self.assertIn("bjt_typical", str(cm.exception))
        self.assertIn("available", str(cm.exception))
        Testbench._SECTION_CACHE.clear()


if __name__ == "__main__":
    unittest.main(verbosity=2)
