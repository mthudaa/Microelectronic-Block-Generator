#!/usr/bin/env python3
"""Regression tests for the default multi-module GDS integration script."""

import importlib.util
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "integrate_modules.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("integrate_modules", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class DefaultIntegrationInputs(unittest.TestCase):
    def test_default_module_configs_resolve_to_existing_gds(self):
        module = _load_script()

        for module_spec in module.MODULE_SPECS:
            config_path = ROOT / module_spec.config
            with self.subTest(module=module_spec.name):
                self.assertTrue(config_path.is_file(), f"missing {config_path}")
                gds_path, _ = module.resolve_gds(config_path, ROOT)
                self.assertTrue(gds_path.is_file(), f"missing {gds_path}")

    def test_top_layout_variable_expands_to_top_source(self):
        module = _load_script()

        self.assertEqual(
            module._resolve_top_layout(
                {"TOP_LAYOUT": "$TOP_SOURCE", "TOP_SOURCE": "ota_5t"}
            ),
            "ota_5t",
        )


if __name__ == "__main__":
    unittest.main()
