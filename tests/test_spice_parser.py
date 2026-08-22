"""SPICE front-end tests: the netlist must survive parsing intact.

Everything here is a failure mode that produced a WRONG CIRCUIT rather than an
error message. That is the dangerous kind: layout, DRC and LVS all run happily
on a circuit nobody asked for, and LVS compares the corrupted netlist against
itself, so it matches.

  A  line continuation (`+`)   -> the wrapped remainder became a phantom
                                  device named "+", and the real device lost
                                  its model and its W/L
  B  inline comments ($ and ;) -> parameter text inside a comment could be
                                  picked up in place of the real value
  C  PDK detection             -> keyed only off a .lib path, so a netlist
                                  that names nfet_03v3 still failed with
                                  "Unknown PDK"
  D  device validation         -> a transistor with no W/L, no model, or a
                                  truncated node list passed straight through
  E  scale                     -> many devices with adjacent-prefix names
                                  (XM1 / XM10 / XM100) must not collide
"""

import os
import sys
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "tests"))

os.environ.setdefault("PDK_ROOT", os.path.expanduser("~/.volare"))
os.environ.setdefault("PDK", "gf180mcuD")
os.environ.setdefault("PDKPATH", os.path.join(os.environ["PDK_ROOT"],
                                              os.environ["PDK"]))

import fixtures                                                # noqa: E402
from mbg.spice_parser import (                                 # noqa: E402
    build_design_context, parse_netlist_with_pdk,
)


def devices(cfg):
    return [c for c in cfg["components"] if c["type"] == "device"]


def by_name(cfg):
    return {c["name"]: c for c in devices(cfg)}


class TestA_LineContinuation(unittest.TestCase):
    """A wrapped instance line is one device, not two."""

    NETLIST = """.subckt t vdd vss a b
XM1 a b vdd vdd
+ pfet_03v3 W=2u L=1u
XM2 b a vss
+ vss nfet_03v3 W=1u
+ L=0.5u
.ends
"""

    def test_no_phantom_device_is_created(self):
        names = sorted(d["name"] for d in devices(parse_netlist_with_pdk(self.NETLIST)))
        self.assertEqual(names, ["XM1", "XM2"],
                         "a continuation line was read as its own device")

    def test_the_wrapped_data_reaches_the_device(self):
        d = by_name(parse_netlist_with_pdk(self.NETLIST))
        self.assertEqual(d["XM1"]["model"], "pfet_03v3")
        self.assertEqual(d["XM1"]["parameters"]["w"], "2u")
        self.assertEqual(d["XM1"]["parameters"]["l"], "1u")

    def test_continuation_across_several_lines(self):
        d = by_name(parse_netlist_with_pdk(self.NETLIST))["XM2"]
        self.assertEqual(d["model"], "nfet_03v3")
        self.assertEqual(d["nodes"]["body"], "vss")
        self.assertEqual(d["parameters"]["w"], "1u")
        self.assertEqual(d["parameters"]["l"], "0.5u")


class TestB_InlineComments(unittest.TestCase):
    """Text after $ or ; is a comment and must not be parsed as data."""

    # Parameters are found by regex over the rest of the instance line, and
    # the regex takes the FIRST match. So a comment placed AFTER the real
    # values is harmless whether or not comments are stripped -- only a
    # comment placed BEFORE them distinguishes the two behaviours, and that is
    # what these use. Nothing after the marker may reach the parser: the
    # correct reading of such a line is that the device has no W/L at all,
    # which the device validation then reports by name.

    def test_dollar_comment_text_is_never_parsed_as_a_parameter(self):
        cfg = parse_netlist_with_pdk(
            ".subckt t vdd vss a\n"
            "XM1 a a vdd vdd pfet_03v3 $ stale note L=99u W=99u\n"
            ".ends\n")
        p = by_name(cfg)["XM1"]["parameters"]
        self.assertNotEqual(p["l"], "99u", "a value inside a $ comment was used")
        self.assertNotEqual(p["w"], "99u", "a value inside a $ comment was used")

    def test_semicolon_comment_text_is_never_parsed_as_a_parameter(self):
        cfg = parse_netlist_with_pdk(
            ".subckt t vdd vss a\n"
            "XM1 a a vss vss nfet_03v3 ; stale note W=77u L=77u\n"
            ".ends\n")
        p = by_name(cfg)["XM1"]["parameters"]
        self.assertNotEqual(p["w"], "77u", "a value inside a ; comment was used")
        self.assertNotEqual(p["l"], "77u", "a value inside a ; comment was used")

    def test_a_comment_after_the_values_leaves_them_alone(self):
        cfg = parse_netlist_with_pdk(
            ".subckt t vdd vss a\n"
            "XM1 a a vdd vdd pfet_03v3 W=2u L=1u $ was L=99u\n"
            ".ends\n")
        p = by_name(cfg)["XM1"]["parameters"]
        self.assertEqual((p["w"], p["l"]), ("2u", "1u"))

    def test_a_comment_line_never_swallows_a_continuation(self):
        cfg = parse_netlist_with_pdk(
            ".subckt t vdd vss a\n"
            "* a comment between the line and its continuation\n"
            "XM1 a a vdd vdd\n"
            "* another one\n"
            "+ pfet_03v3 W=2u L=1u\n"
            ".ends\n")
        self.assertEqual(by_name(cfg)["XM1"]["model"], "pfet_03v3")


class TestC_PDKDetection(unittest.TestCase):
    def test_models_identify_the_pdk_without_a_lib_line(self):
        cfg = parse_netlist_with_pdk(
            ".subckt t vdd vss a\n"
            "XM1 a a vdd vdd pfet_03v3 W=1u L=1u\n.ends\n")
        self.assertEqual(cfg["metadata"]["pdk"], "gf180")

    def test_sky130_models_are_recognised_too(self):
        cfg = parse_netlist_with_pdk(
            ".subckt t vd vs a\n"
            "XM1 a a vd vd sky130_fd_pr__pfet_01v8 W=1u L=1u\n.ends\n")
        self.assertEqual(cfg["metadata"]["pdk"], "sky130")

    def test_an_explicit_lib_line_still_wins(self):
        # inference must never override what the netlist states outright
        cfg = parse_netlist_with_pdk(
            '.lib "/x/sky130.lib" tt\n.subckt t vd vs a\n'
            "XM1 a a vd vd pfet_03v3 W=1u L=1u\n.ends\n")
        self.assertEqual(cfg["metadata"]["pdk"], "sky130")


class TestD_DeviceValidation(unittest.TestCase):
    """A netlist the layout stage cannot build must fail HERE, by name."""

    def _expect_error(self, netlist, *fragments):
        from glayout import gf180
        with self.assertRaises(ValueError) as cm:
            build_design_context(parse_netlist_with_pdk(netlist), gf180)
        msg = str(cm.exception)
        for f in fragments:
            self.assertIn(f, msg, f"error message does not mention {f!r}: {msg}")

    def test_transistor_with_no_width(self):
        self._expect_error(".subckt t vdd vss a\n"
                           "XM1 a a vdd vdd pfet_03v3 L=1u\n.ends\n",
                           "XM1", "W")

    def test_transistor_with_an_unexpanded_param(self):
        self._expect_error(".subckt t vdd vss a\n"
                           "XM1 a a vdd vdd pfet_03v3 W={WP} L=1u\n.ends\n",
                           "XM1", "{WP}")

    def test_truncated_instance_line(self):
        self._expect_error(".subckt t vdd vss a\nXM1 a a vdd\n.ends\n", "XM1")

    def test_unrecognised_transistor_model(self):
        self._expect_error(".subckt t vdd vss a\n"
                           "XM1 a a vdd vdd notatransistor W=1u L=1u\n.ends\n",
                           "XM1", "notatransistor")


class TestE_Scale(unittest.TestCase):
    """Many devices, adjacent name prefixes, and no quadratic blow-up."""

    @staticmethod
    def _synth(n):
        lines = [".subckt big vdd vss inp"]
        for i in range(1, n + 1):
            lines.append(f"XM{i} n{i} n{i-1 if i > 1 else 'inp'} "
                         f"{'vdd vdd pfet_03v3' if i % 2 else 'vss vss nfet_03v3'} "
                         f"W=1u L=1u")
        lines.append(".ends")
        return "\n".join(lines) + "\n"

    def test_device_identity_survives_adjacent_prefixes(self):
        cfg = parse_netlist_with_pdk(self._synth(200))
        names = [d["name"] for d in devices(cfg)]
        self.assertEqual(len(names), 200)
        self.assertEqual(len(set(names)), 200, "device names collided")
        for probe in ("XM1", "XM10", "XM100", "XM200"):
            self.assertIn(probe, names)

    def test_parse_time_stays_close_to_linear(self):
        def t(n):
            netlist = self._synth(n)
            t0 = time.perf_counter()
            parse_netlist_with_pdk(netlist)
            return time.perf_counter() - t0

        t(50)                                  # warm up imports/regex caches
        small, large = t(100), t(400)
        # 4x the devices must not cost more than 16x the time; a genuinely
        # quadratic parser costs 16x, an exponential one far more. This is a
        # loose bound on purpose — it is here to catch a blow-up, not to
        # police normal variation on a loaded machine.
        self.assertLess(large, max(small * 16.0, 0.5),
                        f"parse time scaled badly: 100 devices {small:.3f}s, "
                        f"400 devices {large:.3f}s")


class TestF_ReferenceNetlistsUnchanged(unittest.TestCase):
    """Every shipped fixture still parses to the same circuit."""

    EXPECTED = {
        "cmp_2stage_clk": (12, 11), "inverter": (2, 4), "ota_5t": (5, 8),
        "ota_bb": (5, 9), "rc_filter": (2, 3), "ring_osc_3": (6, 5),
        "strongarm": (11, 10), "vref_1v2": (7, 6),
    }

    def test_device_and_net_counts(self):
        from glayout import gf180
        self.assertEqual(sorted(self.EXPECTED), fixtures.names(),
                         "a netlist fixture was added or removed without "
                         "updating this test")
        for name, (n_dev, n_net) in self.EXPECTED.items():
            with self.subTest(design=name):
                ctx = build_design_context(
                    parse_netlist_with_pdk(fixtures.load(name)), gf180)
                self.assertEqual(len(ctx.devices), n_dev)
                self.assertEqual(len(ctx.nets), n_net)


if __name__ == "__main__":
    unittest.main(verbosity=2)
