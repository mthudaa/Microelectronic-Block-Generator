#!/bin/bash
# Custom IC Design Environment Setup
# Source this file before using any skill: source pi-custom-mbg/common/env.sh
# For first-time setup: bash pi-custom-mbg/setup/install_all.sh

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export MBG_DIR="$REPO_DIR"
export PYTHONPATH="$MBG_DIR:$PYTHONPATH"

# ── Working Directory ────────────────────────────────
# Default: /tmp/mbg_workspace  |  Override: export MBG_WORKDIR=/your/path
export MBG_WORKDIR="${MBG_WORKDIR:-/tmp/mbg_workspace}"
mkdir -p "$MBG_WORKDIR" 2>/dev/null
echo "[MBG] Workdir: $MBG_WORKDIR"

# Each skill has its own core/ copy — add to path
for _skill_dir in "$REPO_DIR"/*/; do
    if [ -d "$_skill_dir/core" ]; then
        export PYTHONPATH="$_skill_dir/core:$PYTHONPATH"
    fi
done

# ── Auto-activate virtual environment if it exists ─────
VENV_PATH="$(realpath -m "$REPO_DIR/../../.venv" 2>/dev/null)"
if [ -f "$VENV_PATH/bin/activate" ]; then
    source "$VENV_PATH/bin/activate" 2>/dev/null
fi

# ── PDK Auto-Detection ─────────────────────────────────
# Priority: 1. PDK_ROOT/PDK env  2. /foss/pdks (Docker)  3. $HOME/.volare (volare)
export PDK="${PDK:-gf180mcuD}"

_found_pdk=""
for _try_root in \
    "${PDK_ROOT:+$PDK_ROOT/$PDK}" \
    "/foss/pdks/$PDK" \
    "$HOME/.volare/$PDK" \
    "/usr/local/share/pdk/$PDK"; do
    if [ -d "$_try_root" ] && [ -f "$_try_root/libs.tech/magic/${PDK}.magicrc" ]; then
        _found_pdk="$_try_root"
        export PDK_ROOT="$(dirname "$_try_root")"
        break
    fi
done

if [ -n "$_found_pdk" ]; then
    export PDKPATH="$_found_pdk"
    export STD_CELL_LIBRARY="${STD_CELL_LIBRARY:-gf180mcu_fd_sc_mcu7t5v0}"
    echo "[MBG] PDK:  $PDK ($PDKPATH)"
else
    export PDK_ROOT="${PDK_ROOT:-/home/huda/.volare}"
    export PDKPATH="${PDKPATH:-$PDK_ROOT/$PDK}"
    echo "[MBG] PDK:  $PDK NOT FOUND at $PDKPATH"
    echo "       Install with:"
    echo "         pip install volare"
    echo "         python3 -m volare enable --pdk-root $PDK_ROOT $PDK"
    echo "       Or run: bash $REPO_DIR/setup/install_pdk.sh"
fi

# ── Tool paths ─────────────────────────────────────────
for _tool_dir in /foss/tools/magic/bin /foss/tools/netgen/bin /usr/local/bin /usr/bin; do
    [ -d "$_tool_dir" ] && [[ ":$PATH:" != *":$_tool_dir:"* ]] && export PATH="$_tool_dir:$PATH"
done

# ── Tool check ─────────────────────────────────────────
_HAS_NGSPICE=$(command -v ngspice &>/dev/null && echo yes || echo no)
_HAS_MAGIC=$(command -v magic &>/dev/null && echo yes || echo no)
_HAS_NETGEN=$(command -v netgen &>/dev/null && echo yes || echo no)
_HAS_PDK=$([ -n "$_found_pdk" ] && echo yes || echo no)

echo "[MBG] Tools: ngspice=$_HAS_NGSPICE magic=$_HAS_MAGIC netgen=$_HAS_NETGEN pdk=$_HAS_PDK"
echo ""

# Show missing tools with install instructions
_MISSING=""
[ "$_HAS_NGSPICE" = no ] && _MISSING="$_MISSING ngspice"
[ "$_HAS_MAGIC" = no ] && _MISSING="$_MISSING magic"
[ "$_HAS_NETGEN" = no ] && _MISSING="$_MISSING netgen"
[ "$_HAS_PDK" = no ] && _MISSING="$_MISSING $PDK-PDK"

if [ -n "$_MISSING" ]; then
    echo "  ⚠️  Missing:$_MISSING"
    echo "     Install all:  bash $REPO_DIR/setup/install_all.sh"
    echo "     Docker:       python3 $REPO_DIR/setup/docker_sandbox.py"
    echo ""
fi
