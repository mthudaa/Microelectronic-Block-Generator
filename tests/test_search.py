"""Evidence-driven search: candidates, selection, credit, rollback, memory.

These encode the lessons from the real failure this machinery was built to
fix. On the regression inverter the old optimizer went 63.1 -> 89.1 MHz
against a 100 MHz target and stopped, because it took one fixed step and had
a two-iteration budget. A later measured sweep showed the passing design was
one step further on (125.9 MHz at width scale 0.80) — and also that going
*further still* breaks the gain constraint (26.2 dB at 0.70, target 30).

So the properties under test are: keep stepping while it helps, compare
alternatives by measurement, attribute the gain to the one change that caused
it, and never let a worse branch become the new baseline.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mbg.search import (Candidate, CandidateResult, DesignMemory,      # noqa: E402
                        SearchState, HeuristicStrategy, LineSearchStrategy,
                        SensitivityStrategy, CompositeStrategy,
                        select_best, ParetoArchive, margin_of)
from mbg.specs import Spec, evaluate_specs                              # noqa: E402
from mbg.flow import DesignPoint                                        # noqa: E402

SPECS = [Spec("gain_db", ">=", 30.0, " dB"), Spec("bw_hz", ">=", 100e6, " Hz")]

NET = (".subckt inverter vdd vss in out\n"
       "XM1p out in vdd vdd pfet_03v3 L=1u W=4u nf=1\n"
       "XM1n out in vss vss nfet_03v3 L=1u W=2u nf=1\n"
       ".ends\n")


def _result(cid, metrics, change="c", knob="width", factor=0.9):
    c = Candidate(id=cid, design=DesignPoint(cell="x"), change=change,
                  params={"knob": knob, "factor": factor,
                          "step": (factor - 1) * 100})
    rep = evaluate_specs(metrics, SPECS, "pex")
    return CandidateResult(candidate=c, ok=True, metrics=metrics, report=rep,
                           score=rep.score, margin=margin_of(rep))


class TestCandidateSelection(unittest.TestCase):
    """Credit goes to the candidate that earned it — the documented failure."""

    def test_best_candidate_wins_and_others_are_labelled(self):
        base = evaluate_specs({"gain_db": 38.0, "bw_hz": 63e6}, SPECS, "pex")
        a = _result("A", {"gain_db": 38.0, "bw_hz": 67e6})
        b = _result("B", {"gain_db": 38.0, "bw_hz": 84e6})
        c = _result("C", {"gain_db": 38.0, "bw_hz": 61e6})

        winner, all_r = select_best([a, b, c], base.score)
        self.assertIs(winner, b)
        self.assertEqual(b.decision, "ACCEPT")
        self.assertEqual(a.decision, "ARCHIVE")   # improved, but not the best
        self.assertEqual(c.decision, "REJECT")    # worse than the incumbent

    def test_a_candidate_that_passes_everything_wins_outright(self):
        base = evaluate_specs({"gain_db": 38.0, "bw_hz": 63e6}, SPECS, "pex")
        near = _result("A", {"gain_db": 38.0, "bw_hz": 99e6})
        passing = _result("B", {"gain_db": 31.3, "bw_hz": 125.9e6})
        winner, _ = select_best([near, passing], base.score)
        self.assertIs(winner, passing)

    def test_a_candidate_that_breaks_another_spec_does_not_win(self):
        """The real trap: shrinking further raises BW but fails gain."""
        base = evaluate_specs({"gain_db": 38.0, "bw_hz": 63e6}, SPECS, "pex")
        good = _result("A", {"gain_db": 31.3, "bw_hz": 125.9e6})   # both pass
        greedy = _result("B", {"gain_db": 26.2, "bw_hz": 223.9e6})  # gain fails
        winner, _ = select_best([good, greedy], base.score)
        self.assertIs(winner, good,
                      "a bandwidth win that breaks gain must not be selected")

    def test_no_improvement_means_no_winner(self):
        base = evaluate_specs({"gain_db": 38.0, "bw_hz": 90e6}, SPECS, "pex")
        worse = _result("A", {"gain_db": 38.0, "bw_hz": 70e6})
        winner, results = select_best([worse], base.score)
        self.assertIsNone(winner, "the caller must roll back, not adopt this")
        self.assertEqual(worse.decision, "REJECT")

    def test_a_failed_candidate_is_an_error_not_a_rejection(self):
        base = evaluate_specs({"gain_db": 38.0, "bw_hz": 63e6}, SPECS, "pex")
        broken = CandidateResult(candidate=Candidate(id="A", design=None),
                                 ok=False, error="DRC failed")
        winner, results = select_best([broken], base.score)
        self.assertIsNone(winner)
        self.assertEqual(broken.decision, "ERROR")


class TestMemory(unittest.TestCase):

    def test_a_move_that_keeps_failing_is_withheld(self):
        mem = DesignMemory(max_failures=2)
        base = evaluate_specs({"gain_db": 38.0, "bw_hz": 63e6}, SPECS, "pex")
        for _ in range(2):
            r = _result("X", {"gain_db": 38.0, "bw_hz": 50e6}, change="bad move")
            r.decision = "REJECT"
            mem.record(r, base.score, {"gain_db": 38.0, "bw_hz": 63e6})
        self.assertTrue(mem.exhausted("bad move"))

    def test_a_move_that_helped_is_never_exhausted(self):
        mem = DesignMemory(max_failures=1)
        base = evaluate_specs({"gain_db": 38.0, "bw_hz": 63e6}, SPECS, "pex")
        good = _result("X", {"gain_db": 38.0, "bw_hz": 90e6}, change="good move")
        good.decision = "ACCEPT"
        mem.record(good, base.score, {"gain_db": 38.0, "bw_hz": 63e6})
        bad = _result("Y", {"gain_db": 38.0, "bw_hz": 60e6}, change="good move")
        bad.decision = "REJECT"
        mem.record(bad, base.score, {"gain_db": 38.0, "bw_hz": 63e6})
        self.assertFalse(mem.exhausted("good move"))

    def test_sensitivity_is_measured_not_assumed(self):
        """d(metric)/d(knob) comes from a real before/after pair."""
        mem = DesignMemory()
        base_metrics = {"gain_db": 38.52, "bw_hz": 63.1e6}
        base = evaluate_specs(base_metrics, SPECS, "pex")
        # real measured point: width x0.9 -> 89.1 MHz
        r = _result("A", {"gain_db": 35.81, "bw_hz": 89.1e6}, factor=0.9)
        r.decision = "ACCEPT"
        mem.record(r, base.score, base_metrics)
        s = mem.sensitivity("width", "bw_hz")
        self.assertIsNotNone(s)
        # bandwidth rose ~41% for a -10% width step => strongly negative slope
        self.assertLess(s, 0)


class TestStrategies(unittest.TestCase):

    def _state(self, metrics, memory=None, iteration=1, tier=1):
        rep = evaluate_specs(metrics, SPECS, "pex")
        return SearchState(design=DesignPoint(cell="inverter", netlist=NET),
                           report=rep, metrics=metrics, specs=SPECS,
                           memory=memory or DesignMemory(),
                           iteration=iteration, tier=tier)

    def test_heuristic_proposes_multiple_distinct_candidates(self):
        st = self._state({"gain_db": 38.0, "bw_hz": 63e6})
        cands = HeuristicStrategy().propose(st, 3)
        self.assertGreaterEqual(len(cands), 2, "one candidate is not a search")
        factors = {c.params["factor"] for c in cands}
        self.assertEqual(len(factors), len(cands), "candidates must differ")
        for c in cands:
            self.assertNotEqual(c.design.netlist, NET, "netlist must change")
            self.assertTrue(c.hypothesis and c.expected_effect and c.risk)

    def test_line_search_continues_a_direction_that_worked(self):
        """The move the old optimizer never made."""
        mem = DesignMemory()
        base = evaluate_specs({"gain_db": 38.0, "bw_hz": 63e6}, SPECS, "pex")
        won = _result("A", {"gain_db": 35.8, "bw_hz": 89.1e6}, factor=0.9)
        won.decision = "ACCEPT"
        mem.record(won, base.score, {"gain_db": 38.0, "bw_hz": 63e6})

        st = self._state({"gain_db": 35.8, "bw_hz": 89.1e6}, memory=mem, iteration=2)
        cands = LineSearchStrategy().propose(st, 3)
        self.assertTrue(cands, "an improving direction must be continued")
        factors = sorted(c.params["factor"] for c in cands)
        # must reach past 0.9 — the passing design measured at 0.80
        self.assertLess(min(factors), 0.9)

    def test_sensitivity_sizes_the_step_from_measurement(self):
        mem = DesignMemory()
        mem.sensitivities["width"] = {"bw_hz": -4.0}   # -4% BW per +1% width
        st = self._state({"gain_db": 38.0, "bw_hz": 63e6}, memory=mem)
        cands = SensitivityStrategy().propose(st, 2)
        self.assertTrue(cands)
        self.assertLess(cands[0].params["factor"], 1.0,
                        "closing a bandwidth gap needs a width reduction")
        self.assertIn("sensitivity", cands[0].hypothesis.lower())

    def test_composite_skips_exhausted_moves(self):
        mem = DesignMemory(max_failures=1)
        base = evaluate_specs({"gain_db": 38.0, "bw_hz": 63e6}, SPECS, "pex")
        for f in (0.9, 0.8):
            r = _result("X", {"gain_db": 38.0, "bw_hz": 50e6},
                        change=f"scale device widths x{f:g}", factor=f)
            r.decision = "REJECT"
            mem.record(r, base.score, {"gain_db": 38.0, "bw_hz": 63e6})
        st = self._state({"gain_db": 38.0, "bw_hz": 63e6}, memory=mem)
        cands = CompositeStrategy().propose(st, 3)
        changes = {c.change for c in cands}
        self.assertNotIn("scale device widths x0.9", changes)
        self.assertNotIn("scale device widths x0.8", changes)

    def test_stagnation_escalates_to_a_wider_bracket(self):
        mem = DesignMemory(max_failures=1)
        base = evaluate_specs({"gain_db": 38.0, "bw_hz": 63e6}, SPECS, "pex")
        for f in (0.9, 0.8):
            r = _result("X", {"gain_db": 38.0, "bw_hz": 50e6},
                        change=f"scale device widths x{f:g}", factor=f)
            r.decision = "REJECT"
            mem.record(r, base.score, {"gain_db": 38.0, "bw_hz": 63e6})
        for f in (0.9, 0.8, 1.15, 1.3):
            r = _result("X", {"gain_db": 38.0, "bw_hz": 50e6},
                        change=f"scale device widths x{f:g}", factor=f)
            r.decision = "REJECT"
            mem.record(r, base.score, {"gain_db": 38.0, "bw_hz": 63e6})

        # Local search still has a move here: the rejected trials left
        # measured sensitivity behind, and using it is the correct next step.
        st = self._state({"gain_db": 38.0, "bw_hz": 63e6}, memory=mem, tier=3)
        cands = CompositeStrategy().propose(st, 3)
        self.assertTrue(cands, "the search must not give up while a "
                               "measured move remains")

        # Only once no local information remains should it widen the bracket.
        mem.sensitivities.clear()
        cands = CompositeStrategy().propose(
            self._state({"gain_db": 38.0, "bw_hz": 63e6}, memory=mem, tier=3), 3)
        self.assertTrue(any(c.source == "wide_bracket" for c in cands),
                        f"expected a wide bracket once local moves are "
                        f"exhausted, got {[c.source for c in cands]}")


class TestParetoArchive(unittest.TestCase):

    def test_archive_keeps_non_dominated_designs_and_stays_bounded(self):
        arch = ParetoArchive(limit=3)
        for i, m in enumerate([{"gain_db": 40.0, "bw_hz": 60e6},
                               {"gain_db": 30.0, "bw_hz": 130e6},
                               {"gain_db": 35.0, "bw_hz": 95e6},
                               {"gain_db": 20.0, "bw_hz": 40e6}]):
            arch.offer(_result(f"C{i}", m))
        self.assertLessEqual(len(arch.entries), 3)
        self.assertTrue(arch.entries)


if __name__ == "__main__":
    unittest.main(verbosity=2)
