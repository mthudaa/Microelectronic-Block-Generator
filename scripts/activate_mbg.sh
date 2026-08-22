# MBG environment activation — source this, do not execute it.
#
#   source scripts/activate_mbg.sh
#
# Activates in one step:
#   * the Python virtual environment
#   * PDK_ROOT / PDK / PDKPATH / STD_CELL_LIBRARY
#   * PATH entries for the MBG-local EDA tools
#
# Every path is derived from the location of this file or from $HOME, so the
# script works in any checkout, for any user, without editing.
#
# Existing settings win: if you already export PDK_ROOT or MBG_TOOLS_ROOT,
# they are respected rather than overwritten.

# --- locate the repository without assuming the caller's cwd ----------
if [ -n "${BASH_SOURCE:-}" ]; then
    _mbg_src="${BASH_SOURCE[0]}"
elif [ -n "${ZSH_VERSION:-}" ]; then
    _mbg_src="${(%):-%N}"
else
    _mbg_src="$0"
fi
_mbg_dir="$(cd -- "$(dirname -- "${_mbg_src}")" && pwd)"
MBG_ROOT="$(cd -- "${_mbg_dir}/.." && pwd)"
export MBG_ROOT

# --- prefer the installed activation ----------------------------------
# install_shell.sh generates ~/.mbg/activate.sh from what it actually found
# on this machine, including pinned MBG_MAGIC / MBG_NETGEN / MBG_KLAYOUT
# paths. This file predates it and sets a strict subset, so if the generated
# one exists it wins — two activation scripts that drift apart is how you end
# up with DRC sign-off silently unavailable in one shell but not another.
if [ -f "${MBG_HOME:-$HOME/.mbg}/activate.sh" ] && [ -z "${MBG_ACTIVATE_LEGACY:-}" ]; then
    # shellcheck disable=SC1091
    . "${MBG_HOME:-$HOME/.mbg}/activate.sh"
    [ -f "${MBG_VENV:-$MBG_ROOT/.venv}/bin/activate" ] && [ -z "${VIRTUAL_ENV:-}" ] \
        && . "${MBG_VENV:-$MBG_ROOT/.venv}/bin/activate"
    printf 'mbg: %s (via ~/.mbg/activate.sh)\n' "${MBG_ROOT}"
    unset _mbg_src _mbg_dir
    return 0 2>/dev/null || true
fi

# --- Python virtual environment ---------------------------------------
_mbg_venv="${MBG_VENV:-${MBG_ROOT}/.venv}"
if [ -x "${_mbg_venv}/bin/activate" ] || [ -f "${_mbg_venv}/bin/activate" ]; then
    # shellcheck disable=SC1091
    . "${_mbg_venv}/bin/activate"
else
    printf 'mbg: no virtual environment at %s\n' "${_mbg_venv}" >&2
    printf 'mbg: run ./scripts/setup_env.sh first\n' >&2
fi

# --- PDK ---------------------------------------------------------------
# These must be exported before anything imports glayout, which reads them at
# import time and calls Path() on the result.
export PDK_ROOT="${PDK_ROOT:-${HOME}/.volare}"
export PDK="${PDK:-gf180mcuD}"
export PDKPATH="${PDKPATH:-${PDK_ROOT}/${PDK}}"
export STD_CELL_LIBRARY="${STD_CELL_LIBRARY:-gf180mcu_fd_sc_mcu7t5v0}"

# --- MBG-local EDA tools ----------------------------------------------
export MBG_TOOLS_ROOT="${MBG_TOOLS_ROOT:-${HOME}/.local/mbg-tools}"
if [ -d "${MBG_TOOLS_ROOT}" ]; then
    for _mbg_tool in "${MBG_TOOLS_ROOT}"/magic-* "${MBG_TOOLS_ROOT}"/netgen-*; do
        [ -d "${_mbg_tool}/bin" ] || continue
        case ":${PATH}:" in
            *":${_mbg_tool}/bin:"*) ;;
            *) PATH="${_mbg_tool}/bin:${PATH}" ;;
        esac
        case "$(basename "${_mbg_tool}")" in
            magic-*)  export MBG_MAGIC_ROOT="${_mbg_tool}" ;;
            netgen-*) export MBG_NETGEN_ROOT="${_mbg_tool}" ;;
        esac
    done
    export PATH
    unset _mbg_tool
fi

printf 'mbg: %s\n' "${MBG_ROOT}"
printf 'mbg: PDK %s at %s\n' "${PDK}" "${PDKPATH}"
if [ -n "${MBG_MAGIC_ROOT:-}" ] || [ -n "${MBG_NETGEN_ROOT:-}" ]; then
    printf 'mbg: local EDA tools from %s\n' "${MBG_TOOLS_ROOT}"
fi
printf 'mbg: run ./scripts/setup_env.sh --check to verify\n'

unset _mbg_src _mbg_dir _mbg_venv
