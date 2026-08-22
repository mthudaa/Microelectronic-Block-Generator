"""A real PEX feedback loop, measured on real artifacts.

Uses the regression inverter biased at its own trip point, where it is a
genuine small-signal amplifier. Layout parasitics cost it roughly 60% of its
bandwidth while leaving DC gain untouched — capacitive loading, which is
exactly the degradation the PEX-aware loop exists to respond to.

Nothing here is a made-up specification. The targets are chosen from the
measured pre-layout and post-layout values so that one of them genuinely
straddles the layout boundary: it passes before layout and fails after. That
is what forces the second optimization loop to run.

Needs the PDK and ngspice; skipped otherwise.
"""

import os
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from mbg.flow import (DesignFlow, DesignPoint, FlowConfig, FlowHooks,   # noqa: E402
                      LayoutResult, Outcome, Failure, Stage)
from mbg.specs import Spec, evaluate_specs, compare_degradation        # noqa: E402
from mbg.flow_runtime import measure_ac_metrics                        # noqa: E402

CELL = "inverter"
ART = REPO / "outputs" / "regression" / CELL
SCH = ART / f"{CELL}.spice"
PEX = ART / f"{CELL}.pex.spice"

HAVE = (os.environ.get("PDKPATH") and SCH.is_file() and PEX.is_file())

SUPPLIES = {"vdd": 3.3, "vss": 0.0}


def _trip_point(netlist):
    """The self-bias point: where the inverter has its maximum small-signal gain."""
    from mbg.analysis import Testbench
    tb = Testbench(netlist, CELL, supplies=SUPPLIES)
    tb.sources = {"in": "DC 0"}
    d = tb.dc("in", 0, 3.3, 0.02)
    vin, vout = d.x, d.get("out")
    i = max(range(1, len(vin) - 1),
            key=lambda k: abs((vout[k + 1] - vout[k - 1]) /
                              (vin[k + 1] - vin[k - 1])))
    return vin[i]


@unittest.skipUnless(HAVE, "needs PDKPATH and a completed regression run")
class TestRealPEXDegradation(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        sch = SCH.read_text()
        cls.bias = _trip_point(sch)
        kw = dict(out_node="out", in_node="in", supplies=SUPPLIES,
                  bias={"in": f"DC {cls.bias:.4f}"})
        cls.pre = measure_ac_metrics(sch, CELL, **kw)
        cls.post = measure_ac_metrics(PEX.read_text(), CELL, **kw)

    def test_both_netlists_simulate(self):
        self.assertIn("gain_db", self.pre, "pre-layout simulation produced nothing")
        self.assertIn("gain_db", self.post, "PEX simulation produced nothing")

    def test_parasitics_cost_bandwidth_but_not_dc_gain(self):
        """The signature of capacitive loading, confirmed on real extraction."""
        self.assertAlmostEqual(self.pre["gain_db"], self.post["gain_db"], delta=1.0,
                               msg="DC gain should be nearly unchanged by parasitic C")
        self.assertLess(self.post["bw_hz"], self.pre["bw_hz"] * 0.9,
                        "extraction produced no measurable bandwidth loss — "
                        "is the PEX netlist actually parasitic-annotated?")

    def test_degradation_analysis_identifies_bandwidth_as_the_problem(self):
        specs = [Spec("gain_db", ">=", 30.0, " dB"),
                 Spec("bw_hz", ">=", 100e6, " Hz")]
        pre = evaluate_specs(self.pre, specs, "pre_layout")
        post = evaluate_specs(self.post, specs, "pex")

        self.assertTrue(pre.passed, "the target should pass BEFORE layout")
        self.assertFalse(post.passed, "the target should fail AFTER extraction")

        deg = compare_degradation(pre, post, specs)
        worst = deg[0]
        self.assertEqual(worst.name, "bw_hz")
        self.assertTrue(worst.worsened)
        self.assertLess(worst.delta_pct, -10.0)

    def test_flow_enters_pex_optimization_on_a_real_spec_miss(self):
        """The end-to-end behaviour: a real PEX miss must start loop B.

        Layout regeneration is stubbed with the measured values so the test
        stays deterministic and quick; the measurements driving it are real.
        """
        specs = [Spec("gain_db", ">=", 30.0, " dB"),
                 Spec("bw_hz", ">=", 100e6, " Hz")]
        tuned = []
        attempts = {"n": 0}

        def simulate_pex(design, layout):
            attempts["n"] += 1
            if attempts["n"] == 1:
                return self.post                       # measured, fails bw
            # after widening the critical net, model the recovered bandwidth
            better = dict(self.post)
            better["bw_hz"] = self.pre["bw_hz"] * 0.95
            return better

        def tune_post(design, report, degradation):
            tuned.append([d.name for d in degradation if d.worsened])
            return design.evolve(layout={"critical_net_width": 0.5})

        hooks = FlowHooks(
            simulate_pre=lambda d: self.pre,
            build_layout=lambda d: LayoutResult(
                ok=True, drc=Outcome.PASS, lvs=Outcome.PASS,
                pex_extraction=Outcome.PASS, pex_netlist=str(PEX)),
            simulate_pex=simulate_pex, tune_post=tune_post)

        res = DesignFlow(hooks, FlowConfig(specs=specs, verbosity=0)).run(
            DesignPoint(cell=CELL, netlist=SCH.read_text()))

        self.assertEqual(res.status, Outcome.PASS)
        self.assertEqual(res.stage, Stage.COMPLETE)
        self.assertEqual(len(res.pex), 2, "the PEX loop did not iterate")
        self.assertFalse(res.pex[0].spec_pass)
        self.assertTrue(res.pex[1].spec_pass)
        self.assertTrue(tuned and "bw_hz" in tuned[0],
                        "the tuner was not told which metric degraded")


if __name__ == "__main__":
    unittest.main(verbosity=2)
