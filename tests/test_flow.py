"""Design-flow logic: two optimization loops, with PEX inside the second one.

These tests are about *control flow*, not about layout quality, so the EDA
work is injected. That is deliberate — the behaviour being verified is
"what does the framework do when PEX misses spec", and that must be provable
without a PDK, deterministically, in under a second.

Covers the cases from the flow specification:

  1  pre-layout fails then passes; layout starts only after it passes
  2  pre PASS -> PEX spec FAIL -> tune -> regenerate -> PEX PASS   (the point)
  3  DRC fail  -> LVS/PEX/PEX-sim SKIP
  4  LVS fail  -> PEX/PEX-sim SKIP
  5  PEX extraction fail -> PEX simulation SKIP
  6  PEX simulation tool error is NOT a spec failure
  7  max PEX iterations -> NOT_CONVERGED, clean termination
  8  best design is not lost when a later iteration is worse
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mbg.flow import (DesignFlow, DesignPoint, FlowConfig, FlowHooks,   # noqa: E402
                      LayoutResult, Stage, Outcome, Failure)
from mbg.specs import Spec, evaluate_specs                              # noqa: E402

SPECS = [Spec("gain_db", ">=", 60.0, " dB"),
         Spec("bw_hz", ">=", 15e6, " Hz")]

GOOD = {"gain_db": 64.0, "bw_hz": 18e6}
BAD = {"gain_db": 52.0, "bw_hz": 11e6}


def _layout(drc="PASS", lvs="PASS", pex="PASS", ok=None, failure=Failure.NONE,
            message=""):
    if ok is None:
        ok = drc == "PASS" and lvs == "PASS" and pex == "PASS"
    return LayoutResult(ok=ok, drc=drc, lvs=lvs, pex_extraction=pex,
                        pex_netlist="dummy.pex.spice" if ok else None,
                        failure=failure, message=message)


def _cfg(**kw):
    kw.setdefault("specs", SPECS)
    kw.setdefault("verbosity", 0)
    return FlowConfig(**kw)


class Test1_PreLayoutLoop(unittest.TestCase):

    def test_layout_starts_only_after_pre_layout_passes(self):
        sim_calls = {"n": 0}
        layout_calls = {"n": 0}

        def simulate_pre(d):
            sim_calls["n"] += 1
            return BAD if sim_calls["n"] == 1 else GOOD

        def build_layout(d):
            layout_calls["n"] += 1
            # Layout must not begin while pre-layout specs are unmet.
            self.assertEqual(sim_calls["n"], 2,
                             "layout was generated before pre-layout converged")
            return _layout()

        hooks = FlowHooks(simulate_pre=simulate_pre, build_layout=build_layout,
                          simulate_pex=lambda d, l: GOOD,
                          tune_pre=lambda d, r: d.evolve(note="tuned"))
        res = DesignFlow(hooks, _cfg()).run(DesignPoint(cell="uut"))

        self.assertEqual(res.status, Outcome.PASS)
        self.assertEqual(len(res.pre_layout), 2)
        self.assertFalse(res.pre_layout[0].spec_pass)
        self.assertTrue(res.pre_layout[1].spec_pass)
        self.assertEqual(layout_calls["n"], 1)

    def test_pre_layout_that_never_converges_does_not_reach_layout(self):
        built = {"n": 0}

        def build_layout(d):
            built["n"] += 1
            return _layout()

        hooks = FlowHooks(simulate_pre=lambda d: BAD, build_layout=build_layout,
                          simulate_pex=lambda d, l: GOOD,
                          tune_pre=lambda d, r: d)
        res = DesignFlow(hooks, _cfg(max_pre_iterations=3, patience=99)).run(
            DesignPoint(cell="uut"))

        self.assertEqual(res.status, Outcome.NOT_CONVERGED)
        self.assertEqual(res.failure, Failure.DESIGN_FAILURE)
        self.assertEqual(built["n"], 0, "layout ran despite pre-layout failing")


class Test2_PEXFeedbackLoop(unittest.TestCase):
    """The central case: PEX missing spec must start an iteration, not end the run."""

    def test_pex_failure_triggers_tuning_regeneration_and_reverification(self):
        pex_runs = {"n": 0}
        builds = []
        tuned = []

        def build_layout(d):
            builds.append(d.note)
            return _layout()

        def simulate_pex(d, l):
            pex_runs["n"] += 1
            # parasitics hurt the first layout; the retuned one recovers
            return BAD if pex_runs["n"] == 1 else GOOD

        def tune_post(d, report, degradation):
            tuned.append(degradation)
            return d.evolve(note=f"pex_tune_{len(tuned)}",
                            circuit={"w_mult": 1.2},
                            layout={"critical_net_width": 0.5})

        hooks = FlowHooks(simulate_pre=lambda d: GOOD, build_layout=build_layout,
                          simulate_pex=simulate_pex, tune_post=tune_post)
        res = DesignFlow(hooks, _cfg()).run(DesignPoint(cell="ota"))

        self.assertEqual(res.status, Outcome.PASS)
        self.assertEqual(res.stage, Stage.COMPLETE)
        # two PEX iterations: one failing, one passing
        self.assertEqual(len(res.pex), 2)
        self.assertFalse(res.pex[0].spec_pass)
        self.assertTrue(res.pex[1].spec_pass)
        # the layout really was regenerated, from a *tuned* design
        self.assertEqual(len(builds), 2)
        self.assertEqual(builds[1], "pex_tune_1")
        # and every stage was re-run on the new layout
        self.assertEqual(res.pex[1].drc, "PASS")
        self.assertEqual(res.pex[1].lvs, "PASS")
        self.assertEqual(res.pex[1].pex_extraction, "PASS")
        self.assertEqual(res.pex[1].pex_simulation, Outcome.PASS)

    def test_degradation_is_measured_against_pre_layout(self):
        hooks = FlowHooks(simulate_pre=lambda d: {"gain_db": 64.0, "bw_hz": 18e6},
                          build_layout=lambda d: _layout(),
                          simulate_pex=lambda d, l: {"gain_db": 52.0, "bw_hz": 11e6},
                          tune_post=None)
        res = DesignFlow(hooks, _cfg()).run(DesignPoint(cell="ota"))

        self.assertEqual(res.failure, Failure.SPEC_FAILURE)
        self.assertTrue(res.degradation)
        gain = next(d for d in res.degradation if d.name == "gain_db")
        self.assertAlmostEqual(gain.pre, 64.0)
        self.assertAlmostEqual(gain.post, 52.0)
        self.assertAlmostEqual(gain.delta, -12.0)
        self.assertTrue(gain.worsened)

    def test_extraction_success_alone_is_not_success(self):
        """PEX extraction PASS + spec FAIL must not report a passing run."""
        hooks = FlowHooks(simulate_pre=lambda d: GOOD,
                          build_layout=lambda d: _layout(),
                          simulate_pex=lambda d, l: BAD, tune_post=None)
        res = DesignFlow(hooks, _cfg()).run(DesignPoint(cell="ota"))
        self.assertEqual(res.pex[0].pex_extraction, "PASS")
        self.assertNotEqual(res.status, Outcome.PASS)
        self.assertEqual(res.failure, Failure.SPEC_FAILURE)


class Test3_DRCGate(unittest.TestCase):

    def test_drc_failure_skips_lvs_pex_and_pex_simulation(self):
        pex_sim = {"n": 0}

        def simulate_pex(d, l):
            pex_sim["n"] += 1
            return GOOD

        hooks = FlowHooks(
            simulate_pre=lambda d: GOOD,
            build_layout=lambda d: _layout(
                drc="FAIL", lvs=Outcome.SKIP, pex=Outcome.SKIP, ok=False,
                failure=Failure.VERIFICATION_FAILURE, message="12 DRC errors"),
            simulate_pex=simulate_pex, tune_post=None)
        res = DesignFlow(hooks, _cfg()).run(DesignPoint(cell="uut"))

        self.assertEqual(res.pex[0].drc, "FAIL")
        self.assertEqual(res.pex[0].lvs, Outcome.SKIP)
        self.assertEqual(res.pex[0].pex_extraction, Outcome.SKIP)
        self.assertEqual(res.pex[0].pex_simulation, Outcome.SKIP)
        self.assertEqual(pex_sim["n"], 0, "PEX was simulated on a DRC-failing layout")
        self.assertEqual(res.failure, Failure.VERIFICATION_FAILURE)


class Test4_LVSGate(unittest.TestCase):

    def test_lvs_failure_skips_pex_and_pex_simulation(self):
        pex_sim = {"n": 0}

        def simulate_pex(d, l):
            pex_sim["n"] += 1
            return GOOD

        hooks = FlowHooks(
            simulate_pre=lambda d: GOOD,
            build_layout=lambda d: _layout(
                drc="PASS", lvs="FAIL", pex=Outcome.SKIP, ok=False,
                failure=Failure.VERIFICATION_FAILURE, message="LVS mismatch"),
            simulate_pex=simulate_pex, tune_post=None)
        res = DesignFlow(hooks, _cfg()).run(DesignPoint(cell="uut"))

        self.assertEqual(res.pex[0].drc, "PASS")
        self.assertEqual(res.pex[0].lvs, "FAIL")
        self.assertEqual(res.pex[0].pex_extraction, Outcome.SKIP)
        self.assertEqual(res.pex[0].pex_simulation, Outcome.SKIP)
        self.assertEqual(pex_sim["n"], 0)
        self.assertEqual(res.failure, Failure.VERIFICATION_FAILURE)


class Test5_ExtractionGate(unittest.TestCase):

    def test_pex_extraction_failure_skips_pex_simulation(self):
        pex_sim = {"n": 0}

        def simulate_pex(d, l):
            pex_sim["n"] += 1
            return GOOD

        hooks = FlowHooks(
            simulate_pre=lambda d: GOOD,
            build_layout=lambda d: _layout(
                drc="PASS", lvs="PASS", pex="FAIL", ok=False,
                failure=Failure.TOOL_FAILURE,
                message="Magic could not extract parasitics"),
            simulate_pex=simulate_pex, tune_post=None)
        res = DesignFlow(hooks, _cfg()).run(DesignPoint(cell="uut"))

        self.assertEqual(res.pex[0].pex_extraction, "FAIL")
        self.assertEqual(res.pex[0].pex_simulation, Outcome.SKIP)
        self.assertEqual(pex_sim["n"], 0)
        self.assertEqual(res.failure, Failure.TOOL_FAILURE)


class Test6_SimulationToolFailure(unittest.TestCase):

    def test_simulation_error_is_not_a_spec_failure(self):
        """A crashed simulator must not be read as 'the design missed spec'.

        If it were, the optimizer would 'tune' in response to a broken tool
        and burn every remaining iteration chasing nothing.
        """
        tuned = {"n": 0}

        def simulate_pex(d, l):
            raise RuntimeError("ngspice segfaulted")

        def tune_post(d, r, deg):
            tuned["n"] += 1
            return d

        hooks = FlowHooks(simulate_pre=lambda d: GOOD,
                          build_layout=lambda d: _layout(),
                          simulate_pex=simulate_pex, tune_post=tune_post)
        res = DesignFlow(hooks, _cfg()).run(DesignPoint(cell="uut"))

        self.assertEqual(res.status, Outcome.ERROR)
        self.assertEqual(res.failure, Failure.TOOL_FAILURE)
        self.assertNotEqual(res.failure, Failure.SPEC_FAILURE)
        self.assertEqual(res.pex[0].pex_simulation, Outcome.ERROR)
        self.assertEqual(tuned["n"], 0, "optimizer tuned in response to a tool crash")
        self.assertIn("ngspice", res.message)

    def test_pre_layout_simulation_error_is_a_tool_failure(self):
        def simulate_pre(d):
            raise OSError("ngspice not found")

        hooks = FlowHooks(simulate_pre=simulate_pre,
                          build_layout=lambda d: _layout(),
                          simulate_pex=lambda d, l: GOOD,
                          tune_pre=lambda d, r: d)
        res = DesignFlow(hooks, _cfg()).run(DesignPoint(cell="uut"))
        self.assertEqual(res.status, Outcome.ERROR)
        self.assertEqual(res.failure, Failure.TOOL_FAILURE)


class Test7_IterationLimits(unittest.TestCase):

    def test_max_pex_iterations_terminates_cleanly_as_not_converged(self):
        runs = {"n": 0}

        def simulate_pex(d, l):
            runs["n"] += 1
            return BAD

        hooks = FlowHooks(simulate_pre=lambda d: GOOD,
                          build_layout=lambda d: _layout(),
                          simulate_pex=simulate_pex,
                          tune_post=lambda d, r, deg: d.evolve(note="t"))
        res = DesignFlow(hooks, _cfg(max_pex_iterations=4, patience=99)).run(
            DesignPoint(cell="uut"))

        self.assertEqual(res.status, Outcome.NOT_CONVERGED)
        self.assertEqual(res.failure, Failure.DESIGN_FAILURE)
        self.assertEqual(runs["n"], 4, "iteration limit was not honoured")
        self.assertEqual(len(res.pex), 4)
        self.assertIn("did not converge", res.message)

    def test_stagnation_stops_the_loop_before_the_hard_limit(self):
        hooks = FlowHooks(simulate_pre=lambda d: GOOD,
                          build_layout=lambda d: _layout(),
                          simulate_pex=lambda d, l: BAD,
                          tune_post=lambda d, r, deg: d)
        res = DesignFlow(hooks, _cfg(max_pex_iterations=50, patience=3)).run(
            DesignPoint(cell="uut"))
        self.assertEqual(res.status, Outcome.NOT_CONVERGED)
        self.assertLess(len(res.pex), 50)
        self.assertIn("stopped improving", res.message)


class Test8_BestDesignPreserved(unittest.TestCase):

    def test_a_worse_later_iteration_does_not_displace_the_best(self):
        # iteration 2 is the closest to target; 3 and 4 are worse
        seq = [
            {"gain_db": 50.0, "bw_hz": 10e6},
            {"gain_db": 58.0, "bw_hz": 14.5e6},     # best
            {"gain_db": 42.0, "bw_hz": 8e6},
            {"gain_db": 40.0, "bw_hz": 7e6},
        ]
        idx = {"n": 0}

        def simulate_pex(d, l):
            m = seq[min(idx["n"], len(seq) - 1)]
            idx["n"] += 1
            return m

        hooks = FlowHooks(simulate_pre=lambda d: GOOD,
                          build_layout=lambda d: _layout(),
                          simulate_pex=simulate_pex,
                          tune_post=lambda d, r, deg: d.evolve(
                              note=f"iter{idx['n']}"))
        res = DesignFlow(hooks, _cfg(max_pex_iterations=4, patience=99)).run(
            DesignPoint(cell="uut"))

        self.assertEqual(res.status, Outcome.NOT_CONVERGED)
        self.assertEqual(res.best_pex_iteration, 2,
                         "the best iteration was lost when later ones got worse")
        self.assertAlmostEqual(res.best_pex.get("gain_db").value, 58.0)

    def test_history_is_written_and_machine_readable(self):
        with tempfile.TemporaryDirectory() as td:
            hooks = FlowHooks(simulate_pre=lambda d: GOOD,
                              build_layout=lambda d: _layout(),
                              simulate_pex=lambda d, l: GOOD)
            res = DesignFlow(hooks, _cfg(outdir=td)).run(DesignPoint(cell="uut"))
            path = os.path.join(td, "history.json")
            self.assertTrue(os.path.isfile(path))
            data = json.loads(Path(path).read_text())
            self.assertEqual(data["status"], Outcome.PASS)
            self.assertEqual(len(data["pre_layout"]), 1)
            self.assertEqual(len(data["pex"]), 1)
            self.assertTrue(data["pex"][0]["spec_pass"])
            self.assertIn("gain_db", data["pex"][0]["metrics"]["metrics"])


class Test9_Configuration(unittest.TestCase):

    def test_missing_specs_is_a_configuration_failure(self):
        hooks = FlowHooks(simulate_pre=lambda d: GOOD,
                          build_layout=lambda d: _layout(),
                          simulate_pex=lambda d, l: GOOD)
        res = DesignFlow(hooks, FlowConfig(specs=[], verbosity=0)).run(
            DesignPoint(cell="uut"))
        self.assertEqual(res.failure, Failure.CONFIGURATION_FAILURE)

    def test_a_missing_metric_is_not_a_pass(self):
        report = evaluate_specs({"gain_db": 64.0}, SPECS, "pex")
        self.assertFalse(report.passed)
        self.assertEqual(report.get("bw_hz").status, "MISSING")


if __name__ == "__main__":
    unittest.main(verbosity=2)
