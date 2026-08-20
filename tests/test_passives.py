"""Native GF180MCU passives: geometry, DRC and extraction.

These devices are built from raw PDK layers by `mbg.passives` because gLayout
cannot build either one in a form gf180 recognises: its `resistor()` is a
diode-connected pfet, and its `mimcap()` sits on met2/met3 while the PDK
defines the MIM over metal4/metal5. The point of these tests is that Magic
really does extract them as `ppolyf_u` and `cap_mim_2f0_m4m5_noshield`.
"""

import os
import re
import subprocess
import tempfile
import unittest

from mbg.passives import (poly_resistor, mim_cap, RES_MIN_WIDTH, CAP_MIN_SIZE)

_UID = __import__('itertools').count()

PDKPATH = os.environ.get("PDKPATH", "")
MAGICRC = os.path.join(PDKPATH, "libs.tech", "magic", "gf180mcuD.magicrc")
HAVE_PDK = bool(PDKPATH) and os.path.exists(MAGICRC)


def _magic(cell, gds_path, workdir, script):
    tcl = os.path.join(workdir, "run.tcl")
    with open(tcl, "w") as f:
        f.write(f'gds read {gds_path}\nload {cell} -dereference\n'
                f'select top cell\n{script}\nquit -noprompt\n')
    return subprocess.run(
        ["magic", "-dnull", "-noconsole", "-rcfile", MAGICRC, tcl],
        cwd=workdir, capture_output=True, text=True, timeout=300,
        stdin=subprocess.DEVNULL).stdout


def _drc_and_extract(component, cell):
    """Returns (drc_violation_lines, extracted_subckt_line)."""
    wd = tempfile.mkdtemp(prefix="mbg_passive_")
    # Unique per call: gdsfactory caches components by name, so reusing one
    # name across cases writes the *first* geometry under it and the later
    # extraction silently comes back empty.
    cell = f"{cell}_{next(_UID)}"
    component.name = cell
    gds = os.path.join(wd, f"{cell}.gds")
    component.write_gds(gds)

    drc_out = _magic(cell, gds, wd,
                     "drc euclidean on\ndrc style drc(full)\ndrc check\n"
                     "drc catchup\nputs {=== WHY ===}\n"
                     "foreach {r} [drc listall why] { puts $r }")
    why = drc_out.split("=== WHY ===", 1)[-1]
    violations = [ln.strip() for ln in why.splitlines()
                  if ln.strip() and not ln.startswith("{")
                  and "No errors found" not in ln
                  and not ln.startswith("quit")]

    _magic(cell, gds, wd, "extract all\next2spice lvs\next2spice -o out.spice")
    spice = ""
    path = os.path.join(wd, "out.spice")
    if os.path.exists(path):
        spice = open(path).read()
    device = ""
    for ln in spice.splitlines():
        if ln.startswith("X"):
            device = ln.strip()
            break
    return violations, device


class TestPassiveGeometry(unittest.TestCase):
    """No PDK tools needed — pure geometry contracts."""

    def test_resistor_rejects_sub_minimum_width(self):
        with self.assertRaises(ValueError):
            poly_resistor(width=RES_MIN_WIDTH - 0.1, length=4.0)

    def test_cap_rejects_sub_minimum_plate(self):
        # MIMTM.8a is 5um, which is unusually large and easy to trip over.
        with self.assertRaises(ValueError):
            mim_cap(size=CAP_MIN_SIZE - 0.5)

    def test_terminals_are_named_for_the_router(self):
        for c in (poly_resistor(1.0, 4.0), mim_cap(5.0)):
            names = set(c.ports)
            for term in ("p", "n"):
                for d in ("N", "E", "S", "W"):
                    self.assertIn(f"{term}_{d}", names, c.name)

    def test_cap_terminals_are_on_met3(self):
        """The cap must not present met4/met5 pins.

        Magic derives the MIM bottom plate as the whole *connected* metal4
        shape and then demands 1.2um of clearance from any unrelated metal4,
        so a router that reaches the plates directly cannot win.
        """
        c = mim_cap(5.0)
        for name, port in c.ports.items():
            self.assertEqual(tuple(port.layer)[0], 42,
                             f"{name} should be on met3 (42), got {port.layer}")


@unittest.skipUnless(HAVE_PDK, "needs PDKPATH and magic")
class TestPassiveSignoff(unittest.TestCase):

    def test_poly_resistor_is_drc_clean_and_extracts(self):
        viol, dev = _drc_and_extract(poly_resistor(1.0, 4.0), "res_uut")
        self.assertEqual(viol, [], f"DRC violations: {viol}")
        self.assertIn("ppolyf_u", dev)
        self.assertIn("r_width=1u", dev)
        self.assertIn("r_length=4u", dev)

    def test_mim_cap_is_drc_clean_and_extracts(self):
        viol, dev = _drc_and_extract(mim_cap(5.0), "cap_uut")
        self.assertEqual(viol, [], f"DRC violations: {viol}")
        self.assertIn("cap_mim_2f0_m4m5_noshield", dev)
        self.assertIn("c_width=5u", dev)

    def test_resistor_sizes_extract_faithfully(self):
        for w, l in ((0.8, 2.0), (2.0, 10.0)):
            with self.subTest(w=w, l=l):
                viol, dev = _drc_and_extract(poly_resistor(w, l), "res_uut")
                self.assertEqual(viol, [], f"W={w} L={l}: {viol}")
                self.assertRegex(dev, rf"r_width={w:g}u")
                self.assertRegex(dev, rf"r_length={l:g}u")


if __name__ == "__main__":
    unittest.main(verbosity=2)
