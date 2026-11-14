"""Public pipeline acceptance and callback ordering without EDA tools."""
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize("magic,lvs,internal,pex,expected", [
    (True, True, True, True, True), (False, True, True, True, False),
    (True, False, True, True, False), (True, True, False, True, False),
    (True, True, True, False, False),
])
def test_public_acceptance_requires_every_published_gate(tmp_path, monkeypatch, magic, lvs, internal, pex, expected):
    from mbg import pipeline
    text = ".subckt public_synthetic vdd vss a y\nXM1 y a vss vss nfet_03v3 W=1u L=1u\n.ends\n"
    monkeypatch.setattr(pipeline, "spice_to_gds_ctx", lambda *a, **kw: {
        "component": object(), "verification": {"clean": internal}, "metrics": {},
        "context": SimpleNamespace(top_ports=["vdd", "vss", "a", "y"])})
    monkeypatch.setattr(pipeline, "write_gds_foundry", lambda c, p: __import__('pathlib').Path(p).write_bytes(b"synthetic"))
    monkeypatch.setattr(pipeline, "run_drc", lambda *a, **kw: {"clean": magic})
    monkeypatch.setattr(pipeline, "run_lvs", lambda *a, **kw: {"match": lvs})
    extracted = tmp_path / "public_synthetic.pex.spice"
    if pex:
        extracted.write_text(text)
    monkeypatch.setattr(pipeline, "run_pex", lambda *a, **kw: {"pex_path": str(extracted) if pex else None})
    result = pipeline._with_checks_ctx(text, SimpleNamespace(name="gf180mcuD"),
        gds_path=None, mode="analog", add_labels=True, verbosity=0,
        placement_config=None, router_config=None, power_rails=True,
        rail_layer="met5", write_views=False, outdir=str(tmp_path), macro_config=None)
    assert result["all_pass"] == expected
    assert result["verification_scope"] == "Magic DRC, netgen LVS, internal connectivity and PEX extraction"
    assert "drc_signoff" not in result


@pytest.mark.parametrize("trial", [False, True])
def test_before_route_callback_runs_before_trial_router(monkeypatch, trial):
    from mbg import placement_engine, router
    calls = []
    ctx = SimpleNamespace(clear_routing=lambda: calls.append("clear"),
                          routing_congestion=None, failures=[])
    cfg = placement_engine.PlacementConfig(trial_route=trial, verbosity=0)
    top = object()
    monkeypatch.setattr(placement_engine, "place", lambda *a: calls.append("place") or top)
    class TrialRouter:
        def __init__(self, *args):
            assert calls == ["place", "contacts"]
            calls.append("trial")
        def run(self):
            return {"failed": [], "routed": []}
    ctx.routed_nets = {}
    monkeypatch.setattr(router, "GridRouter", TrialRouter)
    result, _ = placement_engine.place_with_routability(ctx, object(), cfg,
        before_route=lambda c, t: calls.append("contacts"))
    assert result is top and calls == ["place", "contacts"] + (["trial"] if trial else [])


@pytest.mark.parametrize("macro", [None, {"enabled": True}])
def test_synthetic_inverter_uses_conventional_placement_and_connected_interface(macro):
    from mbg.pipeline import spice_to_gds_ctx
    source = ".subckt public_synthetic_inv vdd vss a y\n" \
             "XM1 y a vss vss nfet_03v3 W=2u L=0.5u\n" \
             "XM2 y a vdd vdd pfet_03v3 W=2u L=0.5u\n.ends\n"
    result = spice_to_gds_ctx(source, verbosity=0, macro_config=macro)
    assert result["verification"]["clean"], result["verification"]
    assert not result["context"].matching_groups
    assert not result["context"].symmetry_constraints
    if macro:
        assert len(result["macro_interface"]["pins"]) == 4
        assert result["macro_interface"]["bounds"][:2] == [0.0, 0.0]
        assert result["context"].macro_bbox.xmin == result["context"].macro_bbox.ymin == 0
