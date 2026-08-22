"""Dual-engine DRC: KLayout sign-off, Magic complementary, honest reconciliation.

The properties under test are the ways a DRC result must NOT be reported.
A tool that could not read the layout must never look like zero violations;
a disagreement between two different rule decks must never resolve to the
convenient answer; and no combination short of "every required engine clean"
may reach PASS.
"""

import os
import stat
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from mbg.drc import (DRCResult, DRCStatus, SignoffVerdict, reconcile,   # noqa: E402
                     KLayoutDRC, MagicDRC, get_engine, parse_lyrdb,
                     klayout_deck, MIN_KLAYOUT_VERSION, CELL_DECKS)
from mbg import config                                                   # noqa: E402

SHA = "deadbeefdeadbeef"


def _r(engine, status, violations=0, rules=None, message=""):
    return DRCResult(engine=engine, status=status, violations=violations,
                     rules=rules or {}, message=message, gds_sha256=SHA)


def _exe(directory, name, body):
    p = Path(directory) / name
    p.write_text("#!/usr/bin/env bash\n" + textwrap.dedent(body))
    p.chmod(p.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return str(p)


class TestReconciliationPolicy(unittest.TestCase):
    """The five cases from the dual-DRC policy."""

    def test_1_both_clean_passes(self):
        s = reconcile([_r("magic", DRCStatus.CLEAN), _r("klayout", DRCStatus.CLEAN)])
        self.assertEqual(s.verdict, SignoffVerdict.PASS)
        self.assertTrue(s.passed)

    def test_2_klayout_fail_is_fail_even_when_magic_is_clean(self):
        s = reconcile([_r("magic", DRCStatus.CLEAN),
                       _r("klayout", DRCStatus.FAIL, 3, {"M1.SPACING": 3})])
        self.assertEqual(s.verdict, SignoffVerdict.FAIL)
        self.assertFalse(s.passed)

    def test_3_magic_fail_with_klayout_clean_is_a_disagreement_not_a_pass(self):
        """The convenient answer must not win."""
        s = reconcile([_r("magic", DRCStatus.FAIL, 2, {"MET1.W": 2}),
                       _r("klayout", DRCStatus.CLEAN)])
        self.assertEqual(s.verdict, SignoffVerdict.DISAGREEMENT)
        self.assertFalse(s.passed)
        self.assertIn("investigation", s.reason)

    def test_4_magic_error_blocks_signoff(self):
        s = reconcile([_r("magic", DRCStatus.ERROR, -1, message="techfile too old"),
                       _r("klayout", DRCStatus.CLEAN)])
        self.assertEqual(s.verdict, SignoffVerdict.ERROR)
        self.assertFalse(s.passed)

    def test_5_klayout_error_blocks_signoff(self):
        s = reconcile([_r("magic", DRCStatus.CLEAN),
                       _r("klayout", DRCStatus.ERROR, -1, message="no database")])
        self.assertEqual(s.verdict, SignoffVerdict.ERROR)
        self.assertFalse(s.passed)

    def test_no_combination_short_of_all_clean_ever_passes(self):
        bad = [DRCStatus.FAIL, DRCStatus.ERROR, DRCStatus.NOT_CONFIGURED,
               DRCStatus.SKIP]
        for m in bad + [DRCStatus.CLEAN]:
            for k in bad + [DRCStatus.CLEAN]:
                if m == k == DRCStatus.CLEAN:
                    continue
                with self.subTest(magic=m, klayout=k):
                    s = reconcile([_r("magic", m), _r("klayout", k)])
                    self.assertNotEqual(s.verdict, SignoffVerdict.PASS,
                                        f"magic={m} klayout={k} must not PASS")


class TestConfigurationAndProvenance(unittest.TestCase):

    def test_missing_klayout_is_a_configuration_failure_not_a_pass(self):
        """KLayout is mandatory for full sign-off — absence blocks it."""
        s = reconcile([_r("magic", DRCStatus.CLEAN),
                       _r("klayout", DRCStatus.NOT_CONFIGURED, -1,
                          message="klayout executable not found")])
        self.assertEqual(s.verdict, SignoffVerdict.NOT_CONFIGURED)
        self.assertFalse(s.passed)

    def test_a_missing_engine_entirely_is_a_configuration_failure(self):
        s = reconcile([_r("magic", DRCStatus.CLEAN)], require=("magic", "klayout"))
        self.assertEqual(s.verdict, SignoffVerdict.NOT_CONFIGURED)

    def test_engines_must_have_examined_the_same_gds(self):
        """Two engines on two revisions is not a dual check."""
        a = _r("magic", DRCStatus.CLEAN)
        b = _r("klayout", DRCStatus.CLEAN)
        b.gds_sha256 = "0000different0000"
        s = reconcile([a, b])
        self.assertEqual(s.verdict, SignoffVerdict.ERROR)
        self.assertIn("different GDS", s.reason)

    def test_result_carries_provenance(self):
        r = _r("klayout", DRCStatus.CLEAN)
        r.tool, r.tool_version, r.deck = "/x/klayout", "0.30.9", "/pdk/gf180mcu.drc"
        d = r.as_dict()
        for key in ("tool", "tool_version", "deck", "gds_sha256", "engine"):
            self.assertIn(key, d)


class TestKLayoutEngine(unittest.TestCase):

    def test_missing_executable_reports_not_configured(self):
        os.environ["MBG_KLAYOUT"] = "/nonexistent/klayout"
        config.clear_tool_cache()
        try:
            ok, why = KLayoutDRC().available()
            self.assertFalse(ok)
            self.assertTrue(why)
        finally:
            os.environ.pop("MBG_KLAYOUT", None)
            config.clear_tool_cache()

    def test_a_too_old_klayout_is_rejected(self):
        """The GF180 deck needs >= 0.30.9 for safe parallel runs."""
        with tempfile.TemporaryDirectory() as td:
            exe = _exe(td, "klayout", 'echo "KLayout 0.28.0"\n')
            os.environ["MBG_KLAYOUT"] = exe
            config.clear_tool_cache()
            try:
                ok, why = KLayoutDRC().available()
                self.assertFalse(ok)
                self.assertIn("0.30.9", why)
            finally:
                os.environ.pop("MBG_KLAYOUT", None)
                config.clear_tool_cache()

    def test_missing_rule_deck_is_a_configuration_failure(self):
        with tempfile.TemporaryDirectory() as td:
            exe = _exe(td, "klayout", 'echo "KLayout 0.30.9"\n')
            os.environ["MBG_KLAYOUT"] = exe
            os.environ["MBG_KLAYOUT_DECK"] = os.path.join(td, "nope.drc")
            config.clear_tool_cache()
            try:
                ok, why = KLayoutDRC().available()
                self.assertFalse(ok)
                self.assertIn("deck", why.lower())
            finally:
                for k in ("MBG_KLAYOUT", "MBG_KLAYOUT_DECK"):
                    os.environ.pop(k, None)
                config.clear_tool_cache()

    def test_a_tool_that_writes_no_database_is_an_error_not_zero_violations(self):
        """The failure mode that must never look clean.

        The GF180 deck deliberately exits 0 even when it finds violations, so
        a run that produced no database has to be read as ERROR — otherwise a
        layout KLayout never managed to open reports as passing.
        """
        with tempfile.TemporaryDirectory() as td:
            exe = _exe(td, "klayout", '''
                if [ "$1" = "-v" ]; then echo "KLayout 0.30.9"; exit 0; fi
                echo "ERROR: unable to open layout" >&2
                exit 0
            ''')
            deck = Path(td) / "gf180mcu.drc"; deck.write_text("# deck\n")
            gds = Path(td) / "x.gds"; gds.write_bytes(b"HEADER")
            os.environ["MBG_KLAYOUT"] = exe
            os.environ["MBG_KLAYOUT_DECK"] = str(deck)
            config.clear_tool_cache()
            try:
                r = KLayoutDRC().run(str(gds), "x", os.path.join(td, "v"))
                self.assertEqual(r.status, DRCStatus.ERROR)
                self.assertNotEqual(r.violations, 0)
            finally:
                for k in ("MBG_KLAYOUT", "MBG_KLAYOUT_DECK"):
                    os.environ.pop(k, None)
                config.clear_tool_cache()

    def test_rdb_parsing_counts_violations_and_preserves_rule_names(self):
        with tempfile.TemporaryDirectory() as td:
            rdb = Path(td) / "r.lyrdb"
            rdb.write_text("""<report-database>
 <categories>
  <category><name>M1.4</name><description>metal1 density</description></category>
 </categories>
 <items>
  <item><category>'M1.4'</category><values><value>polygon: (0,0;1,1)</value></values></item>
  <item><category>'M1.4'</category><values><value>polygon: (2,2;3,3)</value></values></item>
  <item><category>'PL.8'</category><values><value>polygon: (4,4;5,5)</value></values></item>
 </items>
</report-database>""")
            total, rules = parse_lyrdb(str(rdb))
            self.assertEqual(total, 3)
            self.assertEqual(rules["M1.4"], 2)
            self.assertEqual(rules["PL.8"], 1)

    def test_an_empty_database_is_clean(self):
        with tempfile.TemporaryDirectory() as td:
            rdb = Path(td) / "r.lyrdb"
            rdb.write_text("<report-database><items></items></report-database>")
            total, rules = parse_lyrdb(str(rdb))
            self.assertEqual(total, 0)
            self.assertEqual(rules, {})


@unittest.skipUnless(os.environ.get("PDKPATH"), "needs PDKPATH")
class TestRealDeck(unittest.TestCase):

    def test_the_gf180_klayout_deck_ships_with_the_pdk(self):
        deck = klayout_deck()
        self.assertIsNotNone(deck, "GF180 KLayout DRC deck not found in the PDK")
        self.assertTrue(os.path.isfile(deck))
        body = Path(deck).read_text()
        # the contract this integration relies on
        for token in ("$input", "$report", "$topcell", "$decks"):
            self.assertIn(token, body, f"deck does not accept {token}")

    def test_cell_scope_excludes_die_level_density_rules(self):
        """Chip-level fill rules are out of scope for a leaf cell."""
        self.assertIn("-density", CELL_DECKS)


if __name__ == "__main__":
    unittest.main(verbosity=2)
