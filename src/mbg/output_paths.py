"""Local output roots and path checks for public MBG workspaces."""
from datetime import datetime, timezone
import os
from pathlib import Path
import re
from uuid import uuid4


def output_root():
    return Path(os.environ.get('MBG_OUT') or Path.home() / 'mbg').expanduser().resolve()


def checked_path(root, path):
    root = Path(root).expanduser().resolve()
    path = Path(path).expanduser()
    if '..' in path.parts:
        raise ValueError('Parent-directory traversal is not allowed')
    resolved = path.resolve()
    if not resolved.is_relative_to(root):
        raise ValueError('Path escapes its authorized directory')
    _not_secret(path)
    _not_secret(resolved)
    return resolved


def _not_secret(path):
    if any(p.lower().startswith('.env') or p == '.git' or
           p.lower().endswith(('.key', '.pem')) for p in Path(path).parts):
        raise ValueError('Secret and Git metadata paths are not inputs')


def input_path(value):
    path = Path(value).expanduser()
    _not_secret(path)
    if '..' in path.parts:
        raise ValueError('Parent-directory traversal is not allowed')
    resolved = path.resolve()
    _not_secret(resolved)
    if not resolved.is_file():
        raise FileNotFoundError(str(path))
    return resolved


def new_run_directory(category, name=None):
    for part in (category, name):
        if part is not None and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', part):
            raise ValueError('Output names must be single safe path components')
    label = category + ('-' + name if name else '')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')
    root = output_root()
    path = checked_path(root, root / category / (stamp + '-' + label + '-' + uuid4().hex[:10]))
    path.mkdir(parents=True)
    return path
