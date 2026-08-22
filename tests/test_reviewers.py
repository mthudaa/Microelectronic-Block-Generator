"""Multi-agent review: critics advise, evidence decides.

The properties under test are the ones that keep an advisory layer honest:
a critic can block, but no amount of reviewer optimism can turn a failed
verification gate into a sign-off.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mbg.reviewers import (devil_review, angel_review, synthesize,  # noqa: E402
                           ReviewContext, ReviewLedger, Review, Severity,
                           Verdict, ReviewStatus, Finding, Recommendation,
                           register_reviewer, run_reviews)
from mbg.specs import Spec, evaluate_specs, compare_degradation      # noqa: E402
from mbg.flow import LayoutResult, Outcome                           # noqa: E402

SPECS = [Spec("gain_db", ">=", 60.0, " dB"), Spec("bw_hz", ">=", 15e6, " Hz")]


class TestA_DevilDetectsHardFailure(unittest.TestCase):

    def test_lvs_mismatch_is_critical_and_forbids_accept(self):
        layout = LayoutResult(ok=False, drc=Outcome.PASS, lvs="FAIL",
                              pex_extraction=Outcome.SKIP,
                              message="LVS mismatch")
        ctx = ReviewContext(stage="LVS", layout=layout)
        devil = devil_review(ctx)

        self.assertEqual(devil.worst_severity, Severity.CRITICAL)
        self.assertEqual(devil.verdict, Verdict.BLOCK)

        # even with an optimistic angel, ACCEPT must be impossible
        angel = Review(reviewer="angel", stage="LVS", verdict=Verdict.ACCEPT,
                       confidence=0.99)
        d = synthesize(ctx, [devil, angel], evidence_pass=True)
        self.assertEqual(d.verdict, Verdict.BLOCK)
        self.assertFalse(d.may_proceed)

    def test_missing_measurement_is_not_treated_as_a_pass(self):
        report = evaluate_specs({"gain_db": 64.0}, SPECS, "pex")  # bw missing
        devil = devil_review(ReviewContext(stage="PEX_SIMULATION",
                                           spec_report=report))
        names = [f.category for f in devil.findings]
        self.assertIn("bw_hz", names)
        self.assertIn(devil.verdict, (Verdict.REVISE, Verdict.BLOCK))

    def test_a_thin_margin_is_flagged_even_when_passing(self):
        report = evaluate_specs({"gain_db": 60.5, "bw_hz": 15.1e6}, SPECS, "pex")
        self.assertTrue(report.passed)
        devil = devil_review(ReviewContext(stage="PEX_SIMULATION",
                                           spec_report=report))
        self.assertTrue(any(f.severity == Severity.MEDIUM for f in devil.findings),
                        "a 1% margin should not pass without comment")


class TestB_AngelRecommendsActionableWork(unittest.TestCase):

    def test_bandwidth_degradation_yields_an_allowed_action(self):
        pre = evaluate_specs({"gain_db": 64.0, "bw_hz": 18e6}, SPECS, "pre_layout")
        post = evaluate_specs({"gain_db": 63.0, "bw_hz": 11e6}, SPECS, "pex")
        deg = compare_degradation(pre, post, SPECS)

        angel = angel_review(ReviewContext(stage="PEX_SIMULATION",
                                           spec_report=post, pre_report=pre,
                                           degradation=deg))
        self.assertTrue(angel.recommendations)
        targets = {r.target for r in angel.recommendations}
        self.assertTrue(targets & {"circuit", "layout"})
        # a metric lost to parasitics should draw a layout action first
        self.assertEqual(angel.recommendations[0].target, "layout")

    def test_verification_failure_is_recommended_before_tuning(self):
        layout = LayoutResult(ok=False, drc="FAIL", lvs=Outcome.SKIP,
                              pex_extraction=Outcome.SKIP)
        angel = angel_review(ReviewContext(stage="DRC", layout=layout))
        self.assertIn("DRC", angel.recommendations[0].action)


class TestC_ConflictingReviews(unittest.TestCase):

    def test_objective_failure_beats_an_optimistic_reviewer(self):
        report = evaluate_specs({"gain_db": 50.0, "bw_hz": 9e6}, SPECS, "pex")
        ctx = ReviewContext(stage="PEX_SIMULATION", spec_report=report)
        devil = Review(reviewer="devil", stage="PEX_SIMULATION",
                       verdict=Verdict.REVISE)
        angel = Review(reviewer="angel", stage="PEX_SIMULATION",
                       verdict=Verdict.ACCEPT, confidence=0.95)
        d = synthesize(ctx, [devil, angel], evidence_pass=False)
        self.assertEqual(d.verdict, Verdict.REVISE)

    def test_measured_success_is_not_vetoed_by_sentiment(self):
        """Reviewers cannot reject a design that met every measured target."""
        report = evaluate_specs({"gain_db": 70.0, "bw_hz": 30e6}, SPECS, "pex")
        ctx = ReviewContext(stage="PEX_SIMULATION", spec_report=report)
        devil = Review(reviewer="devil", stage="PEX_SIMULATION",
                       verdict=Verdict.REVISE,
                       findings=[Finding(Severity.HIGH, "style", "I dislike it")])
        angel = Review(reviewer="angel", stage="PEX_SIMULATION",
                       verdict=Verdict.ACCEPT)
        d = synthesize(ctx, [devil, angel], evidence_pass=True)
        self.assertEqual(d.verdict, Verdict.ACCEPT)
        self.assertIn("HIGH concern", d.reason)


class TestD_VerificationOverridesReviewers(unittest.TestCase):

    def test_both_reviewers_approve_but_drc_fails(self):
        ctx = ReviewContext(stage="FINAL_SIGNOFF")
        good = [Review(reviewer="devil", stage="FINAL_SIGNOFF",
                       verdict=Verdict.ACCEPT, confidence=0.99),
                Review(reviewer="angel", stage="FINAL_SIGNOFF",
                       verdict=Verdict.ACCEPT, confidence=0.99)]
        d = synthesize(ctx, good, evidence_pass=True, hard_gate_ok=False)
        self.assertEqual(d.verdict, Verdict.BLOCK)
        self.assertIn("hard verification gate", d.reason)

    def test_a_failed_reviewer_blocks_rather_than_silently_approving(self):
        ctx = ReviewContext(stage="FINAL_SIGNOFF")
        broken = Review(reviewer="devil", stage="FINAL_SIGNOFF",
                        status=ReviewStatus.REVIEWER_FAILURE,
                        error="model unavailable")
        angel = Review(reviewer="angel", stage="FINAL_SIGNOFF",
                       verdict=Verdict.ACCEPT)
        d = synthesize(ctx, [broken, angel], evidence_pass=True)
        self.assertEqual(d.verdict, Verdict.ESCALATE)
        self.assertIn("not an approval", d.reason)

    def test_a_crashing_reviewer_does_not_take_down_the_run(self):
        def explode(ctx):
            raise RuntimeError("critic exploded")
        register_reviewer("boom", explode)
        try:
            reviews = run_reviews(ReviewContext(stage="DRC"), ("boom", "angel"))
        finally:
            from mbg.reviewers import _REGISTRY
            _REGISTRY.pop("boom", None)
        self.assertEqual(reviews[0].status, ReviewStatus.REVIEWER_FAILURE)
        self.assertIn("critic exploded", reviews[0].error)
        self.assertEqual(reviews[1].status, ReviewStatus.OK)


class TestE_LedgerTracksWhetherAdviceHelped(unittest.TestCase):

    def test_recommendation_change_and_improvement_are_recorded(self):
        led = ReviewLedger()
        rec = Recommendation("widen and shorten the critical net", target="layout",
                             id="layout:critical_net")
        led.propose(rec, "PEX_SIMULATION", 1)
        led.mark_applied([rec.key()], score_before=0.37)
        led.settle(0.11)                       # measured improvement

        e = led.entries[0]
        self.assertEqual(e["status"], "IMPROVED")
        self.assertEqual(e["score_before"], 0.37)
        self.assertEqual(e["score_after"], 0.11)
        self.assertEqual(led.summary()["angel"]["improved"], 1)

    def test_advice_that_never_helps_is_withheld_after_repeats(self):
        led = ReviewLedger(max_attempts=2)
        rec = Recommendation("no-op", target="circuit", id="circuit:noop")
        for _ in range(2):
            led.propose(rec, "PEX_SIMULATION", 1)
            led.mark_applied([rec.key()], score_before=0.5)
            led.settle(0.5)                    # neutral, twice
        self.assertTrue(led.is_exhausted("circuit:noop"))

        # and the angel stops proposing it
        post = evaluate_specs({"gain_db": 50.0, "bw_hz": 9e6}, SPECS, "pex")
        led2 = ReviewLedger(max_attempts=1)
        for key in ("layout:critical_net", "layout:promote_metal",
                    "circuit:shrink_load"):
            led2.propose(Recommendation("x", target="layout", id=key), "s", 1)
            led2.mark_applied([key], score_before=1.0)
            led2.settle(1.0)
        angel = angel_review(ReviewContext(stage="PEX_SIMULATION",
                                           spec_report=post, ledger=led2))
        keys = {r.key() for r in angel.recommendations}
        self.assertNotIn("layout:critical_net", keys)


if __name__ == "__main__":
    unittest.main(verbosity=2)
