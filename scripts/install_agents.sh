#!/usr/bin/env bash
#
# install_agents.sh — set up the Microelectronic Block Generator agent layer
# for OpenCode, Claude Code and Codex.
#
#   ./scripts/install_agents.sh              install everything that is available
#   ./scripts/install_agents.sh --check      report status, change nothing
#   ./scripts/install_agents.sh --only codex install one platform
#   ./scripts/install_agents.sh --uninstall  undo the Codex registration
#
# OpenCode and Claude Code need no global registration — they discover
# .opencode/ and .claude/ from the repository automatically. Codex does not
# have repo-scoped skills, so its plugin has to be registered once per machine;
# that step writes to ~/.codex/config.toml and asks first unless --yes is given.
#
# No git operations are performed. Nothing outside the repository is modified
# except the Codex registration you explicitly approve.

set -uo pipefail

MODE="install"
ONLY="all"
ASSUME_YES=0

while [ $# -gt 0 ]; do
    case "$1" in
        --check|--dry-run) MODE="check" ;;
        --uninstall)       MODE="uninstall" ;;
        --yes|-y)          ASSUME_YES=1 ;;
        --only)            ONLY="${2:-all}"; shift ;;
        --only=*)          ONLY="${1#*=}" ;;
        -h|--help)         sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "unknown option: $1 (try --help)" >&2; exit 2 ;;
    esac
    shift
done

case "$ONLY" in all|opencode|claude|codex) ;; *)
    echo "--only must be one of: all opencode claude codex" >&2; exit 2 ;;
esac

# ── repository root (never hardcoded) ──────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel 2>/dev/null)"
if [ -z "$REPO_ROOT" ]; then
    REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
fi
if [ ! -f "$REPO_ROOT/.ai/manifest.json" ]; then
    echo "ERROR: cannot find .ai/manifest.json from $SCRIPT_DIR" >&2
    echo "       Run this script from inside a clone of the repository." >&2
    exit 1
fi
cd "$REPO_ROOT" || exit 1

PY="$(command -v python3 || command -v python || true)"
if [ -z "$PY" ]; then
    echo "ERROR: python3 not found on PATH — required to generate the adapters." >&2
    exit 1
fi

ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$1"; }
bad()  { printf '  \033[31m✗\033[0m %s\n' "$1"; }
head_() { printf '\n\033[1m%s\033[0m\n' "$1"; }

want() { [ "$ONLY" = "all" ] || [ "$ONLY" = "$1" ]; }

STATUS_OPENCODE="not attempted"
STATUS_CLAUDE="not attempted"
STATUS_CODEX="not attempted"

confirm() {
    [ "$ASSUME_YES" = "1" ] && return 0
    [ ! -t 0 ] && return 1
    printf '  %s [y/N] ' "$1"
    read -r reply
    case "$reply" in [yY]*) return 0 ;; *) return 1 ;; esac
}

# ── Codex identifiers, read from the manifest so they cannot drift ─────
MARKET_NAME="$("$PY" - <<'PYEOF'
import json
m = json.load(open(".ai/manifest.json"))
print(m["platforms"]["codex"]["marketplace_name"])
PYEOF
)"
MARKET_FILE="$("$PY" - <<'PYEOF'
import json
m = json.load(open(".ai/manifest.json"))
print(m["platforms"]["codex"]["marketplace_file"])
PYEOF
)"
PLUGIN_NAME="$("$PY" - <<'PYEOF'
import json, os
m = json.load(open(".ai/manifest.json"))
print(os.path.basename(m["platforms"]["codex"]["plugin_root"]))
PYEOF
)"

# ══════════════════════════════════════════════════════════════════════
#  uninstall
# ══════════════════════════════════════════════════════════════════════
if [ "$MODE" = "uninstall" ]; then
    head_ "Uninstall"
    if ! command -v codex >/dev/null 2>&1; then
        warn "codex not on PATH — nothing to undo."
    else
        codex plugin remove "$PLUGIN_NAME@$MARKET_NAME" >/dev/null 2>&1 \
            && ok "removed plugin $PLUGIN_NAME@$MARKET_NAME" \
            || warn "plugin $PLUGIN_NAME@$MARKET_NAME was not installed"
        codex plugin marketplace remove "$MARKET_NAME" >/dev/null 2>&1 \
            && ok "removed marketplace $MARKET_NAME" \
            || warn "marketplace $MARKET_NAME was not registered"
    fi
    echo
    echo "OpenCode and Claude Code need no uninstall — they only read files in"
    echo "this repository. Delete the clone and they are gone."
    exit 0
fi

# ══════════════════════════════════════════════════════════════════════
#  regenerate adapters first, so every platform installs current content
# ══════════════════════════════════════════════════════════════════════
head_ "Canonical layer"
if [ "$MODE" = "check" ]; then
    if "$PY" scripts/sync_agent_tools.py --check >/dev/null 2>&1; then
        ok "adapters are up to date with .ai/"
    else
        warn "adapters are STALE — run: python3 scripts/sync_agent_tools.py"
    fi
else
    if "$PY" scripts/sync_agent_tools.py >/dev/null 2>&1; then
        ok "adapters regenerated from .ai/"
    else
        bad "sync failed — run 'python3 scripts/sync_agent_tools.py' to see why"
        exit 1
    fi
fi
N_SKILLS=$(find .ai/skills -name SKILL.md 2>/dev/null | wc -l | tr -d ' ')
N_FLOWS=$(find .ai/workflows -name '*.md' 2>/dev/null | wc -l | tr -d ' ')
ok "$N_SKILLS canonical skills, $N_FLOWS canonical workflows"

# ══════════════════════════════════════════════════════════════════════
#  OpenCode
# ══════════════════════════════════════════════════════════════════════
if want opencode; then
    head_ "OpenCode"
    if ! command -v opencode >/dev/null 2>&1; then
        warn "opencode not on PATH — skipping (install it, then re-run)"
        STATUS_OPENCODE="not installed"
    else
        ok "opencode $(opencode --version 2>/dev/null | head -1)"
        ok "$(find .opencode/skills -name SKILL.md | wc -l | tr -d ' ') skills, $(find .opencode/commands -name '*.md' | wc -l | tr -d ' ') commands discovered from .opencode/"

        # the custom .ts tools import @opencode-ai/plugin
        if [ -d .opencode/node_modules ]; then
            ok "custom tool dependencies present"
            STATUS_OPENCODE="ready"
        elif [ "$MODE" = "check" ]; then
            warn "custom tool dependencies MISSING — run this script without --check"
            STATUS_OPENCODE="needs npm install"
        elif command -v npm >/dev/null 2>&1; then
            printf '  … installing custom tool dependencies (npm)\n'
            if (cd .opencode && npm install --silent --no-fund --no-audit >/dev/null 2>&1); then
                ok "custom tool dependencies installed"
                STATUS_OPENCODE="ready"
            else
                warn "npm install failed — the 4 custom .ts tools will not load"
                warn "  skills and commands still work; retry with: cd .opencode && npm install"
                STATUS_OPENCODE="ready (tools unavailable)"
            fi
        else
            warn "npm not found — the 4 custom .ts tools will not load"
            STATUS_OPENCODE="ready (tools unavailable)"
        fi
        ok "permissions from opencode.jsonc"
    fi
fi

# ══════════════════════════════════════════════════════════════════════
#  Claude Code
# ══════════════════════════════════════════════════════════════════════
if want claude; then
    head_ "Claude Code"
    if ! command -v claude >/dev/null 2>&1; then
        warn "claude not on PATH — skipping (install it, then re-run)"
        STATUS_CLAUDE="not installed"
    else
        ok "claude $(claude --version 2>/dev/null | head -1)"
        ok "$(find .claude/skills -name SKILL.md | wc -l | tr -d ' ') skills, $(find .claude/commands -name '*.md' | wc -l | tr -d ' ') commands discovered from .claude/"
        [ -f CLAUDE.md ] && ok "CLAUDE.md imports the shared rules from AGENTS.md" \
                         || warn "CLAUDE.md missing — run the sync"
        [ -f .claude/settings.json ] && ok "permissions from .claude/settings.json" \
                                     || warn ".claude/settings.json missing"
        STATUS_CLAUDE="ready"
    fi
    echo "  Nothing to register: Claude Code reads .claude/ from this repository."
fi

# ══════════════════════════════════════════════════════════════════════
#  Codex — the only platform needing a per-machine registration
# ══════════════════════════════════════════════════════════════════════
if want codex; then
    head_ "Codex"
    if ! command -v codex >/dev/null 2>&1; then
        warn "codex not on PATH — skipping (install it, then re-run)"
        STATUS_CODEX="not installed"
    else
        ok "codex $(codex --version 2>/dev/null | head -1)"
        ok "AGENTS.md is read natively from the repository root"
        ok "marketplace manifest: $MARKET_FILE"

        # `codex plugin list` exits 0 even for an unregistered marketplace,
        # so the exit code cannot be used — inspect the actual listing.
        if codex plugin marketplace list 2>/dev/null | awk '{print $1}' | grep -qx "$MARKET_NAME"; then
            REGISTERED=1
        else
            REGISTERED=0
        fi
        if codex plugin list --marketplace "$MARKET_NAME" 2>/dev/null | grep -q "installed"; then
            INSTALLED=1
        else
            INSTALLED=0
        fi
        [ "$REGISTERED" = "1" ] && ok "marketplace '$MARKET_NAME' registered"
        [ "$INSTALLED"  = "1" ] && ok "plugin '$PLUGIN_NAME' installed"

        if [ "$MODE" = "check" ]; then
            if [ "$INSTALLED" = "1" ]; then
                STATUS_CODEX="ready"
            else
                warn "plugin not installed — run this script without --check"
                STATUS_CODEX="needs registration"
            fi
        elif [ "$INSTALLED" = "1" ]; then
            # Codex copies the plugin into its cache at install time, so a
            # re-sync does not reach it until the plugin is reinstalled.
            # remove+add refreshes the copy without needing a version bump,
            # which keeps generated output byte-for-byte deterministic.
            codex plugin remove "$PLUGIN_NAME@$MARKET_NAME" >/dev/null 2>&1
            if codex plugin add "$PLUGIN_NAME@$MARKET_NAME" >/dev/null 2>&1; then
                ok "plugin refreshed from the current adapters ($N_SKILLS skills)"
                STATUS_CODEX="ready"
            else
                bad "refresh failed — try: codex plugin add $PLUGIN_NAME@$MARKET_NAME"
                STATUS_CODEX="stale"
            fi
        else
            echo "  Codex has no repo-scoped skills, so its plugin is registered once"
            echo "  per machine. This writes to ~/.codex/config.toml:"
            echo "      codex plugin marketplace add ."
            echo "      codex plugin add $PLUGIN_NAME@$MARKET_NAME"
            if confirm "Register now?"; then
                MKOUT=""
                if [ "$REGISTERED" = "0" ]; then
                    # the source must be the DIRECTORY containing
                    # .agents/plugins/marketplace.json, not the file itself
                    MKOUT="$(codex plugin marketplace add . 2>&1)"
                fi
                if [ "$REGISTERED" = "1" ] || ! printf '%s' "$MKOUT" | grep -qi "^Error"; then
                    [ "$REGISTERED" = "0" ] && ok "marketplace '$MARKET_NAME' registered"
                    if codex plugin add "$PLUGIN_NAME@$MARKET_NAME" >/dev/null 2>&1; then
                        ok "plugin '$PLUGIN_NAME' installed ($N_SKILLS skills)"
                        STATUS_CODEX="ready"
                    else
                        bad "plugin install failed — try: codex plugin add $PLUGIN_NAME@$MARKET_NAME"
                        STATUS_CODEX="marketplace only"
                    fi
                else
                    bad "marketplace registration failed: $MKOUT"
                    STATUS_CODEX="failed"
                fi
            else
                warn "skipped — register later with: ./scripts/install_agents.sh --only codex"
                STATUS_CODEX="skipped by user"
            fi
        fi
        echo "  Codex has no repo-scoped slash commands; ask for a skill by name instead."
    fi
fi

# ══════════════════════════════════════════════════════════════════════
#  verify
# ══════════════════════════════════════════════════════════════════════
head_ "Verification"
if "$PY" scripts/validate_agent_integrations.py >/tmp/mbg_validate.$$ 2>&1; then
    ok "$(grep -E '^SUMMARY' /tmp/mbg_validate.$$ | head -1)"
    VALID=0
else
    bad "validation FAILED — full output:"
    sed 's/^/      /' /tmp/mbg_validate.$$ | tail -20
    VALID=1
fi
rm -f /tmp/mbg_validate.$$

head_ "Summary"
want opencode && printf '  %-14s %s\n' "OpenCode"    "$STATUS_OPENCODE"
want claude   && printf '  %-14s %s\n' "Claude Code" "$STATUS_CLAUDE"
want codex    && printf '  %-14s %s\n' "Codex"       "$STATUS_CODEX"
echo
echo "  Re-run after changing anything under .ai/:  python3 scripts/sync_agent_tools.py"
echo "  Check status without changing anything:     ./scripts/install_agents.sh --check"
exit $VALID
