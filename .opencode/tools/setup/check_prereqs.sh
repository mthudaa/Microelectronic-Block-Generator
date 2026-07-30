#!/bin/bash
# Quick dependency check — run before using any skill.
# Usage: bash setup/check_prereqs.sh
set -e

echo "========================================"
echo "  MBG Prerequisite Check"
echo "========================================"

# ── Python ─────────────────────────────────────────────
echo ""
echo "--- Python ---"
python3 --version 2>&1 || echo "  ❌ python3 not found"

# ── EDA Tools ──────────────────────────────────────────
echo ""
echo "--- EDA Tools ---"
for cmd in ngspice magic netgen; do
    if command -v "$cmd" &>/dev/null; then
        echo "  ✅ $cmd: $(which $cmd)"
        $cmd --version 2>&1 | head -1 || true
    else
        echo "  ❌ $cmd: not installed"
        echo "     Run: bash setup/install_all.sh"
    fi
done

# ── Python Packages ────────────────────────────────────
echo ""
echo "--- Python Packages ---"
for pkg in numpy gdsfactory gdstk glayout; do
    if python3 -c "import $pkg" 2>/dev/null; then
        ver=$(python3 -c "import $pkg; print(getattr($pkg, '__version__', 'ok'))" 2>/dev/null)
        echo "  ✅ $pkg: $ver"
    else
        echo "  ❌ $pkg: not installed"
    fi
done

# ── PDK ────────────────────────────────────────────────
echo ""
echo "--- PDK ---"
PDK_ROOT="${PDK_ROOT:-$HOME/.volare}"
PDK="${PDK:-gf180mcuD}"
if [ -f "$PDK_ROOT/$PDK/libs.tech/magic/$PDK.magicrc" ]; then
    echo "  ✅ PDK: $PDK at $PDK_ROOT/$PDK"
else
    echo "  ⚠️  PDK: $PDK not found at $PDK_ROOT/$PDK"
    echo "     Run: bash setup/install_all.sh"
fi

# ── Environment ────────────────────────────────────────
echo ""
echo "--- Environment ---"
echo "  PDK_ROOT=$PDK_ROOT"
echo "  PDK=$PDK"
echo "  PDKPATH=$PDKPATH"

echo ""
echo "========================================"
echo "  Done. Run 'source common/env.sh' to set up."
echo "========================================"
