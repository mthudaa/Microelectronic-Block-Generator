"""Offline distribution manifests preserve the public command surfaces."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_verification_helpers_are_in_package_and_match_sources():
    from mbg.checks import _find_eda_scripts
    packaged = ROOT / 'src/mbg/eda'
    assert Path(_find_eda_scripts()) == packaged
    for name in ('iic-drc.sh', 'iic-lvs.sh', 'iic-pex.sh'):
        assert (packaged / name).read_bytes() == (ROOT / 'scripts/eda' / name).read_bytes()


def test_sdist_manifest_carries_launcher_and_client_configs():
    text = (ROOT / 'MANIFEST.in').read_text()
    assert 'scripts/mbg' in text and '.mcp.json' in text and 'opencode.jsonc' in text
    for folder in ('.codex', '.cursor', '.gemini'):
        assert f'recursive-include {folder}' in text
