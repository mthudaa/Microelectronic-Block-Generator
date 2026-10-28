"""The agent CLI contract: one JSON envelope on stdout, stable exit codes.

These run the real launcher (`scripts/mbg`) as a subprocess, the way every
agent harness calls it, and need no EDA tools or PDK.
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

from mbg.agent import registry, runio  # noqa: E402
from mbg.agent.cli import parse_number  # noqa: E402

MBG = os.path.join(ROOT, "scripts", "mbg")
OTA = os.path.join(ROOT, "tests", "netlists", "ota_5t.spice")


def run(*args, env=None):
    e = dict(os.environ)
    e.update(env or {})
    p = subprocess.run([MBG, *args], capture_output=True, text=True, timeout=120,
                       env=e, cwd=ROOT)
    lines = [l for l in p.stdout.splitlines() if l.strip()]
    return p.returncode, lines, p


class CliContract(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = {"MBG_OUT": self.tmp.name}

    def tearDown(self):
        self.tmp.cleanup()

    def envelope(self, *args):
        code, lines, p = run(*args, env=self.env)
        self.assertEqual(len(lines), 1, f"stdout must be one JSON line: {p.stdout!r}")
        env = json.loads(lines[0])
        self.assertEqual(env["schema"], "mbg.result/1")
        for k in ("tool", "ok", "status", "summary", "metrics", "artifacts", "issues", "next"):
            self.assertIn(k, env)
        self.assertIn(env["status"], ("PASS", "FAIL", "PARTIAL", "NOT RUN", "NOT AVAILABLE"))
        return code, env

    def test_tools_lists_the_whole_registry(self):
        code, env = self.envelope("tools")
        self.assertEqual(code, 0)
        ids = {t["id"] for t in env["data"]["tools"]}
        self.assertEqual(ids, {t.id for t in registry.TOOLS})

    def test_one_tool_schema(self):
        code, env = self.envelope("tools", "layout.generate")
        self.assertEqual(code, 0)
        self.assertIn("hints", env["data"]["tool"]["input_schema"]["properties"])

    def test_unknown_command_is_a_usage_error(self):
        code, env = self.envelope("frobnicate")
        self.assertEqual(code, 2)
        self.assertFalse(env["ok"])
        self.assertEqual(env["error"]["code"], "USAGE")

    def test_missing_required_argument(self):
        code, env = self.envelope("spec", "check", "--metrics", "{}")
        self.assertEqual(code, 2)
        self.assertIn("spec", env["error"]["message"])

    def test_netlist_check_pass_and_fail(self):
        code, env = self.envelope("netlist", "check", OTA)
        self.assertEqual(code, 0)
        self.assertEqual(env["status"], "PASS")
        self.assertEqual(env["metrics"]["mos"], 5)
        bad = os.path.join(self.tmp.name, "bad.spice")
        with open(bad, "w") as f:
            f.write(".subckt b VDD VSS A\nXM1 A A VSS VSS nfet_03v3 W=2 L=0.5u\n.ends\n")
        code, env = self.envelope("netlist.check", bad)        # dotted form works too
        self.assertEqual(code, 1)
        self.assertEqual(env["status"], "FAIL")
        self.assertIn("UNIT_MISSING", {i["code"] for i in env["issues"]})

    def test_pdk_info_and_list(self):
        code, env = self.envelope("pdk", "list")
        self.assertEqual(code, 0)
        self.assertIn("sky130A", {p["name"] for p in env["data"]["pdks"]})
        code, env = self.envelope("pdk", "info", "--model", "pnp_10p00x10p00")
        self.assertEqual(env["data"]["device"]["terminals"], ["c", "b", "e"])

    def test_spec_check_with_shorthand(self):
        code, env = self.envelope("spec", "check", "--metrics", '{"tc_ppm_c": 120}',
                                  "--spec", '{"tc_ppm_c": "<= 300"}')
        self.assertEqual((code, env["status"]), (0, "PASS"))
        code, env = self.envelope("spec", "check", "--metrics", '{"tc_ppm_c": 420}',
                                  "--spec", "vref_md")
        self.assertEqual((code, env["status"]), (1, "FAIL"))

    def test_design_workspace(self):
        code, env = self.envelope("design", "init", "cli-test", "--netlist", OTA,
                                  "--prompt", "a 5T OTA")
        self.assertEqual((code, env["status"]), (0, "PASS"))
        ws = os.path.join(self.tmp.name, "cli-test")
        exp = json.load(open(os.path.join(ws, "experiment.json")))
        self.assertEqual(exp["experiment_id"], "cli-test")
        self.assertEqual(exp["pdk"], "gf180mcuD")
        code, env = self.envelope("design", "init", "cli-test")
        self.assertEqual(env["status"], "FAIL")              # never overwritten
        code, env = self.envelope("design", "init", "Bad_Name")
        self.assertEqual(code, 2)
        code, env = self.envelope("netlist", "check", "--design", "cli-test")
        self.assertEqual(env["status"], "PASS")
        self.assertTrue(os.path.isdir(os.path.join(ws, "netlist_check")))

    def test_help_is_text(self):
        p = subprocess.run([MBG, "layout", "generate", "--help"], capture_output=True,
                           text=True, cwd=ROOT)
        self.assertEqual(p.returncode, 0)
        self.assertIn("--hints", p.stdout)


class Internals(unittest.TestCase):

    def test_spice_numbers(self):
        self.assertAlmostEqual(parse_number("20u"), 20e-6)
        self.assertAlmostEqual(parse_number("1meg"), 1e6)
        self.assertAlmostEqual(parse_number("3.3"), 3.3)
        self.assertAlmostEqual(parse_number("1p"), 1e-12)
        with self.assertRaises(ValueError):
            parse_number("abc")

    def test_mcp_names_are_legal_and_unique(self):
        names = [t["name"] for t in registry.mcp_tools()]
        self.assertEqual(len(names), len(set(names)))
        for n in names:
            self.assertRegex(n, r"^[a-zA-Z0-9_-]{1,64}$")

    def test_import_without_the_layout_stack(self):
        code = ("import sys; sys.modules['glayout'] = None; sys.modules['gdsfactory'] = None\n"
                "import mbg; from mbg import Spec; from mbg.agent.cli import main\n"
                "from mbg.netlist_check import check_netlist; from mbg import pdk_profile\n"
                "print('ok')")
        p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                           env={**os.environ, "PYTHONPATH": os.path.join(ROOT, "src")})
        self.assertEqual(p.stdout.strip(), "ok", p.stderr)

    def test_background_job_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = os.environ.get("MBG_OUT")
            os.environ["MBG_OUT"] = tmp
            try:
                rd = runio.new_run_dir("netlist.check")
                job = runio.start_job("netlist.check", {"netlist": OTA}, rd, 60)
                self.assertEqual(job["state"], "running")
                state, res = runio.wait_job(rd, 60)
                self.assertEqual(state["state"], "done", runio.log_tail(rd / "log.txt"))
                self.assertEqual(res["status"], "PASS")
                self.assertEqual(runio.find_job(job["id"]), rd)
            finally:
                if old is None:
                    os.environ.pop("MBG_OUT", None)
                else:
                    os.environ["MBG_OUT"] = old


if __name__ == "__main__":
    unittest.main(verbosity=2)
