#!/usr/bin/env bash
#
# setup_env.sh — create and verify the Python environment for the
# Microelectronic Block Generator.
#
#   ./scripts/setup_env.sh                 create .venv and install (editable)
#   ./scripts/setup_env.sh --locked        install the exact pinned versions
#   ./scripts/setup_env.sh --check         report status, install nothing
#   ./scripts/setup_env.sh --system        install into the active interpreter
#   ./scripts/setup_env.sh --freeze        rewrite requirements-lock.txt
#
# After this, `import mbg` works from anywhere and `mbg-sync` / `mbg-validate`
# are on PATH inside the environment.
#
# The EDA tools themselves (ngspice, Magic, netgen) and the GF180MCU PDK are
# NOT installed here — they live in the IIC-OSIC-TOOLS container. This script
# reports whether it can see them.

set -uo pipefail

MODE="install"
LOCKED=0
TARGET="venv"

while [ $# -gt 0 ]; do
    case "$1" in
        --check)   MODE="check" ;;
        --freeze)  MODE="freeze" ;;
        --locked)  LOCKED=1 ;;
        --system)  TARGET="system" ;;
        -h|--help) sed -n '2,18p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "unknown option: $1 (try --help)" >&2; exit 2 ;;
    esac
    shift
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel 2>/dev/null)"
[ -z "$REPO_ROOT" ] && REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
if [ ! -f "$REPO_ROOT/pyproject.toml" ]; then
    echo "ERROR: pyproject.toml not found at $REPO_ROOT" >&2; exit 1
fi
cd "$REPO_ROOT" || exit 1

ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$1"; }
bad()  { printf '  \033[31m✗\033[0m %s\n' "$1"; }
hdr()  { printf '\n\033[1m%s\033[0m\n' "$1"; }

VENV="$REPO_ROOT/.venv"

# ── pick an interpreter ────────────────────────────────────────────────
# gdsfactory 7 + numpy 1 need Python 3.10-3.12; 3.13+ has no wheels for them.
pick_python() {
    # 3.10 first: that is the version the project is validated on, and the
    # one with wheels for every pinned dependency.
    for c in python3.10 python3.11 python3.12 python3; do
        p="$(command -v "$c" 2>/dev/null)" || continue
        v="$("$p" -c 'import sys;print("%d%d"%sys.version_info[:2])' 2>/dev/null)" || continue
        if [ "$v" -ge 310 ] && [ "$v" -le 312 ]; then echo "$p"; return 0; fi
    done
    return 1
}

hdr "Interpreter"
if [ "$TARGET" = "system" ]; then
    PY="$(command -v python3)"
    ok "using the active interpreter: $($PY --version 2>&1)"
else
    if [ -x "$VENV/bin/python" ]; then
        PY="$VENV/bin/python"
        ok "existing environment: $VENV ($($PY --version 2>&1))"
    elif [ "$MODE" = "check" ]; then
        warn "no environment at $VENV — run without --check to create it"
        PY=""
    else
        BASE="$(pick_python)" || {
            bad "no Python 3.10-3.12 found. gdsfactory 7 and numpy 1 have no"
            bad "  wheels for 3.13+; install one of those versions and re-run."
            exit 1; }
        echo "  creating $VENV with $($BASE --version 2>&1)"
        "$BASE" -m venv "$VENV" || { bad "venv creation failed"; exit 1; }
        PY="$VENV/bin/python"
        ok "created $VENV"
    fi
fi

# ── freeze ─────────────────────────────────────────────────────────────
if [ "$MODE" = "freeze" ]; then
    hdr "Freeze"
    [ -z "$PY" ] && { bad "no environment to freeze"; exit 1; }
    "$PY" -m pip freeze 2>/dev/null | grep -viE '^-e |^#' | sort > requirements-lock.txt
    ok "requirements-lock.txt updated ($(wc -l < requirements-lock.txt) packages)"
    exit 0
fi

# ── install ────────────────────────────────────────────────────────────
if [ "$MODE" = "install" ] && [ -n "$PY" ]; then
    hdr "Install"
    "$PY" -m pip install --quiet --upgrade pip setuptools wheel >/dev/null 2>&1 \
        && ok "build tooling up to date" || warn "could not upgrade pip"

    if [ "$LOCKED" = "1" ]; then
        if [ -f requirements-lock.txt ]; then
            echo "  installing pinned versions (this reproduces a known-good environment)"
            "$PY" -m pip install --quiet -r requirements-lock.txt \
                && ok "locked dependencies installed" \
                || { bad "locked install failed"; exit 1; }
        else
            bad "requirements-lock.txt not found"; exit 1
        fi
    fi

    echo "  installing mbg (editable) with dev + notebook extras"
    if "$PY" -m pip install --quiet -e ".[dev,notebooks]"; then
        ok "mbg installed — 'import mbg' now works from anywhere"
    else
        warn "editable install failed; falling back to requirements.txt"
        "$PY" -m pip install --quiet -r requirements.txt \
            && ok "dependencies installed (package not installed)" \
            || { bad "install failed"; exit 1; }
    fi
fi

# ── verify ─────────────────────────────────────────────────────────────
hdr "Python environment"
if [ -z "$PY" ]; then
    warn "no environment to verify"
else
    "$PY" - <<'PYCHECK'
import importlib, sys
print(f"  python {sys.version.split()[0]}")
rows = [("mbg", None), ("gdsfactory", "7"), ("numpy", "1"), ("gdstk", None),
        ("glayout", None), ("nbclient", None)]
missing = []
for name, want_major in rows:
    try:
        m = importlib.import_module(name)
        v = getattr(m, "__version__", "?")
        flag = ""
        if want_major and str(v).split(".")[0] != want_major:
            flag = f"  <-- expected {want_major}.x"
        print(f"  \033[32m✓\033[0m {name:12s} {v}{flag}")
    except Exception as e:
        missing.append(name)
        print(f"  \033[31m✗\033[0m {name:12s} {type(e).__name__}")
sys.exit(1 if missing else 0)
PYCHECK
fi

hdr "EDA toolchain (provided by IIC-OSIC-TOOLS, not by this script)"
for t in ngspice magic netgen klayout; do
    if command -v "$t" >/dev/null 2>&1; then ok "$t"; else warn "$t not on PATH"; fi
done

hdr "PDK"
PDK_ROOT_EFF="${PDK_ROOT:-$HOME/.volare}"
PDK_EFF="${PDK:-gf180mcuD}"
if [ -d "$PDK_ROOT_EFF/$PDK_EFF" ]; then
    ok "$PDK_EFF at $PDK_ROOT_EFF"
    MODELS="$PDK_ROOT_EFF/$PDK_EFF/libs.tech/ngspice/sm141064.ngspice"
    [ -f "$MODELS" ] && ok "ngspice models found" || warn "ngspice models missing"
else
    warn "$PDK_EFF not found under $PDK_ROOT_EFF"
    echo "      export PDK_ROOT=/foss/pdks   # inside the container"
    echo "      or: pip install volare && python3 -m volare enable --pdk gf180mcu <version>"
fi

hdr "Next"
if [ "$TARGET" = "venv" ] && [ -n "$PY" ]; then
    echo "  source .venv/bin/activate"
fi
echo "  ./scripts/install_agents.sh        # register the agent integrations"
echo "  python tests/test_all_designs.py   # end-to-end check"
