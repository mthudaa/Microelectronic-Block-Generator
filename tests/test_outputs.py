#!/usr/bin/env python3
"""Every module must emit the views LibreLane needs to integrate it.

Checks the generated LEF/LIB/Verilog are real — a LEF with no pins or a
zero-size macro is worse than no LEF, because it fails at floorplan time.

Run:  python tests/test_outputs.py
"""

import os
import re
import shutil
import sys
import tempfile
import unittest


def _repo_src():
    d = os.path.dirname(os.path.abspath(__file__))
    for _ in range(8):
        cand = os.path.join(d, "src")
        if os.path.isdir(os.path.join(cand, "mbg")):
            return cand
        d = os.path.dirname(d)
    raise RuntimeError("could not locate src/mbg")


sys.path.insert(0, _repo_src())
os.environ.setdefault("PDK_ROOT", os.path.expanduser("~/.volare"))
os.environ.setdefault("PDK", "gf180mcuD")
os.environ.setdefault("PDKPATH", os.path.join(os.environ["PDK_ROOT"], os.environ["PDK"]))
os.environ.setdefault("STD_CELL_LIBRARY", "gf180mcu_fd_sc_mcu7t5v0")

from mbg.outputs import classify_ports, write_lib, write_verilog  # noqa: E402

PORTS = ["vdd", "vss", "inp", "inm", "out", "vb"]


class PortClassification(unittest.TestCase):
    def test_supplies_recognised(self):
        specs = {p.name: p.direction for p in classify_ports(PORTS)}
        self.assertEqual(specs["vdd"], "power")
        self.assertEqual(specs["vss"], "ground")
        # Signal direction is not knowable from a SPICE netlist; inout is the
        # honest default and must not silently become input/output.
        for sig in ("inp", "inm", "out", "vb"):
            self.assertEqual(specs[sig], "inout", f"{sig} should default to inout")

    def test_explicit_directions_override(self):
        specs = {p.name: p.direction
                 for p in classify_ports(PORTS, {"out": "output"})}
        self.assertEqual(specs["out"], "output")


class ViewContent(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mbg_views_")
        self.specs = classify_ports(PORTS)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_verilog_declares_every_port(self):
        path = write_verilog("ota_5t", self.specs, self.tmp)
        text = open(path).read()
        self.assertIn("module ota_5t", text)
        self.assertIn("(* blackbox *)", text)
        for p in PORTS:
            self.assertRegex(text, rf"\binout\s+{p};", f"{p} not declared")

    def test_liberty_has_pins_and_no_invented_timing(self):
        path = write_lib("ota_5t", self.specs, self.tmp)
        text = open(path).read()
        self.assertIn("library (ota_5t_lib)", text)
        self.assertIn("cell (ota_5t)", text)
        self.assertIn("is_macro_cell : true", text)
        self.assertIn("pg_pin(vdd)", text)
        self.assertIn("pg_pin(vss)", text)
        for sig in ("inp", "inm", "out", "vb"):
            self.assertIn(f"pin({sig})", text)
        # No characterisation was run, so no arcs may be present.
        self.assertNotIn("timing (", text)
        self.assertNotIn("cell_rise", text)


HAVE_MAGIC = shutil.which("magic") is not None


@unittest.skipUnless(HAVE_MAGIC, "magic is not available")
class LefFromLayout(unittest.TestCase):
    """The LEF has to come from real geometry, so this runs the layout flow."""

    @classmethod
    def setUpClass(cls):
        from mbg import spice_to_gds_with_checks
        cls.tmp = tempfile.mkdtemp(prefix="mbg_lef_")
        cls.cwd = os.getcwd()
        os.chdir(cls.tmp)
        lib = os.path.join(os.environ["PDKPATH"], "libs.tech", "ngspice",
                           "sm141064.ngspice")
        netlist = f""".lib "{lib}" typical
.subckt ota_5t vdd vss inp inm out vb
XM1  net1 inp net2 vss nfet_03v3 L=1u W=4u nf=4
XM2  out  inm net2 vss nfet_03v3 L=1u W=4u nf=4
XM3  net1 net1 vdd vdd pfet_03v3 L=1u W=4u nf=4
XM4  out  net1 vdd vdd pfet_03v3 L=1u W=4u nf=4
XM5  net2 vb  vss vss nfet_03v3 L=1u W=4u nf=4
.ends
"""
        cls.result = spice_to_gds_with_checks(netlist, verbosity=0)

    @classmethod
    def tearDownClass(cls):
        os.chdir(cls.cwd)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_all_views_present(self):
        views = self.result.get("views")
        self.assertIsNotNone(views, "no views were generated")
        self.assertEqual(views.missing(), [], f"missing views: {views.missing()}")

    def test_lef_is_a_real_abstract(self):
        lef = self.result["views"].files.get("lef")
        self.assertIsNotNone(lef, "LEF was not generated")
        text = open(lef).read()
        self.assertIn("MACRO ota_5t", text)
        pins = re.findall(r"^\s*PIN\s+(\S+)", text, re.MULTILINE)
        self.assertEqual(sorted(pins), sorted(PORTS), f"LEF pins: {pins}")
        m = re.search(r"SIZE\s+([\d.]+)\s+BY\s+([\d.]+)", text)
        self.assertIsNotNone(m, "LEF has no SIZE")
        w, h = float(m.group(1)), float(m.group(2))
        # An empty Magic cell writes SIZE 0.005 BY 0.005 — catch that.
        self.assertGreater(w, 1.0, f"LEF width {w} looks like an empty cell")
        self.assertGreater(h, 1.0, f"LEF height {h} looks like an empty cell")


def main():
    loader = unittest.TestLoader()
    suite = unittest.TestSuite([loader.loadTestsFromTestCase(c) for c in
                                (PortClassification, ViewContent, LefFromLayout)])
    res = unittest.TextTestRunner(verbosity=2).run(suite)
    total = res.testsRun
    ok = total - len(res.failures) - len(res.errors) - len(res.skipped)
    print(f"\n=== {ok}/{total - len(res.skipped)} PASS "
          f"({len(res.skipped)} skipped) ===")
    return 0 if res.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
