#!/bin/bash
# MBG Python Virtual Environment Setup
# Creates a complete .venv with all dependencies including glayout.
# Usage: bash setup/create_venv.sh [--venv-path /path/to/.venv]
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MBG_DIR="$(dirname "$SCRIPT_DIR")"
DEFAULT_VENV="$MBG_DIR/../../.venv"
VENV_PATH="${1:-$DEFAULT_VENV}"
VENV_PATH="$(realpath -m "$VENV_PATH")"

echo "============================================"
echo "  MBG Python Virtual Environment Setup"
echo "============================================"
echo "  Target: $VENV_PATH"
echo "============================================"

# ── Step 1: Create venv ────────────────────────────────
if [ -d "$VENV_PATH" ]; then
    echo "[INFO] Virtual environment already exists at $VENV_PATH"
    echo "       Delete it first to recreate: rm -rf $VENV_PATH"
else
    echo "[INFO] Creating virtual environment..."
    python3 -m venv "$VENV_PATH"
    echo "[OK] Virtual environment created"
fi

# ── Step 2: Activate ────────────────────────────────────
source "$VENV_PATH/bin/activate" 2>/dev/null || {
    echo "[ERROR] Failed to activate venv at $VENV_PATH"
    exit 1
}
echo "[INFO] Python: $(which python3) ($(python3 --version))"
echo "[INFO] Pip:    $(pip --version | head -c 60)"

# ── Step 3: Upgrade pip ─────────────────────────────────
echo ""
echo "--- Step 1/5: Upgrading pip ---"
pip install --upgrade pip setuptools wheel 2>&1 | tail -3

# ── Step 4: Install core Python deps ────────────────────
echo ""
echo "--- Step 2/5: NumPy/SciPy ---"
pip install numpy scipy 2>&1 | tail -3

echo ""
echo "--- Step 3/5: gdsfactory + gdstk ---"
pip install gdsfactory gdstk 2>&1 | tail -5

echo ""
echo "--- Step 4/5: glayout (from GitHub) ---"
# Patch numpy for glayout compatibility (np.float_ removal in NumPy 2.0+)
python3 -c "
import numpy as np
if not hasattr(np, 'float_'):
    np.float_ = np.float64
print('[INFO] NumPy patch applied for glayout compatibility')
"
pip install glayout@git+https://github.com/ReaLLMASIC/gLayout.git --no-deps 2>&1 | tail -5

echo ""
echo "--- Step 5/5: Verify installation ---"
verify_pkg() {
    python3 -c "import $1; v=getattr($1, '__version__', 'ok'); print(f'  ✅ $1=={v}')" 2>/dev/null || echo "  ❌ $1 FAILED"
}
verify_pkg numpy
verify_pkg gdsfactory
verify_pkg gdstk
verify_pkg glayout

# ── Step 5: Create activate helper ──────────────────────
echo ""
echo "--- Activate Script ---"
ACTIVATE_SCRIPT="$MBG_DIR/common/activate_venv.sh"
cat > "$ACTIVATE_SCRIPT" << EOF
#!/bin/bash
# Activate the MBG Python virtual environment.
# Usage: source \$(dirname \$0)/activate_venv.sh

VENV_PATH="$VENV_PATH"
if [ ! -f "\$VENV_PATH/bin/activate" ]; then
    echo "[ERROR] Virtual environment not found at \$VENV_PATH"
    echo "       Run: bash $MBG_DIR/setup/create_venv.sh"
    return 1
fi
source "\$VENV_PATH/bin/activate"
echo "[VENV] Python: \$(which python3)"
echo "[VENV] glayout: \$(python3 -c 'import glayout; print(glayout.__version__)' 2>/dev/null || echo 'not found')"
EOF
chmod +x "$ACTIVATE_SCRIPT"

echo ""
echo "============================================"
echo "  Virtual Environment Setup Complete!"
echo "============================================"
echo ""
echo "  Activate with:"
echo "    source $ACTIVATE_SCRIPT"
echo "    # or directly:"
echo "    source $VENV_PATH/bin/activate"
echo ""
echo "  Then use skills as normal:"
echo "    source pi-custom-mbg/common/env.sh"
echo "    python inv_full_flow.py"
echo ""
echo "  To delete and recreate:"
echo "    rm -rf $VENV_PATH && bash setup/create_venv.sh"
echo "============================================"
