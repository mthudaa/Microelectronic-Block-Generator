"""The distributable tree contains only this public edition's modules."""
import ast
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
ALLOWED = {
    '__init__', '__main__', 'config', 'analysis', 'simulation', 'spice_parser',
    'netlist_check', 'pdk_profile', 'pdk_devices', 'pdk_rules', 'passives',
    'design_context', 'placement_engine', 'router', 'power', 'connectivity',
    'checks', 'pipeline', 'outputs', 'layout_view', 'specs', 'measure', 'utils',
    'cli', 'converters', 'output_paths', 'macro', 'macro_access',
    'macro_transform', 'macro_guardring', 'geometry',
}


def test_package_module_allowlist():
    names = {p.stem for p in (ROOT / 'src/mbg').glob('*.py')}
    assert names <= ALLOWED


def test_internal_imports_resolve_inside_release():
    package = ROOT / 'src/mbg'
    for path in package.rglob('*.py'):
        for node in ast.walk(ast.parse(path.read_text())):
            modules = [node.module] if isinstance(node, ast.ImportFrom) and node.module else []
            if isinstance(node, ast.Import):
                modules += [a.name for a in node.names]
            for module in modules:
                if not module.startswith('mbg.'):
                    continue
                relative = module.split('.')[1:]
                destination = package.joinpath(*relative)
                assert destination.with_suffix('.py').is_file() or (destination / '__init__.py').is_file(), (path, module)


def test_registered_handlers_are_available():
    from mbg.agent.registry import TOOLS, load_handler
    for tool in TOOLS:
        assert callable(load_handler(tool))


def test_every_lazy_export_resolves():
    import mbg
    assert Path(mbg.__file__).resolve().is_relative_to(ROOT)
    for name in mbg.__all__:
        assert getattr(mbg, name) is not None, name


def test_local_output_default_and_workspace_record(tmp_path, monkeypatch):
    from mbg.output_paths import output_root
    from mbg.agent.handlers import design, record
    from mbg.agent import runio
    import json
    monkeypatch.setenv('MBG_OUT', str(tmp_path / 'runs'))
    assert output_root() == tmp_path / 'runs'
    result = design.init({'name': 'public-test'}, None)
    assert result.status == 'PASS'
    record('public-test', stage='netlist_check', status='PASS')
    data = json.loads((runio.out_root() / 'public-test/experiment.json').read_text())
    assert data['stages']['netlist_check']['status'] == 'PASS'


def test_output_and_secret_path_rejection(tmp_path):
    from mbg.output_paths import checked_path, input_path
    root = tmp_path / 'inside'; root.mkdir()
    outside = tmp_path / 'outside'; outside.mkdir()
    (root / 'escape').symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError):
        checked_path(root, root / 'escape' / 'run')
    with pytest.raises(ValueError):
        input_path(root / '.env')


def test_converter_metrics_from_measurement_data():
    from mbg.converters import adc_metrics, dac_metrics
    codes = list(range(16))
    assert dac_metrics(codes, [c / 16 for c in codes], bits=4, vref=1)['status'] == 'PASS'
    assert adc_metrics([i / 256 for i in range(257)], [min(15, i // 16) for i in range(257)], bits=4, vref=1)['status'] == 'PASS'
    assert adc_metrics([(c + .5) / 16 for c in codes], codes, bits=4, vref=1)['status'] == 'PARTIAL'


def test_public_parser_keeps_plain_device_graph():
    from mbg.spice_parser import parse_netlist_with_pdk, build_design_context
    source = (ROOT / 'tests/netlists/ota_5t.spice').read_text()
    context = build_design_context(parse_netlist_with_pdk(source))
    assert len(context.devices) == 5
    assert not context.matching_groups
    assert not context.symmetry_constraints


def test_public_placer_rejects_unavailable_options():
    from mbg.placement_engine import PlacementConfig
    with pytest.raises(ValueError):
        PlacementConfig(with_dnwell=True)
