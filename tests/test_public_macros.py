"""Synthetic ordinary macro geometry and public feature boundaries; no EDA."""
from pathlib import Path

import pytest


def test_macro_defaults_disabled_and_rejects_excluded_options():
    from mbg.macro import MacroConfig
    assert not MacroConfig.from_dict().enabled
    for value in ({"guardring": "dnwell"}, {"guardring": "auto"}, {"groups": []},
                  {"enabled": True, "unknown": True}):
        with pytest.raises(ValueError):
            MacroConfig.from_dict(value)


def test_placement_rejects_isolation_matching_and_dummy_controls():
    from mbg.placement_engine import PlacementConfig
    for value in ({"with_dnwell": True}, {"dnwell_devices": ["M1"]},
                  {"with_dummy": True}, {"hints": {"groups": []}},
                  {"hints": {"array": []}}):
        with pytest.raises(ValueError):
            PlacementConfig(**value)


def fixture():
    import gdsfactory as gf
    from glayout import gf180
    from mbg.design_context import DesignContext, BoundingBox, Net
    from mbg.pdk_rules import get_rules
    from mbg.router import RouterConfig
    gf180.activate()
    ctx = DesignContext(name="ordinary_synthetic")
    ctx.pdk, ctx.rules = gf180, get_rules(gf180)
    ctx.top_ports = ["vdd", "vss", "out"]
    ctx.nets = {n: Net(n, is_power=n == "vdd", is_ground=n == "vss") for n in ctx.top_ports}
    ctx.power_nets, ctx.ground_nets = {"vdd"}, {"vss"}
    top = gf.Component()
    top.add_polygon([(0, 0), (10, 0), (10, 12), (0, 12)], layer=(0, 0))
    ctx.component = top
    ctx.device_bboxes["synthetic_core"] = BoundingBox(0, 0, 10, 12)
    return ctx, top, gf180, RouterConfig(verbosity=0)


def test_ordinary_macro_contacts_pins_and_obstacles_are_real_and_routable():
    from mbg.macro import MacroConfig, prepare_macro
    from mbg.router import GridRouter, realize
    from mbg.connectivity import verify
    ctx, top, pdk, rcfg = fixture()
    original = {name: list(net.terminals) for name, net in ctx.nets.items()}
    proof = prepare_macro(ctx, top, pdk, MacroConfig(enabled=True), rcfg)
    assert proof["guardrings"]["mode"] == "ordinary"
    assert [r["net"] for r in proof["guardrings"]["rings"]] == ["vss", "vdd"]
    assert not top.get_polygons(by_spec=True).get(pdk.get_glayer("dnwell"))
    for name in ctx.top_ports:
        assert ctx.net_to_access[name]
        assert any(o.net == name for o in ctx.obstacles)
    assert all(list(ctx.nets[n].terminals) != original[n] for n in ("vdd", "vss"))
    routed = GridRouter(ctx, rcfg).run()
    assert not routed["failed"]
    realize(ctx, top, rcfg)
    assert verify(ctx)["clean"]


def test_macro_lef_uses_exact_contract_pins_without_magic(tmp_path):
    from mbg.macro import MacroConfig, prepare_macro
    from mbg.outputs import write_macro_lef
    ctx, top, pdk, rcfg = fixture()
    interface = prepare_macro(ctx, top, pdk, MacroConfig(enabled=True), rcfg)
    path = write_macro_lef({"cell_name": ctx.name, "context": ctx,
                            "macro_interface": interface}, str(tmp_path))
    text = Path(path).read_text()
    for pin in interface["pins"]:
        assert "PIN " + pin["name"] in text
        assert "LAYER Metal" + pin["layer"][3:] in text
    assert "LAYER met" not in text  # GF180 technology LEF uses Metal1..Metal5.
    assert "SIZE 0 " not in text
    assert "END " + ctx.name in text


def test_macro_fixed_pin_cannot_escape_bounds_or_overlap_other_net():
    from mbg.macro import MacroConfig, prepare_macro
    ctx, top, pdk, rcfg = fixture()
    with pytest.raises(ValueError):
        prepare_macro(ctx, top, pdk, MacroConfig.from_dict({"enabled": True,
            "pins": {"out": {"rect": [-1, -1, 1, 1]}}}), rcfg)
