"""FULL AUTOMATE orchestration and the /mbg-* command namespace.

`/mbg-full-auto` has to be able to fail honestly. Most of these tests are
about the ways it must *not* claim success: a tool crash, an unresolved
CRITICAL finding, or a sign-off condition that was never evaluated all have
to stop TAPEOUT_READY, no matter how well the rest of the run went.
"""

import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from mbg.full_auto import (run_full_auto, parse_request, AutoStatus,   # noqa: E402
                           FullAutoConfig, SignoffGate, MBG_COMMANDS,
                           CANONICAL_COMMAND)
from mbg.flow import FlowHooks, LayoutResult, Outcome, Failure          # noqa: E402
from mbg.specs import Spec                                              # noqa: E402
from mbg.reviewers import register_reviewer, Review, Verdict, Severity, Finding  # noqa: E402

REQUEST = ("Design a 5T OTA in GF180 with VDD=3.3 V, gain >= 30 dB, "
           "bandwidth >= 100 MHz, and CL=1 pF. Produce a tapeout-ready "
           "layout and design report.")

GOOD = {"gain_db": 40.0, "bw_hz": 150e6}
BAD = {"gain_db": 40.0, "bw_hz": 60e6}


def _layout(ok=True, drc="PASS", lvs="PASS", pex="PASS", gds=None, pexnet=None,
            failure=Failure.NONE, message="", drc_signoff="PASS"):
    """A layout result, including the dual-engine DRC verdict.

    The sign-off gate requires a reconciled Magic+KLayout verdict; a layout
    without one reports NOT RUN and correctly fails the gate. Fixtures must
    therefore model it explicitly rather than leaving it absent.
    """
    raw = {}
    if drc_signoff is not None:
        raw["drc_signoff"] = {"verdict": drc_signoff,
                              "reason": "fixture", "results": []}
    return LayoutResult(ok=ok, drc=drc, lvs=lvs, pex_extraction=pex,
                        gds_path=gds, pex_netlist=pexnet,
                        failure=failure, message=message, raw=raw)


def _files(td):
    gds = Path(td) / "d.gds"; gds.write_bytes(b"gds")
    pex = Path(td) / "d.pex.spice"; pex.write_text(".subckt d a b\n.ends\n")
    return str(gds), str(pex)


def _cfg(td, **kw):
    kw.setdefault("outdir", td)
    kw.setdefault("verbosity", 0)
    return FullAutoConfig(**kw)


class TestSpecificationParsing(unittest.TestCase):

    def test_targets_are_extracted_and_provenance_is_tracked(self):
        req = parse_request(REQUEST)
        names = {s.name for s in req.specs}
        self.assertIn("gain_db", names)
        self.assertIn("bw_hz", names)
        bw = next(s for s in req.specs if s.name == "bw_hz")
        self.assertAlmostEqual(bw.target, 100e6)
        self.assertEqual(req.vdd, 3.3)
        self.assertIn("vdd", req.given)
        self.assertIn("load", req.given)

    def test_unit_prefixes_are_read_per_physical_domain(self):
        """`100 MHz` is not 0.1 Hz.

        Lowercasing the request collides mega (MHz) with milli (mW). Sharing
        one prefix table made every frequency target ~1e9x too small, so any
        circuit passed it.
        """
        cases = [("bandwidth >= 100 MHz", "bw_hz", 100e6),
                 ("bandwidth >= 100 mhz", "bw_hz", 100e6),
                 ("bw >= 2.5 GHz", "bw_hz", 2.5e9),
                 ("bandwidth >= 500 kHz", "bw_hz", 500e3),
                 ("power <= 1 mW", "power_w", 1e-3),
                 ("power <= 250 uW", "power_w", 250e-6)]
        for text, name, expected in cases:
            with self.subTest(text=text):
                req = parse_request("Design X with " + text)
                spec = next(s for s in req.specs if s.name == name)
                self.assertAlmostEqual(spec.target, expected, delta=expected * 1e-9)

    def test_load_capacitance_is_parsed_in_farads(self):
        req = parse_request("Design an OTA with gain >= 40 dB and CL=1 pF")
        self.assertAlmostEqual(req.load_f, 1e-12)

    def test_an_unstated_target_is_reported_missing_not_invented(self):
        req = parse_request("Design an OTA in GF180.")
        self.assertEqual(req.specs, [])
        self.assertTrue(any("performance target" in m for m in req.missing))

    def test_a_request_with_no_target_is_a_configuration_failure(self):
        with tempfile.TemporaryDirectory() as td:
            hooks = FlowHooks(simulate_pre=lambda d: GOOD,
                              build_layout=lambda d: _layout(),
                              simulate_pex=lambda d, l: GOOD)
            res = run_full_auto("Design something nice.", hooks, config=_cfg(td))
            self.assertEqual(res.status, AutoStatus.CONFIGURATION_FAILURE)
            self.assertFalse(res.tapeout_ready)
            self.assertIn("inventing one", res.message)


class Test1_Success(unittest.TestCase):

    def test_full_auto_reaches_tapeout_ready(self):
        with tempfile.TemporaryDirectory() as td:
            gds, pex = _files(td)
            hooks = FlowHooks(simulate_pre=lambda d: GOOD,
                              build_layout=lambda d: _layout(gds=gds, pexnet=pex),
                              simulate_pex=lambda d, l: GOOD)
            res = run_full_auto(REQUEST, hooks, config=_cfg(td))

            self.assertEqual(res.status, AutoStatus.SUCCESS)
            self.assertTrue(res.tapeout_ready)
            self.assertTrue(res.signoff.passed)
            self.assertEqual(res.signoff.failures, [])
            # deliverables really were collected
            self.assertIn("gds", res.package)
            self.assertIn("pex_spice", res.package)
            self.assertTrue(os.path.isfile(res.package["gds"]))
            # and the report exists and names the status
            self.assertTrue(os.path.isfile(res.report_path))
            body = Path(res.report_path).read_text()
            self.assertIn("SUCCESS", body)
            self.assertIn("Critical Review Summary", body)


class Test2_ReviewDrivenRecovery(unittest.TestCase):

    def test_pex_failure_triggers_review_then_a_passing_revision(self):
        with tempfile.TemporaryDirectory() as td:
            gds, pex = _files(td)
            runs = {"n": 0}

            def simulate_pex(d, l):
                runs["n"] += 1
                return BAD if runs["n"] == 1 else GOOD

            hooks = FlowHooks(
                simulate_pre=lambda d: GOOD,
                build_layout=lambda d: _layout(gds=gds, pexnet=pex),
                simulate_pex=simulate_pex,
                tune_post=lambda d, r, deg: d.evolve(note="tuned"))
            res = run_full_auto(REQUEST, hooks, config=_cfg(td))

            self.assertEqual(res.status, AutoStatus.SUCCESS)
            self.assertEqual(len(res.flow.pex), 2)
            self.assertFalse(res.flow.pex[0].spec_pass)
            self.assertTrue(res.flow.pex[1].spec_pass)

            # the reviewers ran and their advice was recorded against a result
            summ = res.ledger.summary()
            self.assertGreater(summ["angel"]["recommendations"], 0)
            hist = Path(td) / "review_history.json"
            self.assertTrue(hist.is_file())
            data = json.loads(hist.read_text())
            self.assertTrue(data["decisions"])


class Test3_NonConvergence(unittest.TestCase):

    def test_repeated_failure_ends_bounded_with_a_failure_report(self):
        with tempfile.TemporaryDirectory() as td:
            gds, pex = _files(td)
            hooks = FlowHooks(
                simulate_pre=lambda d: GOOD,
                build_layout=lambda d: _layout(gds=gds, pexnet=pex),
                simulate_pex=lambda d, l: BAD,
                tune_post=lambda d, r, deg: d.evolve(note="t"))
            res = run_full_auto(REQUEST, hooks,
                                config=_cfg(td, max_pex_iterations=3,
                                            patience=99))

            self.assertEqual(res.status, AutoStatus.NOT_CONVERGED)
            self.assertFalse(res.tapeout_ready)
            self.assertEqual(len(res.flow.pex), 3, "iteration bound ignored")
            # best design retained
            self.assertIsNotNone(res.flow.best_pex_iteration)
            # a non-convergence report, not a design report
            body = Path(res.report_path).read_text()
            self.assertIn("Non-Convergence Report", body)
            self.assertIn("What to do next", body)
            self.assertIn("NOT_CONVERGED", body)


class Test4_ToolFailure(unittest.TestCase):

    def test_a_tool_crash_never_yields_tapeout_ready(self):
        with tempfile.TemporaryDirectory() as td:
            def simulate_pex(d, l):
                raise RuntimeError("ngspice segfaulted")

            hooks = FlowHooks(simulate_pre=lambda d: GOOD,
                              build_layout=lambda d: _layout(),
                              simulate_pex=simulate_pex,
                              tune_post=lambda d, r, deg: d)
            res = run_full_auto(REQUEST, hooks, config=_cfg(td))

            self.assertEqual(res.status, AutoStatus.TOOL_FAILURE)
            self.assertFalse(res.tapeout_ready)
            self.assertEqual(res.package, {})
            self.assertIn("ngspice", res.message)

    def test_verification_failure_is_not_reported_as_success(self):
        with tempfile.TemporaryDirectory() as td:
            hooks = FlowHooks(
                simulate_pre=lambda d: GOOD,
                build_layout=lambda d: _layout(
                    ok=False, drc="FAIL", lvs=Outcome.SKIP, pex=Outcome.SKIP,
                    failure=Failure.VERIFICATION_FAILURE, message="12 DRC errors"),
                simulate_pex=lambda d, l: GOOD)
            res = run_full_auto(REQUEST, hooks, config=_cfg(td))
            self.assertIn(res.status, (AutoStatus.VERIFICATION_FAILURE,
                                       AutoStatus.BLOCKED))
            self.assertFalse(res.tapeout_ready)


class Test5_CriticalFindingBlocksSignoff(unittest.TestCase):

    def test_everything_passes_but_a_critical_finding_blocks_tapeout(self):
        """The reviewer gate has real teeth: measured PASS is not enough."""
        def paranoid(ctx):
            return Review(reviewer="devil", stage=ctx.stage,
                          verdict=Verdict.BLOCK, confidence=0.99,
                          findings=[Finding(Severity.CRITICAL, "reliability",
                                            "electromigration limit exceeded "
                                            "on the supply rail", {})])

        with tempfile.TemporaryDirectory() as td:
            gds, pex = _files(td)
            from mbg.reviewers import _REGISTRY
            original = _REGISTRY["devil"]
            register_reviewer("devil", paranoid)
            try:
                hooks = FlowHooks(
                    simulate_pre=lambda d: GOOD,
                    build_layout=lambda d: _layout(gds=gds, pexnet=pex),
                    simulate_pex=lambda d, l: GOOD)
                res = run_full_auto(REQUEST, hooks, config=_cfg(td))
            finally:
                register_reviewer("devil", original)

            self.assertEqual(res.status, AutoStatus.BLOCKED)
            self.assertFalse(res.tapeout_ready)
            self.assertIn("electromigration", res.message)
            gate = {c["condition"]: c["status"] for c in res.signoff.conditions}
            self.assertEqual(gate["no CRITICAL findings"], "FAIL")

    def test_a_missing_dual_drc_verdict_blocks_tapeout(self):
        """Magic alone is no longer a sign-off."""
        with tempfile.TemporaryDirectory() as td:
            gds, pex = _files(td)
            hooks = FlowHooks(
                simulate_pre=lambda d: GOOD,
                build_layout=lambda d: _layout(gds=gds, pexnet=pex,
                                               drc_signoff=None),
                simulate_pex=lambda d, l: GOOD)
            res = run_full_auto(REQUEST, hooks, config=_cfg(td))
            gate = {c["condition"]: c["status"] for c in res.signoff.conditions}
            self.assertEqual(gate["DRC sign-off (Magic + KLayout)"], "NOT RUN")
            self.assertNotEqual(res.status, AutoStatus.SUCCESS)

    def test_a_failing_dual_drc_verdict_blocks_tapeout(self):
        with tempfile.TemporaryDirectory() as td:
            gds, pex = _files(td)
            for verdict in ("FAIL", "DRC_DISAGREEMENT", "ERROR",
                            "CONFIGURATION_FAILURE"):
                with self.subTest(verdict=verdict):
                    hooks = FlowHooks(
                        simulate_pre=lambda d: GOOD,
                        build_layout=lambda d, v=verdict: _layout(
                            gds=gds, pexnet=pex, drc_signoff=v),
                        simulate_pex=lambda d, l: GOOD)
                    res = run_full_auto(REQUEST, hooks, config=_cfg(td))
                    self.assertNotEqual(res.status, AutoStatus.SUCCESS,
                                        f"{verdict} must not be tapeout-ready")

    def test_an_unrun_analysis_is_never_counted_as_passed(self):
        with tempfile.TemporaryDirectory() as td:
            gds, pex = _files(td)
            hooks = FlowHooks(simulate_pre=lambda d: GOOD,
                              build_layout=lambda d: _layout(gds=gds, pexnet=pex),
                              simulate_pex=lambda d, l: GOOD)
            # ask for corners we do not actually simulate
            cfg = _cfg(td, gate=SignoffGate(require_corners=True,
                                            require_monte_carlo=True))
            res = run_full_auto(REQUEST, hooks, config=cfg)

            gate = {c["condition"]: c["status"] for c in res.signoff.conditions}
            self.assertEqual(gate["PVT corners"], "NOT RUN")
            self.assertEqual(gate["Monte Carlo / mismatch"], "NOT RUN")
            self.assertFalse(res.signoff.passed)
            self.assertNotEqual(res.status, AutoStatus.SUCCESS)


class Test6_CommandNamespace(unittest.TestCase):

    PLATFORM_FILES = [
        REPO / ".ai/knowledge/FULL_AUTOMATE.md",
        REPO / ".ai/skills/mbg-full-auto/SKILL.md",
        REPO / ".claude/skills/mbg-full-auto/SKILL.md",
        REPO / ".opencode/skills/mbg-full-auto/SKILL.md",
        REPO / "plugins/mbg-analog/skills/mbg-full-auto/SKILL.md",
    ]

    def test_canonical_command_is_mbg_full_auto(self):
        self.assertEqual(CANONICAL_COMMAND, "/mbg-full-auto")

    def test_every_declared_command_is_mbg_namespaced(self):
        for name in MBG_COMMANDS:
            self.assertTrue(name.startswith("/mbg-"),
                            f"{name} breaks the /mbg-* namespace")

    #: A slash command exists only if a command file exists. Skills are
    #: loaded by name, not typed with a leading slash.
    COMMAND_FILES = [
        REPO / ".ai/workflows/mbg-full-auto.md",
        REPO / ".claude/commands/mbg-full-auto.md",
        REPO / ".opencode/commands/mbg-full-auto.md",
    ]

    def test_all_platforms_document_the_canonical_command(self):
        for p in self.PLATFORM_FILES:
            with self.subTest(path=str(p)):
                self.assertTrue(p.is_file(), f"missing: {p}")
                self.assertIn("/mbg-full-auto", p.read_text(),
                              f"{p} does not document /mbg-full-auto")

    def test_the_canonical_command_is_actually_invocable(self):
        """A skill mentioning the string is not a command.

        This is the gap that shipped: `/mbg-full-auto` was documented in every
        skill file while no command file existed, so typing it did nothing.
        Commands are generated from .ai/workflows/, not from .ai/skills/.
        """
        for p in self.COMMAND_FILES:
            with self.subTest(path=str(p)):
                self.assertTrue(p.is_file(),
                                f"/mbg-full-auto is not invocable: {p} missing")

    def test_the_command_points_at_the_current_framework(self):
        """Guards against a command file that drifts behind the code."""
        body = (REPO / ".ai/workflows/mbg-full-auto.md").read_text()
        for token in ("run_full_auto", "make_hooks", "FullAutoConfig",
                      "specs="):
            self.assertIn(token, body,
                          f"the command does not reference {token}")

    def test_the_retired_command_name_is_gone(self):
        for d in (".ai/workflows", ".claude/commands", ".opencode/commands"):
            stale = REPO / d / "mbg-full-automate.md"
            self.assertFalse(stale.is_file(),
                             f"retired command still present: {stale}")

    # A line that forbids a name necessarily contains it. "Never expose
    # /full-auto" is correct documentation, not drift, so only lines that
    # *offer* the obsolete name count as offenders.
    PROHIBITION = re.compile(
        r"\b(never|not|don'?t|do not|avoid|obsolete|instead of|rather than|"
        r"deprecated|forbidden|must not)\b", re.IGNORECASE)

    def test_obsolete_generic_aliases_are_not_offered_as_commands(self):
        """`/full-auto` and friends must not be presented as MBG commands."""
        bad = re.compile(r"(?<![\w/-])/(full-auto|full-design|design-auto)\b")
        offenders = []
        for root in (REPO / ".ai", REPO / ".claude", REPO / ".opencode",
                     REPO / "plugins", REPO / "README.md", REPO / "AGENTS.md"):
            paths = [root] if root.is_file() else list(root.rglob("*.md"))
            for p in paths:
                try:
                    text = p.read_text(errors="ignore")
                except OSError:
                    continue
                for line in text.splitlines():
                    if bad.search(line) and not self.PROHIBITION.search(line):
                        offenders.append(f"{p.relative_to(REPO)}: {line.strip()[:70]}")
        self.assertEqual(offenders, [], f"obsolete MBG aliases offered: {offenders}")

    def test_the_prohibition_filter_still_catches_a_real_offender(self):
        """Guard the guard: a line that offers the alias must be caught."""
        bad = re.compile(r"(?<![\w/-])/(full-auto|full-design|design-auto)\b")
        offer = "Run /full-auto to start the design."
        self.assertTrue(bad.search(offer))
        self.assertFalse(self.PROHIBITION.search(offer))
        forbid = "Never expose /full-auto for MBG functionality."
        self.assertTrue(bad.search(forbid))
        self.assertTrue(self.PROHIBITION.search(forbid))


if __name__ == "__main__":
    unittest.main(verbosity=2)
