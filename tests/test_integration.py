#!/usr/bin/env python3
"""Chip-level integration: module discovery and LibreLane deliverables.

Uses synthetic module manifests so it runs in milliseconds — the layout flow is
already covered by tests/test_outputs.py. What matters here is that discovery,
the top-level Verilog, the LibreLane config and the Chipathon files are correct
and consistent with each other.

Run:  python tests/test_integration.py
"""

import json
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

from mbg.integrate import (  # noqa: E402
    discover_modules, integrate, write_librelane_config, write_top_verilog,
)

MODULES = {
    "ota_5t": ["vdd", "vss", "inp", "inm", "out", "vb"],
    "inverter": ["vdd", "vss", "a", "y"],
}


def _fake_module(root, cell, ports, *, with_lef=True):
    d = os.path.join(root, cell)
    os.makedirs(d, exist_ok=True)
    files = {}
    for view, ext in (("gds", ".gds"), ("lib", ".lib"), ("verilog", ".v"),
                      ("sch_spice", ".spice"), ("pex_spice", ".pex.spice")):
        fn = f"{cell}{ext}"
        open(os.path.join(d, fn), "w").write(f"* {view} for {cell}\n")
        files[view] = fn
    if with_lef:
        fn = f"{cell}.lef"
        open(os.path.join(d, fn), "w").write(
            f"MACRO {cell}\n  SIZE 20.000 BY 30.000 ;\n"
            + "".join(f"  PIN {p}\n  END {p}\n" for p in ports)
            + f"END {cell}\n")
        files["lef"] = fn
    else:
        files["lef"] = None
    json.dump({"cell": cell, "files": files,
               "ports": [{"name": p,
                          "direction": "power" if p == "vdd" else
                                       "ground" if p == "vss" else "inout"}
                         for p in ports]},
              open(os.path.join(d, f"{cell}.views.json"), "w"), indent=2)
    return d


class Discovery(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mbg_integ_")
        for cell, ports in MODULES.items():
            _fake_module(self.tmp, cell, ports)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_finds_every_module(self):
        mods = discover_modules([self.tmp])
        self.assertEqual([m.cell for m in mods], sorted(MODULES))
        for m in mods:
            self.assertEqual(m.missing(["gds", "lef", "lib", "verilog"]), [])

    def test_reports_a_module_missing_its_lef(self):
        _fake_module(self.tmp, "no_lef", ["vdd", "vss", "z"], with_lef=False)
        mods = {m.cell: m for m in discover_modules([self.tmp])}
        self.assertIn("lef", mods["no_lef"].missing(["lef"]))


class Deliverables(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mbg_integ_")
        for cell, ports in MODULES.items():
            _fake_module(self.tmp, cell, ports)
        self.out = os.path.join(self.tmp, "integration")
        self.res = integrate("chip_top", [self.tmp], self.out,
                             title="t", team="team", repo_root=self.tmp,
                             run=False, verbosity=0)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_every_deliverable_written(self):
        for key in ("top_verilog", "config", "info_yaml", "macros"):
            self.assertTrue(os.path.isfile(self.res[key]), f"{key} missing")
        self.assertEqual(len(self.res["lvs_configs"]), len(MODULES))

    def test_supplies_shared_signals_namespaced(self):
        v = open(self.res["top_verilog"]).read()
        # one shared supply pair at the top
        self.assertIn("inout  vdd;", v)
        self.assertIn("inout  vss;", v)
        # signals namespaced per block: two blocks with a pin named `y`/`out`
        # must not be silently tied together
        self.assertIn("ota_5t_out", v)
        self.assertIn("inverter_y", v)
        self.assertIn(".vdd(vdd)", v)

    def test_librelane_config_declares_macros(self):
        cfg = json.load(open(self.res["config"]))
        self.assertEqual(cfg["DESIGN_NAME"], "chip_top")
        self.assertEqual(sorted(cfg["MACROS"]), sorted(MODULES))
        for cell in MODULES:
            m = cfg["MACROS"][cell]
            self.assertTrue(m["lef"] and m["gds"])
            self.assertIn(f"u_{cell}", m["instances"])
        # die area must come from the LEF sizes, not a placeholder
        x0, y0, x1, y1 = cfg["DIE_AREA"]
        self.assertGreater(x1 - x0, 20.0)
        self.assertGreater(y1 - y0, 30.0)

    def test_info_yaml_lists_configs_and_pins(self):
        text = open(self.res["info_yaml"]).read()
        self.assertIn("project:", text)
        self.assertIn("lvs_config:", text)
        for cell in MODULES:
            self.assertIn(f'lvs_config_{cell}.json', text)
            self.assertIn(f'name: "{cell}"', text)

    def test_lvs_config_uses_portable_paths(self):
        for path in self.res["lvs_configs"]:
            cfg = json.load(open(path))
            self.assertTrue(cfg["LAYOUT_FILE"].startswith("$UPRJ_ROOT/"),
                            f"non-portable path: {cfg['LAYOUT_FILE']}")
            self.assertEqual(cfg["TOP_LAYOUT"], "$TOP_SOURCE")

    def test_librelane_absence_is_not_a_pass(self):
        # Generating a config is not running the flow. If LibreLane is not
        # installed the status must say NOT RUN, never PASS.
        st = self.res["librelane"]["status"]
        self.assertIn(st, ("NOT RUN", "PASS", "FAIL"))
        if shutil.which("librelane") is None and shutil.which("openlane") is None:
            self.assertNotEqual(st, "PASS")


def main():
    loader = unittest.TestLoader()
    suite = unittest.TestSuite([loader.loadTestsFromTestCase(c)
                                for c in (Discovery, Deliverables)])
    res = unittest.TextTestRunner(verbosity=2).run(suite)
    ok = res.testsRun - len(res.failures) - len(res.errors)
    print(f"\n=== {ok}/{res.testsRun} PASS ===")
    return 0 if res.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
