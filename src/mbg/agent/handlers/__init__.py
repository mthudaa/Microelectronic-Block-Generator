"""Shared input handling and local workspace stage records."""
from __future__ import annotations
import json
import os
from pathlib import Path
import re
from mbg.agent import runio
from mbg.output_paths import checked_path, input_path


def load_obj(value, what):
    if value is None:
        return None
    if isinstance(value, (dict, list, tuple)):
        return value
    if isinstance(value, str) and value.lstrip().startswith(('{', '[')):
        return json.loads(value)
    return json.loads(input_path(value).read_text())


def workspace_netlist(design):
    if not design:
        return None
    root = runio.out_root()
    path = checked_path(root, root / runio.safe_name(design) / 'generated_netlist.spice')
    return path if path.is_file() else None


def read_netlist(args):
    path = input_path(args['netlist']) if args.get('netlist') else workspace_netlist(args.get('design'))
    if path is None:
        raise ValueError('Supply a netlist or a design workspace')
    return path.read_text(), path


def subckt_name(text):
    match = re.search(r'^\s*\.subckt\s+(\S+)', text, re.I | re.M)
    if not match:
        raise ValueError('No .subckt definition')
    return match.group(1)


def subckt_ports(text):
    match = re.search(r'^\s*\.subckt\s+\S+\s+(.*)$', text, re.I | re.M)
    return match.group(1).split() if match else []


def profile_for(args, text=None):
    from mbg import pdk_profile
    return pdk_profile.for_netlist(text, args.get('pdk')) if text else pdk_profile.resolve(args.get('pdk'))


def ensure_pdk(profile, result):
    if profile.installed():
        return True
    result.set('NOT AVAILABLE', f'PDK {profile.name} is not installed')
    result.issue('PDK_MISSING', 'Install the selected PDK', hint='./install.sh --stage pdk')
    return False


def env_note():
    return {key: os.environ.get(key, '') for key in ('PDK_ROOT', 'PDK', 'PDKPATH')}


def record(design, *, stage=None, status=None, artifact=None, netlist_valid=None, gds=None):
    if not design:
        return
    root = runio.out_root()
    ws = checked_path(root, root / runio.safe_name(design))
    path = checked_path(ws, ws / 'experiment.json')
    if not path.is_file():
        raise FileNotFoundError(f'Workspace record missing: {path}')
    data = json.loads(path.read_text())
    if netlist_valid is not None:
        data.setdefault('stages', {})['netlist_check'] = {'status': 'PASS' if netlist_valid else 'FAIL'}
    if stage:
        entry = {'status': status or 'NOT RUN'}
        if artifact:
            entry['artifact'] = str(Path(artifact).resolve())
        data.setdefault('stages', {})[stage] = entry
    if gds:
        data.setdefault('artifacts', {})['gds'] = str(Path(gds).resolve())
    path.write_text(json.dumps(data, indent=2) + '\n')
