"""PDK profiles: loading, resolution, and agreement with the installed PDK.

The pure-data checks run anywhere. The ones that read model files are
skipped when the PDK is not installed.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from mbg import pdk_profile  # noqa: E402
from mbg.pdk_profile import ProfileError  # noqa: E402


class ProfileData(unittest.TestCase):

    def test_both_profiles_ship(self):
        self.assertIn("gf180mcuD", pdk_profile.available())
        self.assertIn("sky130A", pdk_profile.available())

    def test_gf180_is_the_default_and_matches_the_old_constants(self):
        # The values the flow hard-coded before profiles existed; the gf180
        # profile must reproduce them exactly or gf180 results change.
        p = pdk_profile.family_default("gf180")
        self.assertEqual(p.name, "gf180mcuD")
        self.assertTrue(p.data["default"])
        self.assertEqual(p.model_file_rel, "libs.tech/ngspice/sm141064.ngspice")
        self.assertEqual(p.design_file_rel, "libs.tech/ngspice/design.ngspice")
        self.assertEqual(p.supply_v, 3.3)
        self.assertEqual(p.std_cell_library, "gf180mcu_fd_sc_mcu7t5v0")
        self.assertEqual(p.lvs_permute_models, ["pfet_03v3", "nfet_03v3"])
        self.assertEqual(p.drc_engines, ["magic", "klayout"])
        self.assertEqual(p.drc_primary, "klayout")
        self.assertEqual(p.klayout_variant, "D")
        self.assertEqual(p.default_corner, "typical")

    def test_resolution_rules(self):
        self.assertEqual(pdk_profile.load("SKY130A").name, "sky130A")
        self.assertEqual(pdk_profile.load("gf180mcud").name, "gf180mcuD")
        self.assertEqual(pdk_profile.resolve("sky130").name, "sky130A")
        with self.assertRaises(ProfileError):
            pdk_profile.load("tsmc28")

    def test_family_follows_the_environment_variant(self):
        old = os.environ.get("PDK")
        os.environ["PDK"] = "sky130A"
        try:
            self.assertEqual(pdk_profile.resolve().name, "sky130A")
            self.assertEqual(pdk_profile.resolve("gf180").name, "gf180mcuD")
        finally:
            if old is None:
                os.environ.pop("PDK", None)
            else:
                os.environ["PDK"] = old

    def test_lib_sections(self):
        g = pdk_profile.load("gf180mcuD")
        self.assertEqual(g.lib_sections({"nmos", "pmos"}, "typical"), ["typical"])
        self.assertEqual(g.lib_sections({"nmos", "bjt", "res"}, "ss"),
                         ["ss", "bjt_ss", "res_ss"])
        # gf180 has no bjt_fs: falls back to typical
        self.assertEqual(g.lib_sections({"bjt"}, "fs"), ["fs", "bjt_typical"])
        self.assertEqual(g.lib_sections({"nmos"}, "tt"), ["typical"])
        s = pdk_profile.load("sky130A")
        self.assertEqual(s.lib_sections({"nmos", "res", "cap"}, "typical"), ["tt"])

    def test_device_catalogue(self):
        g = pdk_profile.load("gf180mcuD")
        pnp = g.device("PNP_10P00X10P00")
        self.assertEqual(pnp.kind, "bjt")
        self.assertEqual(pnp.terminals, ("c", "b", "e"))
        self.assertIn("c", pnp.substrate_terminals)
        self.assertIn("ppolyf_u_1k", g.models("res", layout_only=True))
        self.assertNotIn("nfet_06v0", g.models(layout_only=True))

    def test_netlist_family_must_match_the_request(self):
        text = (".subckt inv vdd vss a y\nXM1 y a vdd vdd pfet_03v3 W=1u L=0.5u\n"
                "XM2 y a vss vss nfet_03v3 W=1u L=0.5u\n.ends\n")
        self.assertEqual(pdk_profile.for_netlist(text).name, "gf180mcuD")
        with self.assertRaises(ProfileError):
            pdk_profile.for_netlist(text, "sky130A")

    def test_env_overrides_and_restores(self):
        s = pdk_profile.load("sky130A")
        before = os.environ.get("PDK")
        with s.env():
            self.assertEqual(os.environ["PDK"], "sky130A")
            self.assertTrue(os.environ["PDKPATH"].endswith("sky130A"))
        self.assertEqual(os.environ.get("PDK"), before)


@unittest.skipUnless(pdk_profile.load("gf180mcuD").installed(), "gf180mcuD not installed")
class Gf180AgainstInstalledPdk(unittest.TestCase):

    def test_every_section_exists_in_the_model_file(self):
        g = pdk_profile.load("gf180mcuD")
        have = set(pdk_profile.scan_lib_sections(g.model_file()))
        for kind in ("mos", "bjt", "res", "cap"):
            for c in g.corners:
                for sec in g.lib_sections({kind}, c):
                    self.assertIn(sec, have, f"{kind}@{c} -> {sec}")

    def test_every_device_model_is_defined(self):
        g = pdk_profile.load("gf180mcuD")
        ng = g.model_file().parent
        text = " ".join(f.read_text(errors="replace").lower().replace("\t", " ")
                        for f in ng.glob("*.ngspice"))
        for model in g.devices:
            self.assertTrue(f".subckt {model} " in text, f"{model} not defined in {ng}")


@unittest.skipUnless(pdk_profile.load("sky130A").installed(), "sky130A not installed")
class Sky130AgainstInstalledPdk(unittest.TestCase):

    def test_corner_sections_exist(self):
        s = pdk_profile.load("sky130A")
        have = set(pdk_profile.scan_lib_sections(s.model_file()))
        for c in s.corners:
            self.assertIn(c, have)


if __name__ == "__main__":
    unittest.main(verbosity=2)
