#!/usr/bin/env bash
# MBG local environment installer — no Docker, no root, no fixed paths.
#
#   ./scripts/setup_env.sh              full local install (python + pdk + eda)
#   ./scripts/setup_env.sh --check      preflight only; installs nothing
#   ./scripts/setup_env.sh --python-only
#   ./scripts/setup_env.sh --pdk        GF180MCU PDK via volare
#   ./scripts/setup_env.sh --eda        build Magic and netgen under the tools root
#   ./scripts/setup_env.sh --deps       print (or install, with --yes) OS build deps
#
# Everything the script creates lives in one of two places:
#   <repo>/.venv                              the Python environment
#   $MBG_TOOLS_ROOT (default ~/.local/mbg-tools)   EDA builds
# Nothing is written to /usr, /usr/local, or the system package database
# unless you explicitly pass --deps --yes, which asks sudo for OS packages.

set -euo pipefail

# ── locations (all derived, none hard-coded) ──────────────────────────
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
VENV="${MBG_VENV:-${REPO_ROOT}/.venv}"
TOOLS_ROOT="${MBG_TOOLS_ROOT:-${HOME}/.local/mbg-tools}"
PDK_ROOT_EFF="${PDK_ROOT:-${HOME}/.volare}"
PDK_NAME="${PDK:-gf180mcuD}"
STD_CELLS="${STD_CELL_LIBRARY:-gf180mcu_fd_sc_mcu7t5v0}"

# ── pinned tool versions ──────────────────────────────────────────────
# Minimum Magic is dictated by the PDK techfile ("requires magic-8.3.411").
# We build a known-good newer tag when we have to build at all; an existing
# install is accepted on the >= rule, so nobody is forced to rebuild.
MAGIC_VERSION="${MBG_MAGIC_VERSION:-8.3.681}"
NETGEN_VERSION="${MBG_NETGEN_VERSION:-1.5.323}"
MAGIC_REPO="https://github.com/RTimothyEdwards/magic.git"
NETGEN_REPO="https://github.com/RTimothyEdwards/netgen.git"
VOLARE_PDK_VERSION="${MBG_PDK_VERSION:-}"      # empty = volare's default for gf180mcu

PY_MIN="3.10"
PY_MAX_EXCL="3.13"

MODE="all"
ASSUME_YES=0

# ── output helpers ────────────────────────────────────────────────────
if [ -t 1 ]; then
    B=$'\033[1m'; G=$'\033[32m'; Y=$'\033[33m'; R=$'\033[31m'; C=$'\033[36m'; N=$'\033[0m'
else
    B=""; G=""; Y=""; R=""; C=""; N=""
fi
say()  { printf '%s\n' "$*"; }
head_() { printf '\n%s%s%s\n' "$B" "$*" "$N"; }
ok()   { printf '  %-22s %sPASS%s  %s\n' "$1" "$G" "$N" "${2-}"; }
warn() { printf '  %-22s %sWARN%s  %s\n' "$1" "$Y" "$N" "${2-}"; }
opt()  { printf '  %-22s %sOPTIONAL%s  %s\n' "$1" "$C" "$N" "${2-}"; }
bad()  { printf '  %-22s %sFAIL%s  %s\n' "$1" "$R" "$N" "${2-}"; FAILED=$((FAILED+1)); }
die()  { printf '\n%sERROR%s %s\n' "$R" "$N" "$*" >&2; exit 1; }
FAILED=0

usage() { sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 0; }

while [ $# -gt 0 ]; do
    case "$1" in
        --check)        MODE="check" ;;
        --python-only)  MODE="python" ;;
        --pdk)          MODE="pdk" ;;
        --eda)          MODE="eda" ;;
        --deps)         MODE="deps" ;;
        --yes|-y)       ASSUME_YES=1 ;;
        -h|--help)      usage ;;
        *) die "unknown option: $1  (try --help)" ;;
    esac
    shift
done

# ── OS detection ──────────────────────────────────────────────────────
detect_distro() {
    if [ -r /etc/os-release ]; then
        # shellcheck disable=SC1091
        . /etc/os-release
        DISTRO_ID="${ID:-unknown}"
        DISTRO_LIKE="${ID_LIKE:-}"
        DISTRO_NAME="${PRETTY_NAME:-${NAME:-unknown}}"
    else
        DISTRO_ID="unknown"; DISTRO_LIKE=""; DISTRO_NAME="unknown"
    fi
}

pkg_family() {
    case "$DISTRO_ID $DISTRO_LIKE" in
        *debian*|*ubuntu*) echo apt ;;
        *fedora*|*rhel*|*centos*|*rocky*|*almalinux*) echo dnf ;;
        *arch*|*manjaro*) echo pacman ;;
        *suse*) echo zypper ;;
        *) echo unknown ;;
    esac
}

build_deps() {
    case "$(pkg_family)" in
      apt)    echo "build-essential git m4 tcl-dev tk-dev libcairo2-dev \
libx11-dev mesa-common-dev libglu1-mesa-dev python3-dev python3-venv" ;;
      dnf)    echo "gcc gcc-c++ make git m4 tcl-devel tk-devel cairo-devel \
libX11-devel mesa-libGLU-devel python3-devel" ;;
      pacman) echo "base-devel git m4 tcl tk cairo libx11 glu python" ;;
      zypper) echo "gcc gcc-c++ make git m4 tcl-devel tk-devel cairo-devel \
libX11-devel Mesa-libGLU-devel python3-devel" ;;
      *)      echo "" ;;
    esac
}

install_deps_cmd() {
    case "$(pkg_family)" in
      apt)    echo "sudo apt-get update && sudo apt-get install -y $(build_deps)" ;;
      dnf)    echo "sudo dnf install -y $(build_deps)" ;;
      pacman) echo "sudo pacman -S --needed $(build_deps)" ;;
      zypper) echo "sudo zypper install -y $(build_deps)" ;;
      *)      echo "" ;;
    esac
}

do_deps() {
    head_ "System build prerequisites"
    say "  distribution : ${DISTRO_NAME}"
    local cmd; cmd="$(install_deps_cmd)"
    if [ -z "$cmd" ]; then
        warn "package manager" "unrecognised — install a C toolchain, Tcl/Tk, Cairo and X11 headers"
        return 0
    fi
    say ""
    say "  These OS packages are needed only to BUILD Magic and netgen."
    say "  If you already have working Magic and netgen you can skip this."
    say ""
    say "    ${cmd}"
    say ""
    if [ "$ASSUME_YES" -eq 1 ]; then
        say "  --yes given: running the command above (sudo will prompt)."
        bash -c "$cmd"
    else
        say "  Not run. Installing OS packages needs root, so it is never done"
        say "  silently. Re-run with:  ./scripts/setup_env.sh --deps --yes"
    fi
}

# ── python ────────────────────────────────────────────────────────────
pick_python() {
    local c
    # 3.11 first on purpose: it is the version requirements-lock.txt was
    # produced against, so the pinned set installs from wheels. Newer is not
    # better here — numpy 1.24 has no cp312 wheel and its source build fails
    # on 3.12 (setuptools reaches for pkgutil.ImpImporter, removed there).
    for c in "${MBG_PYTHON:-}" python3.11 python3.10 python3.12 python3; do
        [ -n "$c" ] || continue
        command -v "$c" >/dev/null 2>&1 || continue
        if "$c" - <<'EOF' >/dev/null 2>&1
import sys
raise SystemExit(0 if (3,10) <= sys.version_info < (3,13) else 1)
EOF
        then echo "$c"; return 0; fi
    done
    return 1
}

do_python() {
    head_ "Python environment"
    local py
    if ! py="$(pick_python)"; then
        die "no supported Python found (need >= ${PY_MIN}, < ${PY_MAX_EXCL}).
  Install one, or point MBG_PYTHON at it:
      MBG_PYTHON=/usr/bin/python3.11 ./scripts/setup_env.sh"
    fi
    say "  Python executable : $(command -v "$py")"
    say "  Python version    : $("$py" -c 'import sys;print(".".join(map(str,sys.version_info[:3])))')"
    say "  venv              : ${VENV}"

    if [ ! -x "${VENV}/bin/python" ]; then
        say "  creating virtual environment…"
        "$py" -m venv "${VENV}"
    else
        # A venv whose interpreter no longer resolves is worse than none: it
        # fails later, deep inside an import, instead of here.
        if ! "${VENV}/bin/python" -c 'import sys' >/dev/null 2>&1; then
            say "  existing venv is broken (dangling interpreter) — recreating"
            rm -rf "${VENV}"
            "$py" -m venv "${VENV}"
        fi
    fi

    "${VENV}/bin/python" -m pip install --quiet --upgrade pip setuptools wheel
    if [ -f "${REPO_ROOT}/requirements-lock.txt" ] && [ "${MBG_LOCKED:-1}" = "1" ]; then
        say "  installing pinned dependencies (requirements-lock.txt)…"
        "${VENV}/bin/python" -m pip install --quiet -r "${REPO_ROOT}/requirements-lock.txt" || {
            warn "locked install" "failed — falling back to requirements.txt"
            "${VENV}/bin/python" -m pip install --quiet -r "${REPO_ROOT}/requirements.txt"
        }
    else
        "${VENV}/bin/python" -m pip install --quiet -r "${REPO_ROOT}/requirements.txt"
    fi
    say "  installing mbg (editable)…"
    "${VENV}/bin/python" -m pip install --quiet -e "${REPO_ROOT}"
    ok "python env" "${VENV}"
}

# ── PDK ───────────────────────────────────────────────────────────────
pdk_present() { [ -f "${PDK_ROOT_EFF}/${PDK_NAME}/libs.tech/magic/${PDK_NAME}.tech" ]; }

do_pdk() {
    head_ "GF180MCU PDK"
    say "  PDK_ROOT : ${PDK_ROOT_EFF}"
    say "  PDK      : ${PDK_NAME}"
    if pdk_present; then
        ok "pdk" "already installed"
        return 0
    fi
    [ -x "${VENV}/bin/python" ] || die "create the Python environment first: ./scripts/setup_env.sh --python-only"
    say "  installing volare…"
    "${VENV}/bin/python" -m pip install --quiet volare
    say "  fetching the PDK (this downloads a few hundred MB)…"
    mkdir -p "${PDK_ROOT_EFF}"
    if [ -n "$VOLARE_PDK_VERSION" ]; then
        PDK_ROOT="${PDK_ROOT_EFF}" "${VENV}/bin/python" -m volare enable \
            --pdk gf180mcu "$VOLARE_PDK_VERSION"
    else
        PDK_ROOT="${PDK_ROOT_EFF}" "${VENV}/bin/python" -m volare enable --pdk gf180mcu
    fi
    if pdk_present; then ok "pdk" "installed at ${PDK_ROOT_EFF}/${PDK_NAME}"
    else bad "pdk" "volare finished but ${PDK_NAME} techfile is still missing"; fi
}

# ── EDA ───────────────────────────────────────────────────────────────
have_build_tools() { command -v git >/dev/null && command -v make >/dev/null && command -v gcc >/dev/null; }

tcl_version() {
    local cfg
    for cfg in /usr/lib64/tclConfig.sh /usr/lib/tclConfig.sh \
               /usr/lib/x86_64-linux-gnu/tclConfig.sh /usr/local/lib/tclConfig.sh; do
        [ -r "$cfg" ] || continue
        sed -n "s/^TCL_VERSION='\{0,1\}\([0-9.]*\)'\{0,1\}.*/\1/p" "$cfg" | head -1
        return 0
    done
    echo ""
}

# Magic and netgen are Tcl/Tk applications. Distributions that have moved to
# Tcl 9 (Fedora 43 and newer) break the source build: configure links against
# -ltcl9.0, the extension fails to load, and the installed launcher is a
# script with nothing behind it. Say so up front rather than after a build.
warn_if_tcl9() {
    local v; v="$(tcl_version)"
    case "$v" in
        9.*) warn "tcl" "system Tcl is ${v}; Magic/netgen need Tcl 8.6 to build"
             say  "        Install the 8.6 development package and point configure at it,"
             say  "        or use an existing Magic/netgen built against Tcl 8.6."
             say  "        A tool that already works is detected and reused — you may"
             say  "        not need to build anything at all."
             return 1 ;;
        "")  warn "tcl" "could not determine the system Tcl version" ;;
        *)   ok   "tcl" "${v}" ;;
    esac
    return 0
}

build_tool() {   # name repo version [jobs]
    local name="$1" repo="$2" version="$3" jobs="${4:-}"
    local prefix="${TOOLS_ROOT}/${name}-${version}"
    local src="${TOOLS_ROOT}/src/${name}-${version}"
    if [ -x "${prefix}/bin/${name}" ]; then
        ok "${name}" "already built at ${prefix}"
        return 0
    fi
    have_build_tools || die "git, make and a C compiler are required to build ${name}.
  Run:  ./scripts/setup_env.sh --deps        (prints the packages)
        ./scripts/setup_env.sh --deps --yes  (installs them via sudo)"

    say "  building ${name} ${version} -> ${prefix}"
    mkdir -p "${TOOLS_ROOT}/src"
    rm -rf "${src}"
    # Pinned tag, shallow clone, from the maintainer's own repository. No
    # piping a downloaded script into a shell.
    git clone --quiet --depth 1 --branch "${version}" "${repo}" "${src}" 2>/dev/null \
      || git clone --quiet --depth 1 "${repo}" "${src}"
    (
        cd "${src}"
        ./configure --prefix="${prefix}" >"${src}/configure.log" 2>&1 \
            || { tail -25 "${src}/configure.log"; die "${name}: configure failed (see ${src}/configure.log)"; }
        make -j"${jobs}" >>"${src}/build.log" 2>&1 \
            || { tail -25 "${src}/build.log"; die "${name}: build failed (see ${src}/build.log)"; }
        make install >>"${src}/build.log" 2>&1 \
            || { tail -25 "${src}/build.log"; die "${name}: install failed (see ${src}/build.log)"; }
    )
    [ -x "${prefix}/bin/${name}" ] || die "${name}: build finished but ${prefix}/bin/${name} is missing"

    # An installed file is not a working tool. netgen in particular installs a
    # launcher script that runs fine while the Tcl library it needs was never
    # linked, so the binary exists and every invocation fails. Verify with the
    # same resolver the pipeline uses, so "installed" means "usable".
    if [ -x "${VENV}/bin/python" ]; then
        if ! MBG_TOOLS_ROOT="${TOOLS_ROOT}" \
             MBG_$(echo "$name" | tr '[:lower:]' '[:upper:]')_ROOT="${prefix}" \
             PDK_ROOT="${PDK_ROOT_EFF}" PDK="${PDK_NAME}" \
             PDKPATH="${PDK_ROOT_EFF}/${PDK_NAME}" \
             "${VENV}/bin/python" -c "
import sys
from mbg import config
info = getattr(config, 'resolve_' + '${name}')()
sys.exit(0 if info.ok else 1)
" 2>/dev/null
        then
            grep -iE "no rule to make target|error:|cannot open shared object" \
                "${src}/build.log" | head -5 | sed 's/^/    /'
            local tclv; tclv="$(tcl_version)"
            grep -iE "no rule to make target|error:|cannot open shared object" \
                "${src}/build.log" | head -5 | sed 's/^/    /'
            if [ "${tclv%%.*}" = "9" ]; then
                say ""
                say "  Cause: this system has Tcl ${tclv}. ${name} builds its Tcl"
                say "  extension against the system Tcl and supports 8.6; with Tcl 9"
                say "  the extension cannot load, so the installed launcher script"
                say "  has nothing behind it."
                say ""
                say "  Options:"
                say "    - reuse an existing ${name} built against Tcl 8.6; MBG detects"
                say "      and prefers any working install (./scripts/setup_env.sh --check)"
                say "    - install Tcl 8.6 development files, then rebuild"
                say "    - use the optional Docker image, which ships working tools"
                say ""
                die "${name} ${version}: built, but not usable on this host. Log: ${src}/build.log"
            fi
            die "${name} ${version} built but does not work (see ${src}/build.log).
  This is usually a missing build dependency:
      ./scripts/setup_env.sh --deps"
        fi
    fi
    ok "${name}" "${prefix}/bin/${name}"
}

do_eda() {
    head_ "EDA toolchain (user-local, no root)"
    say "  tools root : ${TOOLS_ROOT}"
    local need_magic=1 need_netgen=1
    warn_if_tcl9 || true
    if [ -x "${VENV}/bin/python" ]; then
        # Ask the resolver, which applies the version and functional checks.
        if PDK_ROOT="${PDK_ROOT_EFF}" PDK="${PDK_NAME}" \
           PDKPATH="${PDK_ROOT_EFF}/${PDK_NAME}" \
           "${VENV}/bin/python" -c 'import sys;from mbg import config;sys.exit(0 if config.resolve_magic().ok else 1)' 2>/dev/null
        then need_magic=0; ok "magic" "an existing installation is compatible"; fi
        if PDK_ROOT="${PDK_ROOT_EFF}" PDK="${PDK_NAME}" \
           "${VENV}/bin/python" -c 'import sys;from mbg import config;sys.exit(0 if config.resolve_netgen().ok else 1)' 2>/dev/null
        then need_netgen=0; ok "netgen" "an existing installation is compatible"; fi
    fi
    local jobs; jobs="$(nproc 2>/dev/null || echo 2)"
    [ "$need_magic" -eq 1 ]  && build_tool magic  "$MAGIC_REPO"  "$MAGIC_VERSION" "$jobs"
    # netgen is built with one job on purpose: its Makefile races under -j
    # ("No rule to make target '../base/libbase.o', needed by 'tclnetgen.so'"),
    # which produces a launcher script with no Tcl library behind it.
    [ "$need_netgen" -eq 1 ] && build_tool netgen "$NETGEN_REPO" "$NETGEN_VERSION" 1
    return 0
}

# ── preflight ─────────────────────────────────────────────────────────
do_check() {
    say ""
    say "${B}MBG Local Environment Check${N}"
    say "=================================================="

    head_ "Operating System"
    ok "distro" "${DISTRO_NAME}"

    head_ "Python"
    if [ -x "${VENV}/bin/python" ]; then
        ok "virtualenv" "${VENV}"
        ok "python" "$("${VENV}/bin/python" -c 'import sys;print(".".join(map(str,sys.version_info[:3])))')"
        local pyv
        pyv="$("${VENV}/bin/python" -c 'import sys;print(1 if (3,10)<=sys.version_info<(3,13) else 0)')"
        [ "$pyv" = "1" ] || bad "python version" "outside the supported range ${PY_MIN}–${PY_MAX_EXCL}"
        for pkg in mbg gdsfactory gdstk glayout numpy; do
            local v
            if v="$("${VENV}/bin/python" -c "import importlib.metadata as m;print(m.version('${pkg}'))" 2>/dev/null)"; then
                ok "${pkg}" "${v}"
            else
                bad "${pkg}" "not importable in ${VENV}"
            fi
        done
    else
        bad "virtualenv" "not found at ${VENV} — run ./scripts/setup_env.sh"
        say ""
        say "  Skipping PDK and EDA checks: they run inside the environment."
        return 1
    fi

    # Everything below is reported by the resolver, so the shell and Python
    # can never disagree about which tool would actually be used.
    PDK_ROOT="${PDK_ROOT_EFF}" PDK="${PDK_NAME}" \
    PDKPATH="${PDKPATH:-${PDK_ROOT_EFF}/${PDK_NAME}}" \
    STD_CELL_LIBRARY="${STD_CELLS}" MBG_QUIET_TOOLS=1 \
    "${VENV}/bin/python" "${SCRIPT_DIR}/mbg_preflight.py"
    return $?
}

# ── main ──────────────────────────────────────────────────────────────
detect_distro
case "$MODE" in
    check)  do_check; rc=$?; exit $rc ;;
    python) do_python ;;
    pdk)    do_pdk ;;
    eda)    do_eda ;;
    deps)   do_deps ;;
    all)
        do_python
        do_pdk
        do_eda
        say ""
        say "${B}Next:${N}"
        say "  source scripts/activate_mbg.sh     # venv + PDK + tool PATH"
        say "  ./scripts/setup_env.sh --check     # verify"
        say "  python tests/test_all_designs.py   # end-to-end regression"
        ;;
esac
