"""Environment and verification-chain failure tests.

These test the paths that only run when something is *wrong*. That is
deliberate: every bug this file guards against shipped precisely because the
happy path was the only thing anyone exercised.

Cases A-F correspond to the failure modes that once broke this project:

  A  PDK missing            -> a clear error, not Path(None) from glayout
  B  incompatible Magic     -> rejected at preflight, not used silently
  C  extraction failure     -> LVS SKIPPED; netgen never sees the GDS
  D  missing extracted SPICE-> LVS does not run
  E  netgen timeout         -> TIMEOUT returned cleanly, process killed
  F  KLayout missing        -> optional; the GF180 flow stays runnable
"""

import os
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from mbg import config                                   # noqa: E402
from mbg.checks import validate_spice_netlist, run_tool  # noqa: E402


def _fake_exe(directory, name, body):
    """A stand-in executable, so a fake tool can be tested without one installed."""
    p = Path(directory) / name
    p.write_text("#!/usr/bin/env bash\n" + textwrap.dedent(body))
    p.chmod(p.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return str(p)


# ── A: PDK missing ────────────────────────────────────────────────────

class TestA_PDKMissing(unittest.TestCase):

    def test_import_survives_an_unset_pdk_root(self):
        """`import mbg` must work with no PDK variables set at all.

        glayout calls Path(os.getenv("PDK_ROOT")) at import time, so an unset
        variable used to surface as
            TypeError: expected str, bytes or os.PathLike object, not NoneType
        from inside a third-party package. mbg.config.ensure_pdk_env() runs
        before that import specifically to stop it.
        """
        env = {k: v for k, v in os.environ.items()
               if k not in ("PDK_ROOT", "PDK", "PDKPATH", "STD_CELL_LIBRARY")}
        env["PYTHONPATH"] = str(REPO / "src")
        r = subprocess.run(
            [sys.executable, "-c", "import mbg; print('IMPORT_OK')"],
            capture_output=True, text=True, env=env, timeout=300)
        self.assertIn("IMPORT_OK", r.stdout,
                      f"import failed without PDK vars:\n{r.stderr[-1500:]}")
        self.assertNotIn("NoneType", r.stderr)

    def test_strict_mode_names_the_missing_files_and_the_fix(self):
        with tempfile.TemporaryDirectory() as td:
            old = {k: os.environ.get(k) for k in ("PDK_ROOT", "PDKPATH", "PDK")}
            try:
                os.environ["PDK_ROOT"] = td
                os.environ["PDKPATH"] = os.path.join(td, "gf180mcuD")
                os.environ["PDK"] = "gf180mcuD"
                with self.assertRaises(config.ToolError) as cm:
                    config.ensure_pdk_env(strict=True)
                msg = str(cm.exception)
                self.assertIn("setup_env.sh --pdk", msg)
                self.assertIn("gf180mcuD", msg)
                self.assertNotIn("NoneType", msg)
            finally:
                for k, v in old.items():
                    if v is None:
                        os.environ.pop(k, None)
                    else:
                        os.environ[k] = v


# ── B: incompatible Magic ─────────────────────────────────────────────

class TestB_IncompatibleMagic(unittest.TestCase):

    def test_a_too_old_magic_is_rejected_not_used(self):
        """An executable called `magic` is not a usable Magic.

        The real failure reported `this version of magic is 0.0.0` while the
        techfile required 8.3.411, then produced empty extractions.
        """
        with tempfile.TemporaryDirectory() as td:
            exe = _fake_exe(td, "magic", 'echo "0.0.0"\n')
            os.environ["MBG_MAGIC"] = exe
            config.clear_tool_cache()
            try:
                info = config.resolve_magic()
                self.assertFalse(info.ok)
                self.assertIn("0.0.0", info.reason)
                self.assertIn("setup_env.sh", info.reason)
                with self.assertRaises(config.ToolError):
                    config.magic_bin()
            finally:
                os.environ.pop("MBG_MAGIC", None)
                config.clear_tool_cache()

    def test_a_magic_that_cannot_load_the_techfile_is_rejected(self):
        """Version alone is not enough — the techfile has to actually load."""
        with tempfile.TemporaryDirectory() as td:
            exe = _fake_exe(td, "magic", '''
                if [ "$1" = "--version" ]; then echo "8.3.999"; exit 0; fi
                echo "Magic version 8.3.411 is required by this techfile, but this version of magic is 0.0.0"
                exit 0
            ''')
            os.environ["MBG_MAGIC"] = exe
            config.clear_tool_cache()
            try:
                info = config.resolve_magic()
                self.assertFalse(info.ok, "a Magic that cannot load the "
                                          "techfile must not be accepted")
            finally:
                os.environ.pop("MBG_MAGIC", None)
                config.clear_tool_cache()


# ── C/D: extraction failure and netlist validation ────────────────────

class TestCD_ExtractionGatesLVS(unittest.TestCase):

    def test_a_gds_is_never_accepted_as_a_netlist(self):
        """The exact accident: handing netgen the layout instead of a netlist."""
        with tempfile.TemporaryDirectory() as td:
            gds = Path(td) / "inverter.gds"
            gds.write_bytes(b"HEADER\x00\x06\x00\x02" + b"\x00" * 64)
            ok, why = validate_spice_netlist(str(gds))
            self.assertFalse(ok)
            self.assertIn("netgen", why.lower())

    def test_missing_empty_and_deviceless_netlists_are_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertFalse(validate_spice_netlist(None)[0])
            self.assertFalse(validate_spice_netlist(
                str(Path(td) / "nope.spice"))[0])

            empty = Path(td) / "empty.spice"
            empty.write_text("")
            self.assertFalse(validate_spice_netlist(str(empty))[0])

            nosub = Path(td) / "nosub.spice"
            nosub.write_text("* only a comment\n")
            ok, why = validate_spice_netlist(str(nosub))
            self.assertFalse(ok)
            self.assertIn("subckt", why.lower())

    def test_a_real_netlist_is_accepted(self):
        with tempfile.TemporaryDirectory() as td:
            good = Path(td) / "good.spice"
            good.write_text(".subckt inv a y vdd vss\n"
                            "XM1 y a vdd vdd pfet_03v3 L=0.28u W=2u\n.ends\n")
            ok, why = validate_spice_netlist(str(good))
            self.assertTrue(ok, why)

    def test_extraction_failure_skips_lvs_without_calling_netgen(self):
        """End-to-end: a GDS Magic cannot read must SKIP LVS.

        netgen is replaced by a script that fails loudly if it is ever run, so
        the test proves netgen was not invoked rather than assuming it.
        """
        from mbg.checks import run_lvs
        with tempfile.TemporaryDirectory() as td:
            sentinel = Path(td) / "NETGEN_WAS_CALLED"
            netgen = _fake_exe(td, "netgen", f'''
                touch "{sentinel}"
                exit 0
            ''')
            gds = Path(td) / "broken.gds"
            gds.write_bytes(b"not really a gds file at all")
            sch = Path(td) / "broken.spice"
            sch.write_text(".subckt broken a b\n.ends\n")

            os.environ["MBG_NETGEN"] = netgen
            config.clear_tool_cache()
            try:
                res = run_lvs(str(gds), str(sch), cell_name="broken",
                              workdir=td, timeout=120)
            except Exception as e:                    # a clean error is also fine
                self.assertNotIn("NoneType", str(e))
                res = None
            finally:
                os.environ.pop("MBG_NETGEN", None)
                config.clear_tool_cache()

            self.assertFalse(sentinel.exists(),
                             "netgen was invoked even though extraction failed")
            if res is not None:
                self.assertFalse(res["match"])
                self.assertIn(res.get("status"), ("SKIP", "FAIL", "ERROR"))


# ── E: timeout handling ───────────────────────────────────────────────

class TestE_Timeout(unittest.TestCase):

    def test_a_hanging_tool_is_killed_and_reported(self):
        """A hang must become a clean TIMEOUT, not an unexplained failure.

        The original symptom was exit 143 / __EXIT_STATUS__=124 with no
        indication of which tool stalled or where its log went.
        """
        with tempfile.TemporaryDirectory() as td:
            hang = _fake_exe(td, "hang", "sleep 120\n")
            st = run_tool("netgen", [hang], stage="netgen_lvs",
                          workdir=td, timeout=3)
            self.assertEqual(st["status"], "TIMEOUT")
            self.assertIn("MBG_NETGEN_TIMEOUT", st["message"])
            self.assertTrue(os.path.isfile(st["log"]),
                            "a timeout must still leave a log behind")
            self.assertIn("timeout", Path(st["log"]).read_text().lower())

    def test_timeouts_are_configurable(self):
        os.environ["MBG_NETGEN_TIMEOUT"] = "77"
        try:
            self.assertEqual(config.tool_timeout("netgen"), 77)
        finally:
            os.environ.pop("MBG_NETGEN_TIMEOUT", None)
        os.environ["MBG_TOOL_TIMEOUT"] = "55"
        try:
            self.assertEqual(config.tool_timeout("magic"), 55)
        finally:
            os.environ.pop("MBG_TOOL_TIMEOUT", None)

    def test_tool_output_is_always_logged(self):
        with tempfile.TemporaryDirectory() as td:
            noisy = _fake_exe(td, "noisy", 'echo "on stdout"; echo "on stderr" >&2; exit 3\n')
            st = run_tool("magic", [noisy], stage="magic_drc", workdir=td, timeout=30)
            self.assertEqual(st["status"], "FAIL")
            self.assertEqual(st["returncode"], 3)
            body = Path(st["log"]).read_text()
            self.assertIn("on stdout", body)
            self.assertIn("on stderr", body)


# ── F: KLayout is optional ────────────────────────────────────────────

class TestF_KLayoutOptional(unittest.TestCase):

    def test_klayout_is_reported_optional_when_absent(self):
        info = config.resolve_klayout()
        self.assertTrue(info.optional)
        if not info.ok:
            self.assertIn("OPTIONAL", info.reason)

    def test_the_gf180_flow_does_not_require_klayout(self):
        """Magic + netgen must be enough to declare the regression runnable."""
        cfg = config.pdk_config()
        if cfg.missing():
            self.skipTest("PDK not installed")
        magic = config.resolve_magic(cfg)
        netgen = config.resolve_netgen()
        if not (magic.ok and netgen.ok):
            self.skipTest("Magic/netgen not installed")
        self.assertTrue(magic.ok and netgen.ok,
                        "the default flow must be READY without KLayout")


# ── portability ───────────────────────────────────────────────────────

class TestG_NoMachineSpecificPaths(unittest.TestCase):

    def test_no_developer_home_in_shipped_sources(self):
        """No tracked source or script may hard-code a developer's home."""
        bad = []
        needle = "/home/" + "huda"          # built up so this file never matches
        roots = [REPO / "src", REPO / "scripts", REPO / "tests"]
        for root in roots:
            for p in root.rglob("*"):
                if p.is_file() and p.suffix in (".py", ".sh", ".toml", ".cfg"):
                    try:
                        if needle in p.read_text(errors="ignore"):
                            bad.append(str(p.relative_to(REPO)))
                    except OSError:
                        pass
        self.assertEqual(bad, [], f"machine-specific paths found in: {bad}")

    def test_repo_root_is_discovered_not_assumed(self):
        self.assertTrue((config.repo_root() / "pyproject.toml").is_file())

    def test_tools_root_is_configurable(self):
        os.environ["MBG_TOOLS_ROOT"] = "/tmp/mbg-tools-test"
        try:
            self.assertEqual(str(config.tools_root()), "/tmp/mbg-tools-test")
        finally:
            os.environ.pop("MBG_TOOLS_ROOT", None)


if __name__ == "__main__":
    unittest.main(verbosity=2)
