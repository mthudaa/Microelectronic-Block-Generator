#!/bin/bash
# Activate the MBG Python virtual environment.
# Usage: source <path>/activate_venv.sh

# Auto-detect: find .venv relative to this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MBG_DIR="$(dirname "$SCRIPT_DIR")"
VENV_PATH="${MBG_DIR}/../../.venv"
VENV_PATH="$(realpath -m "$VENV_PATH")"

if [ ! -f "$VENV_PATH/bin/activate" ]; then
    echo "[ERROR] Virtual environment not found at $VENV_PATH"
    echo "       Create it first:"
    echo "       bash $MBG_DIR/setup/create_venv.sh"
    return 1
fi

source "$VENV_PATH/bin/activate"

# Verify key packages
python3 -c "
import numpy as np
if not hasattr(np, 'float_'):
    np.float_ = np.float64
import sys
ok = True
for pkg in ['glayout', 'gdsfactory', 'gdstk']:
    try:
        __import__(pkg)
        print(f'  ✅ {pkg}')
    except ImportError:
        print(f'  ❌ {pkg}')
        ok = False
if not ok:
    print('  Run: bash $(dirname ${BASH_SOURCE[0]})/../setup/create_venv.sh')
" 2>/dev/null

echo "[VENV] Python: $(which python3)"
echo "[VENV] Ready for MBG skills"
