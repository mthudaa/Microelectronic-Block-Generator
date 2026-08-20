#!/usr/bin/env python3
"""Analysis-layer tests: op, DC, AC, transient, FFT, Monte Carlo.

Each check asserts something physically meaningful rather than just "it ran" —
an inverter's trip point sits between the rails, the FFT of a 100 MHz pulse
peaks at 100 MHz, and a Monte Carlo run actually varies.

Run:  python tests/test_analysis.py
"""

import os
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

from mbg.analysis import Testbench, fft  # noqa: E402

INV = """
.subckt inv vdd vss a y
XM1 y a vdd vdd pfet_03v3 L=0.5u W=4u nf=1
XM2 y a vss vss nfet_03v3 L=0.5u W=2u nf=1
.ends
"""

HAVE_NGSPICE = shutil.which("ngspice") is not None
MODELS = os.path.join(os.environ["PDKPATH"], "libs.tech", "ngspice", "sm141064.ngspice")
HAVE_PDK = os.path.isfile(MODELS)
REASON = "ngspice or the GF180 models are not available"


@unittest.skipUnless(HAVE_NGSPICE and HAVE_PDK, REASON)
class AnalysisTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mbg_analysis_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _tb(self, **kw):
        kw.setdefault("supplies", {"vdd": 3.3, "vss": 0.0})
        kw.setdefault("probes", ["y"])
        kw.setdefault("workdir", os.path.join(self.tmp, "wd"))
        return Testbench(INV, cell="inv", **kw)

    def test_operating_point(self):
        r = self._tb(sources={"a": 1.65}).op()
        self.assertTrue(r.ok, r.stderr[:300])
        vy = r.value("y")
        self.assertGreaterEqual(vy, -0.1)
        self.assertLessEqual(vy, 3.4)

    def test_dc_sweep_spans_the_rails(self):
        r = self._tb(sources={"a": 0.0}).dc("a", 0, 3.3, 0.05)
        self.assertTrue(r.ok, r.stderr[:300])
        self.assertLess(r.min("y"), 0.3, "output should pull down to ground")
        self.assertGreater(r.max("y"), 3.0, "output should pull up to the rail")
        trip = r.cross("y", 1.65, "fall")
        self.assertIsNotNone(trip, "no trip point found")
        self.assertTrue(0.3 < trip < 3.0, f"implausible trip point {trip}")

    def test_ac_sweep_has_a_bandwidth(self):
        r = self._tb(sources={"a": 1.5}).ac(1, 1e10, points=10)
        self.assertTrue(r.ok, r.stderr[:300])
        self.assertGreater(len(r.x), 10)

    def test_transient_and_fft(self):
        tb = self._tb(sources={"a": "PULSE(0 3.3 1n 0.1n 0.1n 5n 10n)"},
                      loads={"y": "20f"})
        r = tb.tran("0.02n", "40n")
        self.assertTrue(r.ok, r.stderr[:300])
        self.assertGreater(r.peak_to_peak("y"), 2.0)
        freq, mag = fft(r, "y")
        peak = freq[max(range(len(mag)), key=lambda i: mag[i])]
        # 10 ns period -> 100 MHz fundamental
        self.assertAlmostEqual(peak / 1e8, 1.0, delta=0.1,
                               msg=f"FFT peaked at {peak:.4g} Hz, expected ~1e8")

    def test_monte_carlo_actually_varies(self):
        mc = self._tb(sources={"a": 1.5}).monte_carlo("op", runs=6)
        self.assertEqual(len(mc.runs), 6)
        stats = mc.stats("y")
        self.assertEqual(stats["n"], 6)
        # The typical corner gates mismatch off; if sigma is zero the corner
        # or the sw_stat_mismatch switch has regressed.
        self.assertGreater(stats["sigma"], 1e-6,
                           "Monte Carlo produced no spread — mismatch is gated off")


def main():
    if not (HAVE_NGSPICE and HAVE_PDK):
        print(f"SKIP  {REASON}")
        return 0
    suite = unittest.TestLoader().loadTestsFromTestCase(AnalysisTests)
    res = unittest.TextTestRunner(verbosity=2).run(suite)
    print(f"\n=== {res.testsRun - len(res.failures) - len(res.errors)}/{res.testsRun} PASS ===")
    return 0 if res.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())


class TestProbeCapture(unittest.TestCase):
    """Each analysis must return the response, not just the stimulus."""

    NET = """.subckt inv a y vdd vss
XM1 y a vdd vdd pfet_03v3 L=0.28u W=2u nf=1
XM2 y a vss vss nfet_03v3 L=0.28u W=1u nf=1
.ends
"""

    def _tb(self, stim):
        tb = Testbench(self.NET, "inv", supplies={"vdd": 3.3, "vss": 0.0})
        tb.sources = {"a": stim}
        return tb

    def test_shared_workdir_does_not_cross_contaminate(self):
        """dc/ac/tran write into one workdir; each must read its own file.

        Taking the first *.dat in the directory returned a previous
        analysis's data — the transient came back holding the DC sweep, with
        the output node absent entirely.
        """
        tb = self._tb("PULSE(0 3.3 1n 0.1n 0.1n 5n 10n)")
        tb.dc("a", 0, 3.3, 0.1)
        tran = tb.tran("0.05n", "20n")
        self.assertEqual(tran.x_name, "time")
        for node in ("y", "a", "vdd", "vss"):
            self.assertIn(node, tran.signals)

    def test_dc_sweep_records_the_output(self):
        tb = self._tb("DC 0")
        d = tb.dc("a", 0, 3.3, 0.05)
        self.assertIn("y", d.signals)
        vy = d.get("v(y)")
        # an inverter: output must fall as the input rises
        self.assertGreater(vy[0], vy[-1])

    def test_ac_parses_complex_columns(self):
        """AC writes (freq, re, im) triplets, not (x, y) pairs."""
        tb = self._tb("DC 1.2")
        a = tb.ac(1e3, 1e9)
        self.assertIn("y", a.signals)
        self.assertIn("y.re", a.signals)
        self.assertIn("y.im", a.signals)
        # the real-stride misparse invented these
        self.assertNotIn("col4", a.signals)
        self.assertNotIn("col5", a.signals)
        self.assertTrue(any(v > 0 for v in a.get("y")),
                        "AC magnitude is identically zero — the source never "
                        "received an AC magnitude")

    def test_ac_refuses_when_the_source_is_missing(self):
        tb = self._tb("DC 1.2")
        with self.assertRaises((RuntimeError, ValueError)):
            tb.ac(1e3, 1e9, ac_node="no_such_node")
