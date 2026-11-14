#!/usr/bin/env bash
# Source this helper; it never installs packages.
_mbg_setup_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
_mbg_setup_venv="${MBG_VENV:-$_mbg_setup_root/.venv}"
if [ ! -f "$_mbg_setup_venv/bin/activate" ]; then
    printf 'Create the environment with ./install.sh --stage python\n' >&2
    return 1 2>/dev/null || exit 1
fi
source "$_mbg_setup_venv/bin/activate"
export MBG_ROOT="$_mbg_setup_root"
export PYTHONPATH="$_mbg_setup_root/src${PYTHONPATH:+:$PYTHONPATH}"
unset _mbg_setup_root _mbg_setup_venv
