"""Installer contract tests for the single-file ``install.sh``.

The five former install scripts were merged into one file with six stages.
Nothing tested that file, and a real defect shipped in the gap: in check mode
``do_shell``'s loop variable was named ``rc``, the same name the dispatcher
used to hold ``do_check``'s status. Reading the shell rc files emptied it, so
``exit $rc`` became a bare ``exit`` and returned the status of the *previous*
command instead. ``./install.sh --check --stage shell`` therefore exited 1
while every line it printed said PASS — a false failure that would fail a CI
gate with no visible cause.

These tests only exercise modes that install nothing: --help, --list, --check
and argument rejection.
"""

import re
import subprocess
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
INSTALLER = REPO / "install.sh"
STAGES = ("python", "pdk", "eda", "shell", "agents", "global")


def run(*args, timeout=600):
    return subprocess.run(
        [str(INSTALLER), *args],
        capture_output=True, text=True, timeout=timeout, cwd=str(REPO),
    )


class TestInstallerExists(unittest.TestCase):
    def test_installer_is_present_and_executable(self):
        self.assertTrue(INSTALLER.is_file(), "install.sh is missing")
        self.assertTrue(INSTALLER.stat().st_mode & 0o111, "install.sh is not executable")

    def test_installer_parses(self):
        r = subprocess.run(["bash", "-n", str(INSTALLER)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, f"install.sh has a syntax error:\n{r.stderr}")

    def test_no_developer_paths_are_baked_in(self):
        # Needles are built up so this file never matches its own check, the
        # same way tests/test_environment.py does it.
        text = INSTALLER.read_text()
        for bad in ("/home/" + "huda", "/Users" + "/"):
            self.assertNotIn(bad, text, f"install.sh hard-codes {bad}")


class TestHelp(unittest.TestCase):
    """--help prints the header comment and must stop at the first line of code."""

    def test_help_succeeds_and_describes_every_stage(self):
        r = run("--help")
        self.assertEqual(r.returncode, 0, r.stderr)
        for stage in STAGES:
            self.assertIn(stage, r.stdout, f"--help does not mention the {stage} stage")

    def test_help_does_not_leak_script_source(self):
        # usage() used to print a hard-coded line range, which drifted past the
        # end of the comment block and dumped real code into the help text.
        out = run("--help").stdout
        for leak in ("set -uo pipefail", "REPO_ROOT=", "#!/usr/bin/env"):
            self.assertNotIn(leak, out, f"--help leaks script source: {leak!r}")

    def test_list_names_every_stage(self):
        r = run("--list")
        self.assertEqual(r.returncode, 0, r.stderr)
        for stage in STAGES:
            self.assertIn(stage, r.stdout)


class TestArgumentRejection(unittest.TestCase):
    def test_unknown_stage_is_rejected_with_a_distinct_status(self):
        r = run("--stage", "nonesuch")
        self.assertEqual(r.returncode, 2, "an unknown stage must exit 2, not install anything")
        self.assertIn("nonesuch", r.stdout + r.stderr)

    def test_rejection_lists_the_valid_stages(self):
        r = run("--stage", "nonesuch")
        combined = r.stdout + r.stderr
        for stage in STAGES:
            self.assertIn(stage, combined, "the error should show what the valid stages are")


class TestCheckModeExitStatus(unittest.TestCase):
    """The regression that motivated this file.

    --check installs nothing, so its exit status is pure signal: it must
    reflect the environment, and must not depend on which stage was selected.
    """

    def test_a_nonzero_check_always_says_what_failed(self):
        """A non-zero --check must be explained by something it printed.

        Only this direction is asserted. The reverse does not hold: `agents`
        and `global` are optional stages, so their checks can legitimately
        print a failure while the overall verdict stays 0 — a stale generated
        adapter does not make the environment unusable. Asserting "exit 0
        implies no FAIL anywhere" would couple this test to the output of
        every tool install.sh shells out to.
        """
        for stage in (None, *STAGES):
            args = ("--check",) if stage is None else ("--check", "--stage", stage)
            with self.subTest(stage=stage or "all"):
                r = run(*args)
                if r.returncode == 0:
                    continue
                out = r.stdout + r.stderr
                self.assertRegex(
                    out, r"\bFAIL(ED)?\b",
                    f"./install.sh {' '.join(args)} exited {r.returncode} but "
                    f"printed nothing that explains it — a false failure.\n"
                    f"{out[-2000:]}",
                )

    def test_stage_selection_does_not_change_the_verdict(self):
        # Every stage check runs the same environment report; selecting a stage
        # only adds a section. The verdict must therefore be identical.
        baseline = run("--check").returncode
        for stage in STAGES:
            with self.subTest(stage=stage):
                self.assertEqual(
                    run("--check", "--stage", stage).returncode, baseline,
                    f"--check --stage {stage} disagrees with plain --check",
                )

    def test_dry_run_is_an_alias_for_check(self):
        self.assertEqual(run("--dry-run").returncode, run("--check").returncode)


class TestGeneratedFileReferences(unittest.TestCase):
    def test_installer_does_not_cite_the_scripts_it_replaced(self):
        # The five merged scripts are gone; a generated file that names one
        # tells the user to run something that does not exist.
        text = INSTALLER.read_text()
        for dead in ("scripts/setup_env.sh", "install_shell.sh",
                     "install_agents.sh", "install_global.sh"):
            self.assertNotIn(
                dead, text,
                f"install.sh still refers to the removed script {dead}",
            )


class TestSetupDocsKnowTheRealInstall(unittest.TestCase):
    """The skills must describe the environment the installer actually builds.

    All three platforms once documented only "run the installer" and knew
    nothing about $MBG_HOME. An agent asked why `mbg` was not a command, or
    why /mbg-* worked only inside the clone, had nothing to go on, because the
    canonical skill had never been updated after the global-install work.
    """

    SETUP_DOCS = (
        ".ai/skills/mbg-setup/SKILL.md",
        ".claude/skills/mbg-setup/SKILL.md",
        ".opencode/skills/mbg-setup/SKILL.md",
        "plugins/mbg-analog/skills/mbg-setup/SKILL.md",
        ".ai/workflows/mbg-install.md",
        ".claude/commands/mbg-install.md",
        ".opencode/commands/mbg-install.md",
    )

    def test_every_platform_documents_mbg_home(self):
        for rel in self.SETUP_DOCS:
            with self.subTest(doc=rel):
                f = REPO / rel
                self.assertTrue(f.is_file(), f"{rel} is missing")
                text = f.read_text()
                self.assertRegex(
                    text, r"MBG_HOME|~/\.mbg|\$HOME/\.mbg",
                    f"{rel} never mentions where MBG installs to",
                )

    def test_every_platform_documents_the_launcher(self):
        for rel in self.SETUP_DOCS:
            with self.subTest(doc=rel):
                self.assertRegex(
                    (REPO / rel).read_text(), r"mbg check|mbg-python|bin/mbg",
                    f"{rel} never mentions the mbg launcher",
                )

    def test_setup_docs_do_not_name_removed_scripts(self):
        for rel in self.SETUP_DOCS:
            with self.subTest(doc=rel):
                text = (REPO / rel).read_text()
                for dead in ("scripts/setup_env.sh", "install_shell.sh",
                             "install_agents.sh", "install_global.sh"):
                    self.assertNotIn(dead, text, f"{rel} names removed {dead}")

    def test_setup_docs_only_offer_flags_the_installer_accepts(self):
        """`--locked` was documented for years and never existed.

        A flag is checked on any line that does not name some other command,
        because the flag that caused this was written in prose, not next to
        `./install.sh`. Anything absent from the installer entirely is wrong.
        """
        accepted = set(re.findall(r"--[a-z][a-z-]+", INSTALLER.read_text()))
        other_cmd = re.compile(r"\.py\b|volare|pip |codex |git |python3? ")
        for rel in self.SETUP_DOCS:
            with self.subTest(doc=rel):
                for line in (REPO / rel).read_text().splitlines():
                    if other_cmd.search(line):
                        continue
                    for f in re.findall(r"--[a-z][a-z-]+", line):
                        self.assertIn(
                            f, accepted,
                            f"{rel} documents `{f}`, which appears nowhere in "
                            f"install.sh:\n  {line.strip()}",
                        )


class TestCodexCacheStaleness(unittest.TestCase):
    """Codex copies the plugin at install time; nothing used to notice drift.

    `codex plugin list` still reports "installed" for a cache holding last
    week's instructions, so a check that only asks whether the plugin is
    installed reported "ready" while the agent ran stale skills. That is the
    Codex half of the same bug.
    """

    def test_installer_compares_the_cache_against_the_generated_skills(self):
        text = INSTALLER.read_text()
        self.assertIn("codex_cache_stale_count", text,
                      "install.sh has no Codex cache staleness check")
        self.assertRegex(text, r"\bcmp\b",
                         "the staleness check must compare file contents")

    def test_a_stale_cache_is_reported_not_called_ready(self):
        text = INSTALLER.read_text()
        self.assertRegex(
            text, r"STALE.{0,80}install\.sh --stage agents",
            "a stale Codex cache must name the command that refreshes it",
        )


if __name__ == "__main__":
    unittest.main()
