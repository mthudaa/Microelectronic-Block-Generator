#!/usr/bin/env bash
# install.sh — install MBG. One script, six stages, no Docker, no root.
#
#   ./install.sh                 install everything (the usual case)
#   ./install.sh --check         verify every layer; installs nothing
#   ./install.sh --uninstall     remove shell + agent integration
#   ./install.sh --stage <name>  run one stage only
#   ./install.sh --list          show the stages
#   ./install.sh --deps [--yes]  print (or install) OS build prerequisites
#
# Stages, in dependency order:
#
#   python   .venv + pinned dependencies + `pip install -e .`
#   pdk      GF180MCU via volare
#   eda      Magic, netgen, KLayout — reused when already compatible
#   shell    ~/.mbg/activate.sh + one idempotent line in ~/.bashrc
#   agents   repo-scoped adapters + the Codex plugin        (optional)
#   global   /mbg-* skills for the whole user account       (optional)
#
# Everything it creates lives in three places you control:
#   <repo>/.venv                          the Python environment
#   $MBG_TOOLS_ROOT (~/.local/mbg-tools)  EDA builds
#   $MBG_HOME       (~/.mbg)              activation + launchers
# Nothing is written to /usr or the system package database unless you pass
# --deps --yes, which asks sudo for OS packages and nothing else.

set -uo pipefail

# ── locations (all derived, none hard-coded) ──────────────────────────
REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_DIR="${REPO_ROOT}/scripts"
VENV="${MBG_VENV:-${REPO_ROOT}/.venv}"
TOOLS_ROOT="${MBG_TOOLS_ROOT:-${HOME}/.local/mbg-tools}"
MBG_HOME="${MBG_HOME:-${HOME}/.mbg}"
PDK_ROOT_EFF="${PDK_ROOT:-${HOME}/.volare}"
PDK_NAME="${PDK:-gf180mcuD}"
STD_CELLS="${STD_CELL_LIBRARY:-gf180mcu_fd_sc_mcu7t5v0}"
ACTIVATE="$MBG_HOME/activate.sh"
MARKER="# >>> Microelectronic Block Generator >>>"
END_MARKER="# <<< Microelectronic Block Generator <<<"

# ── pinned versions ───────────────────────────────────────────────────
MAGIC_VERSION="${MBG_MAGIC_VERSION:-8.3.681}"
NETGEN_VERSION="${MBG_NETGEN_VERSION:-1.5.323}"
KLAYOUT_MIN="${MBG_KLAYOUT_MIN:-0.30.9}"
KLAYOUT_VERSION="${MBG_KLAYOUT_VERSION:-0.30.10}"
KLAYOUT_BASE="https://www.klayout.org/downloads"
MAGIC_REPO="https://github.com/RTimothyEdwards/magic.git"
NETGEN_REPO="https://github.com/RTimothyEdwards/netgen.git"
VOLARE_PDK_VERSION="${MBG_PDK_VERSION:-}"
PY_MIN="3.10"; PY_MAX_EXCL="3.13"

# ── output helpers (one set, was four) ────────────────────────────────
if [ -t 1 ]; then
    B=$'\033[1m'; G=$'\033[32m'; Y=$'\033[33m'; R=$'\033[31m'; C=$'\033[36m'; N=$'\033[0m'
else B=""; G=""; Y=""; R=""; C=""; N=""; fi
W=34
say()   { printf '%s\n' "$*"; }
head_() { printf '\n%s%s%s\n' "$B" "$*" "$N"; }
ok()    { printf '  %-*s %sOK%s   %s\n' "$W" "$1" "$G" "$N" "${2-}"; }
warn()  { printf '  %-*s %sWARN%s %s\n' "$W" "$1" "$Y" "$N" "${2-}"; WARNED=$((WARNED+1)); }
opt()   { printf '  %-*s %sOPTIONAL%s %s\n' "$W" "$1" "$C" "$N" "${2-}"; }
miss()  { printf '  %-*s %sMISSING%s %s\n' "$W" "$1" "$Y" "$N" "${2-}"; MISSING=$((MISSING+1)); }
bad()   { printf '  %-*s %sFAIL%s %s\n' "$W" "$1" "$R" "$N" "${2-}"; FAILED=$((FAILED+1)); }
die()   { printf '\n%sERROR%s %s\n' "$R" "$N" "$*" >&2; exit 1; }
FAILED=0; MISSING=0; WARNED=0; OPTIONAL_SKIPPED=0

usage() { awk 'NR<2{next} /^#/{sub(/^# ?/,""); print; next} {exit}' "$0"; }

# ── derived config the stage bodies rely on ───────────────────────────
PY="$(command -v python3 || command -v python || true)"
CLAUDE_SKILLS="${MBG_CLAUDE_HOME:-$HOME/.claude}/skills"
CLAUDE_CMDS="${MBG_CLAUDE_HOME:-$HOME/.claude}/commands"
OC_HOME="${MBG_OPENCODE_HOME:-${XDG_CONFIG_HOME:-$HOME/.config}/opencode}"
OC_SKILLS="$OC_HOME/skills"
OC_CMDS="$OC_HOME/commands"

# ── arguments (one parser, was five) ──────────────────────────────────
MODE="install"; ONLY=""; ASSUME_YES=0; LINK=1; WITH_VENV=0
while [ $# -gt 0 ]; do
    case "$1" in
        --check|--dry-run) MODE="check" ;;
        --uninstall)       MODE="uninstall" ;;
        --deps)            MODE="deps" ;;
        --yes|-y)          ASSUME_YES=1 ;;
        --copy)            LINK=0 ;;
        --with-venv)       WITH_VENV=1 ;;
        --list)            MODE="list" ;;
        --stage)           ONLY="${2:-}"; shift ;;
        --stage=*)         ONLY="${1#*=}" ;;
        --only)            ONLY="${2:-}"; shift ;;
        -h|--help)         usage; exit 0 ;;
        *) die "unknown option: $1  (try --help)" ;;
    esac
    shift
done

# ══════════════════════════════════════════════════════════════════════
#  stages: python / pdk / eda   (+ OS prerequisites)
# ══════════════════════════════════════════════════════════════════════
detect_distro() {
    if [ -r /etc/os-release ]; then
        # shellcheck disable=SC1091
        . /etc/os-release
        DISTRO_ID="${ID:-unknown}"
        DISTRO_LIKE="${ID_LIKE:-}"
        DISTRO_NAME="${PRETTY_NAME:-${NAME:-unknown}}"
        DISTRO_VERSION_ID="${VERSION_ID:-}"
    else
        DISTRO_ID="unknown"; DISTRO_LIKE=""; DISTRO_NAME="unknown"
        DISTRO_VERSION_ID=""
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
        say "  silently. Re-run with:  ./install.sh --deps --yes"
    fi
}

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
      MBG_PYTHON=/usr/bin/python3.11 ./install.sh"
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

pdk_present() { [ -f "${PDK_ROOT_EFF}/${PDK_NAME}/libs.tech/magic/${PDK_NAME}.tech" ]; }

do_pdk() {
    head_ "GF180MCU PDK"
    say "  PDK_ROOT : ${PDK_ROOT_EFF}"
    say "  PDK      : ${PDK_NAME}"
    if pdk_present; then
        ok "pdk" "already installed"
        return 0
    fi
    [ -x "${VENV}/bin/python" ] || die "create the Python environment first: ./install.sh --stage python"
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
  Run:  ./install.sh --deps        (prints the packages)
        ./install.sh --deps --yes  (installs them via sudo)"

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
                say "      and prefers any working install (./install.sh --check)"
                say "    - install Tcl 8.6 development files, then rebuild"
                say "    - use the optional Docker image, which ships working tools"
                say ""
                die "${name} ${version}: built, but not usable on this host. Log: ${src}/build.log"
            fi
            die "${name} ${version} built but does not work (see ${src}/build.log).
  This is usually a missing build dependency:
      ./install.sh --deps"
        fi
    fi
    ok "${name}" "${prefix}/bin/${name}"
}

klayout_package() {   # -> "<dir>|<file>|<kind>" for this distro, or empty
    local v="$KLAYOUT_VERSION" id="${DISTRO_ID}" like="${DISTRO_LIKE}"
    local ver="${DISTRO_VERSION_ID%%.*}"
    case "$id" in
        ubuntu) case "$ver" in 16|18|20|22|24|26)
                    echo "Ubuntu-$ver|klayout_${v}-1_amd64.deb|deb"; return ;;
                esac ;;
        debian) echo "Ubuntu-24|klayout_${v}-1_amd64.deb|deb"; return ;;
        rocky|almalinux|rhel|centos)
            case "$ver" in
                9) echo "RockyLinux_9|klayout-${v}-0.x86_64.rpm|rpm"; return ;;
                8) echo "CentOS_8|klayout-${v}-0.x86_64.rpm|rpm"; return ;;
                7) echo "CentOS_7|klayout-${v}-0.x86_64.rpm|rpm"; return ;;
            esac ;;
        opensuse*|sles) echo "openSUSE_Leap_15|klayout-${v}-0.x86_64.rpm|rpm"; return ;;
    esac
    case "$like" in *debian*) echo "Ubuntu-24|klayout_${v}-1_amd64.deb|deb"; return ;; esac
    echo ""
}

install_klayout() {
    local spec dir file kind url prefix tmp
    spec="$(klayout_package)"
    if [ -z "$spec" ]; then
        warn "klayout" "no upstream package for ${DISTRO_NAME}"
        say  "        klayout.org publishes builds for Ubuntu, CentOS, Rocky and"
        say  "        openSUSE only. On Fedora the EL9 build will NOT run: it needs"
        say  "        Python 3.9, Ruby 3.0 and Qt5 Multimedia, and the GF180 DRC deck"
        say  "        is Ruby, so a Ruby-less KLayout cannot run it at all."
        say  "        Options:"
        say  "          - build from source: ${KLAYOUT_BASE}/source/klayout-${KLAYOUT_VERSION}.tar.gz"
        say  "          - use an existing binary:  export MBG_KLAYOUT=/path/to/klayout"
        say  "            then re-run  ./install.sh --stage eda  to adopt it"
        return 1
    fi
    dir="${spec%%|*}"; spec="${spec#*|}"; file="${spec%%|*}"; kind="${spec##*|}"
    url="${KLAYOUT_BASE}/${dir}/${file}"
    prefix="$TOOLS_ROOT/klayout-$KLAYOUT_VERSION"
    [ "$MODE" = "check" ] && { say "  would install klayout from $url"; return 0; }

    command -v curl >/dev/null 2>&1 || { warn "klayout" "curl is required"; return 1; }
    say "  downloading klayout ${KLAYOUT_VERSION} for ${DISTRO_NAME}…"
    tmp="$(mktemp -d)"
    if ! curl -fsSL --retry 2 -o "$tmp/$file" "$url"; then
        warn "klayout" "download failed: $url"
        rm -rf "$tmp"; return 1
    fi
    mkdir -p "$prefix"
    case "$kind" in
        deb) command -v dpkg-deb >/dev/null 2>&1 \
                 && dpkg-deb -x "$tmp/$file" "$prefix" \
                 || { warn "klayout" "dpkg-deb not available to unpack the .deb"; rm -rf "$tmp"; return 1; } ;;
        rpm) command -v rpm2cpio >/dev/null 2>&1 \
                 && ( cd "$prefix" && rpm2cpio "$tmp/$file" | cpio -idm --quiet ) \
                 || { warn "klayout" "rpm2cpio/cpio not available to unpack the .rpm"; rm -rf "$tmp"; return 1; } ;;
    esac
    rm -rf "$tmp"

    local real; real="$(find "$prefix" -name klayout -type f -perm -u+x | head -1)"
    if [ -z "$real" ]; then
        warn "klayout" "package unpacked but no executable found"; return 1
    fi
    mkdir -p "$prefix/bin"
    [ "$real" = "$prefix/bin/klayout" ] || ln -sfn "$real" "$prefix/bin/klayout"
    # An unpacked package is not a working tool: confirm it actually starts on
    # this distribution before we let the resolver depend on it.
    if ! "$prefix/bin/klayout" -v >/dev/null 2>&1; then
        warn "klayout" "unpacked but will not run on ${DISTRO_NAME}:"
        ldd "$real" 2>/dev/null | grep "not found" | head -4 | sed 's/^/          /'
        return 1
    fi
    ok "klayout" "$KLAYOUT_VERSION installed at $prefix/bin/klayout"
    return 0
}

adopt_klayout() {
    local found="" c ver prefix
    for c in "${MBG_KLAYOUT:-}" "$(command -v klayout 2>/dev/null || true)" \
             "$TOOLS_ROOT"/klayout-*/bin/klayout /nix/store/*klayout*/bin/klayout; do
        [ -n "$c" ] && [ -x "$c" ] && { found="$c"; break; }
    done

    if [ -z "$found" ]; then
        install_klayout || true
        for c in "$TOOLS_ROOT"/klayout-*/bin/klayout; do
            [ -x "$c" ] && { found="$c"; break; }
        done
    fi
    if [ -z "$found" ]; then
        warn "klayout" "not found — DRC sign-off will report CONFIGURATION_FAILURE"
        return 0
    fi

    ver="$("$found" -v 2>&1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)"
    [ -n "$ver" ] || ver="unknown"
    if [ "$ver" != "unknown" ] \
       && [ "$(printf '%s\n%s\n' "$KLAYOUT_MIN" "$ver" | sort -V | head -1)" != "$KLAYOUT_MIN" ]; then
        warn "klayout" "$ver is older than $KLAYOUT_MIN (GF180 deck / KLayout issue #2339)"
        return 0
    fi

    prefix="$TOOLS_ROOT/klayout-$ver"
    if [ "$MODE" = "check" ]; then
        ok "klayout" "$found ($ver)"
        return 0
    fi
    mkdir -p "$prefix/bin"
    # Resolve to the REAL binary before linking. The discovery loop above
    # searches $TOOLS_ROOT first, so on a second run it finds the symlink we
    # made last time — and linking that to itself produces a self-referential
    # link that silently un-installs KLayout. Re-running an installer must
    # never break what the previous run set up.
    local target; target="$(readlink -f "$found")"
    if [ -z "$target" ] || [ ! -x "$target" ]; then
        warn "klayout" "could not resolve $found to a real executable"
        return 0
    fi
    if [ "$target" != "$(readlink -f "$prefix/bin/klayout" 2>/dev/null || true)" ]; then
        ln -sfn "$target" "$prefix/bin/klayout"
    fi

    # Protect a nix-store binary from garbage collection.
    case "$target" in
        /nix/store/*)
            if command -v nix-store >/dev/null 2>&1; then
                local store="${target%/bin/klayout}"
                if nix-store --add-root "$prefix/.gcroot" --indirect -r "$store" \
                        >/dev/null 2>&1; then
                    ok "klayout" "$ver adopted, GC root created"
                else
                    warn "klayout" "$ver adopted, but no GC root — "
                    say  "        nix-collect-garbage could delete $store"
                fi
            fi ;;
        *) ok "klayout" "$ver adopted at $prefix/bin/klayout" ;;
    esac
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
    adopt_klayout
    local jobs; jobs="$(nproc 2>/dev/null || echo 2)"
    [ "$need_magic" -eq 1 ]  && build_tool magic  "$MAGIC_REPO"  "$MAGIC_VERSION" "$jobs"
    # netgen is built with one job on purpose: its Makefile races under -j
    # ("No rule to make target '../base/libbase.o', needed by 'tclnetgen.so'"),
    # which produces a launcher script with no Tcl library behind it.
    [ "$need_netgen" -eq 1 ] && build_tool netgen "$NETGEN_REPO" "$NETGEN_VERSION" 1
    return 0
}

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
        bad "virtualenv" "not found at ${VENV} — run ./install.sh"
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

# ══════════════════════════════════════════════════════════════════════
#  stage: shell   — ~/.mbg/activate.sh, launchers, one .bashrc line
# ══════════════════════════════════════════════════════════════════════
rc_files() {
    local out=()
    [ -f "$HOME/.bashrc" ] || [ "${SHELL##*/}" = "bash" ] && out+=("$HOME/.bashrc")
    [ -f "$HOME/.zshrc" ] && out+=("$HOME/.zshrc")
    printf '%s\n' "${out[@]}"
}

find_klayout() {
    if [ -n "${MBG_KLAYOUT:-}" ] && [ -x "${MBG_KLAYOUT}" ]; then
        printf '%s' "$MBG_KLAYOUT"; return
    fi
    command -v klayout >/dev/null 2>&1 && { command -v klayout; return; }
    local c
    for c in "$TOOLS_ROOT"/klayout-*/bin/klayout /nix/store/*klayout*/bin/klayout; do
        [ -x "$c" ] && { printf '%s' "$c"; return; }
    done
    printf ''
}

find_tool() {   # name
    local n="$1" c
    for c in "$TOOLS_ROOT"/"$n"-*/bin/"$n"; do
        [ -x "$c" ] && { printf '%s' "$c"; return; }
    done
    command -v "$n" >/dev/null 2>&1 && { command -v "$n"; return; }
    printf ''
}

do_shell() {
# ── uninstall ─────────────────────────────────────────────────────────
if [ "$MODE" = "uninstall" ]; then
    while read -r rc; do
        [ -n "$rc" ] && [ -f "$rc" ] || continue
        if grep -qF "$MARKER" "$rc"; then
            # delete only our own block, never anything else
            sed -i "/${MARKER}/,/${END_MARKER}/d" "$rc"
            printf '%s\n' "$(sed -e :a -e '/^\n*$/{$d;N;};/\n$/ba' "$rc")" > "$rc.mbgtmp" \
                && mv "$rc.mbgtmp" "$rc"
            ok "$(basename "$rc")" "MBG block removed"
        fi
    done < <(rc_files)
    [ -f "$ACTIVATE" ] && rm -f "$ACTIVATE" && ok "activate.sh" "removed"
    printf '\n%sRemoved.%s Your other shell configuration is untouched.\n' "$G" "$N"
    return 0
fi

# ── discover what to record ───────────────────────────────────────────
PDK_ROOT_EFF="${PDK_ROOT:-$HOME/.volare}"
PDK_NAME="${PDK:-gf180mcuD}"
TOOLS_ROOT="${MBG_TOOLS_ROOT:-$HOME/.local/mbg-tools}"
VENV="${MBG_VENV:-$REPO_ROOT/.venv}"

# KLayout is required for DRC sign-off and is frequently not on PATH
# (no Fedora package; nix store installs live outside PATH). Record whatever
# we can find so the user never has to remember the path.
find_klayout() {
    if [ -n "${MBG_KLAYOUT:-}" ] && [ -x "${MBG_KLAYOUT}" ]; then
        printf '%s' "$MBG_KLAYOUT"; return
    fi
    command -v klayout >/dev/null 2>&1 && { command -v klayout; return; }
    local c
    for c in "$TOOLS_ROOT"/klayout-*/bin/klayout /nix/store/*klayout*/bin/klayout; do
        [ -x "$c" ] && { printf '%s' "$c"; return; }
    done
    printf ''
}
KLAYOUT_BIN="$(find_klayout || true)"

# Same treatment for Magic and netgen. Relying on PATH order means a shell
# with a different PATH (a cron job, a stripped environment, another tool
# prepending its own bin) silently resolves a different binary — or none.
# Pin whatever the resolver validated.
find_tool() {   # name
    local n="$1" c
    for c in "$TOOLS_ROOT"/"$n"-*/bin/"$n"; do
        [ -x "$c" ] && { printf '%s' "$c"; return; }
    done
    command -v "$n" >/dev/null 2>&1 && { command -v "$n"; return; }
    printf ''
}
MAGIC_BIN="$(find_tool magic || true)"
NETGEN_BIN="$(find_tool netgen || true)"
NGSPICE_BIN="$(find_tool ngspice || true)"

if [ "$MODE" = "check" ]; then
    printf '%sMBG shell integration%s\n\n' "$B" "$N"
    [ -f "$ACTIVATE" ] && ok "activate.sh" "$ACTIVATE" || warn "activate.sh" "not installed"
    local rcfile n
    while read -r rcfile; do
        [ -n "$rcfile" ] && [ -f "$rcfile" ] || continue
        n=$(grep -cF "$MARKER" "$rcfile" || true)
        case "$n" in
            0) warn "$(basename "$rcfile")" "no MBG line" ;;
            1) ok "$(basename "$rcfile")" "1 MBG block (idempotent)" ;;
            *) warn "$(basename "$rcfile")" "$n MBG blocks — duplicated!" ;;
        esac
    done < <(rc_files)
    [ -n "$KLAYOUT_BIN" ] && ok "klayout" "$KLAYOUT_BIN" || warn "klayout" "not found — DRC sign-off will report CONFIGURATION_FAILURE"
    return 0
fi

# ── generate the activation script ────────────────────────────────────
mkdir -p "$MBG_HOME" "$MBG_HOME/bin"
cat > "$ACTIVATE" <<EOF
# Generated by ./install.sh --stage shell — re-run it to refresh.
# Edit MBG_* values in your own rc file BEFORE the source line to override;
# every assignment below defers to a value you already set.

export MBG_HOME="\${MBG_HOME:-$MBG_HOME}"
export MBG_ROOT="\${MBG_ROOT:-$REPO_ROOT}"

# --- GF180 PDK ---------------------------------------------------------
export PDK_ROOT="\${PDK_ROOT:-$PDK_ROOT_EFF}"
export PDK="\${PDK:-$PDK_NAME}"
export PDKPATH="\${PDKPATH:-\$PDK_ROOT/\$PDK}"
export STD_CELL_LIBRARY="\${STD_CELL_LIBRARY:-gf180mcu_fd_sc_mcu7t5v0}"

# --- EDA tools ---------------------------------------------------------
export MBG_TOOLS_ROOT="\${MBG_TOOLS_ROOT:-$TOOLS_ROOT}"
EOF

if [ -n "$KLAYOUT_BIN" ]; then
    cat >> "$ACTIVATE" <<EOF
# KLayout is required for DRC sign-off (GF180 foundry deck) and is often not
# on PATH, so the resolved binary is pinned here.
export MBG_KLAYOUT="\${MBG_KLAYOUT:-$KLAYOUT_BIN}"
EOF
fi
[ -n "$MAGIC_BIN" ] && printf 'export MBG_MAGIC="${MBG_MAGIC:-%s}"\n' "$MAGIC_BIN" >> "$ACTIVATE"
[ -n "$NETGEN_BIN" ] && printf 'export MBG_NETGEN="${MBG_NETGEN:-%s}"\n' "$NETGEN_BIN" >> "$ACTIVATE"
[ -n "$NGSPICE_BIN" ] && printf 'export MBG_NGSPICE="${MBG_NGSPICE:-%s}"\n' "$NGSPICE_BIN" >> "$ACTIVATE"

cat >> "$ACTIVATE" <<'EOF'

if [ -d "$MBG_TOOLS_ROOT" ]; then
    for _t in "$MBG_TOOLS_ROOT"/magic-* "$MBG_TOOLS_ROOT"/netgen-*; do
        [ -d "$_t/bin" ] || continue
        case ":$PATH:" in *":$_t/bin:"*) ;; *) PATH="$_t/bin:$PATH" ;; esac
        case "$(basename "$_t")" in
            magic-*)  export MBG_MAGIC_ROOT="$_t" ;;
            netgen-*) export MBG_NETGEN_ROOT="$_t" ;;
        esac
    done
    unset _t
    export PATH
fi

# --- MBG launchers -----------------------------------------------------
case ":$PATH:" in *":$MBG_HOME/bin:"*) ;; *) PATH="$MBG_HOME/bin:$PATH" ;; esac
export PATH
EOF

if [ "$WITH_VENV" -eq 1 ]; then
    cat >> "$ACTIVATE" <<EOF

# --- Python environment (--with-venv) ----------------------------------
# NOTE: this makes \`python\` and \`pip\` refer to MBG's environment in EVERY
# shell, including ones you open for other projects.
if [ -f "$VENV/bin/activate" ] && [ -z "\${VIRTUAL_ENV:-}" ]; then
    . "$VENV/bin/activate"
fi
EOF
else
    cat >> "$ACTIVATE" <<EOF

# The virtualenv is deliberately NOT activated here — that would change what
# \`python\` and \`pip\` mean for every other project. Use the launchers in
# \$MBG_HOME/bin, or re-run: ./install.sh --stage shell --with-venv
export MBG_VENV="\${MBG_VENV:-$VENV}"
EOF
fi

# ── launchers ─────────────────────────────────────────────────────────
cat > "$MBG_HOME/bin/mbg-python" <<EOF
#!/usr/bin/env bash
# MBG's interpreter, without putting it on PATH as bare \`python\`.
exec "\${MBG_VENV:-$VENV}/bin/python" "\$@"
EOF
cat > "$MBG_HOME/bin/mbg" <<'EOF'
#!/usr/bin/env bash
# Minimal MBG launcher. Subcommands are delegated to the repo scripts that
# implement them; `mbg check` is the environment preflight.
set -euo pipefail
PY="${MBG_VENV:?MBG_VENV not set — source ~/.mbg/activate.sh}/bin/python"
ROOT="${MBG_ROOT:?MBG_ROOT not set}"
case "${1-}" in
    check|"")   exec "$ROOT/install.sh" --check ;;
    version|--version) exec "$PY" -c "import importlib.metadata as m;print('mbg', m.version('mbg'))" ;;
    python)     shift; exec "$PY" "$@" ;;
    shell)      exec "$PY" ;;
    -h|--help|help)
        cat <<'USAGE'
mbg — Microelectronic Block Generator

  mbg check       environment preflight (Python, PDK, Magic, netgen, KLayout)
  mbg version     installed package version
  mbg python ...  run a script with MBG's interpreter
  mbg shell       interactive Python with MBG importable

Design flows are driven from the agent slash commands (/mbg-full-auto) or
from Python; see the README.
USAGE
        ;;
    *) echo "mbg: unknown subcommand '$1' (try: mbg --help)" >&2; exit 2 ;;
esac
EOF
chmod +x "$MBG_HOME/bin/mbg" "$MBG_HOME/bin/mbg-python"

# ── one idempotent rc line ────────────────────────────────────────────
BLOCK="$MARKER
[ -f \"\$HOME/.mbg/activate.sh\" ] && . \"\$HOME/.mbg/activate.sh\"
$END_MARKER"

while read -r rc; do
    [ -n "$rc" ] || continue
    [ -f "$rc" ] || touch "$rc"
    had_block=0
    grep -qF "$MARKER" "$rc" && had_block=1
    # Drop any existing block, then trim trailing blank lines before
    # appending. Without the trim, an uninstall/reinstall cycle leaves its
    # separator behind and the file grows a blank line every round.
    [ "$had_block" -eq 1 ] && sed -i "/${MARKER}/,/${END_MARKER}/d" "$rc"
    printf '%s\n' "$(sed -e :a -e '/^\n*$/{$d;N;};/\n$/ba' "$rc")" > "$rc.mbgtmp" \
        && mv "$rc.mbgtmp" "$rc"
    printf '\n%s\n' "$BLOCK" >> "$rc"
    if [ "$had_block" -eq 1 ]; then
        ok "$(basename "$rc")" "MBG block refreshed (still exactly one)"
    else
        ok "$(basename "$rc")" "MBG block added"
    fi
done < <(rc_files)

ok "activate.sh" "$ACTIVATE"
ok "launchers" "$MBG_HOME/bin/{mbg,mbg-python}"
for _pair in "magic:$MAGIC_BIN" "netgen:$NETGEN_BIN" "klayout:$KLAYOUT_BIN" \
             "ngspice:$NGSPICE_BIN"; do
    _n="${_pair%%:*}"; _v="${_pair#*:}"
    if [ -n "$_v" ]; then ok "$_n pinned" "$_v"
    elif [ "$_n" = "klayout" ]; then
        warn "klayout" "not found — DRC sign-off will report CONFIGURATION_FAILURE"
    elif [ "$_n" = "ngspice" ]; then
        warn "ngspice" "not found — simulation unavailable (optional)"
    else
        warn "$_n" "not found — required for verification"
    fi
done

printf '\n%sDone.%s Open a new shell, or: source "%s"\n' "$G" "$N" "$ACTIVATE"
printf 'Verify with: ./install.sh --check --stage shell\n'
}

# ══════════════════════════════════════════════════════════════════════
#  stage: agents  — repo adapters + Codex plugin
# ══════════════════════════════════════════════════════════════════════
want() { [ "$ONLY" = "all" ] || [ "$ONLY" = "$1" ]; }
confirm() {
    [ "$ASSUME_YES" = "1" ] && return 0
    [ ! -t 0 ] && return 1
    printf '  %s [y/N] ' "$1"
    read -r reply
    case "$reply" in [yY]*) return 0 ;; *) return 1 ;; esac
}

do_agents() {
    # The former per-platform installer used --only for a platform; here
    # stage, so inside this function "all platforms" is the only meaning.
    local ONLY="all"
    [ -n "$PY" ] || { warn "agents" "python3 not found — cannot generate adapters"; return 1; }
    [ -f "$REPO_ROOT/.ai/manifest.json" ] || {
        warn "agents" "no .ai/manifest.json — not a full checkout"; return 1; }
    cd "$REPO_ROOT" || return 1
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

# Codex COPIES the plugin into its own cache at install time, so a sync that
# updates plugins/<name>/skills/ never reaches it. Nothing else notices: the
# plugin still lists as "installed", so a check that only asks whether it is
# installed will report ready while the agent runs last week's instructions.
# Compare the cached skills against the generated ones instead.
codex_cache_root() {
    local base="${CODEX_HOME:-$HOME/.codex}/plugins/cache/$MARKET_NAME/$PLUGIN_NAME"
    [ -d "$base" ] || return 1
    # the version directory is whatever Codex last installed
    local d
    d="$(find "$base" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | sort | tail -1)"
    [ -n "$d" ] || return 1
    printf '%s\n' "$d"
}

# echoes the number of stale/missing skills; 0 means the cache is current
codex_cache_stale_count() {
    local cache src n=0 rel
    cache="$(codex_cache_root)" || { printf '%s\n' "-1"; return; }
    src="$REPO_ROOT/plugins/$PLUGIN_NAME/skills"
    [ -d "$src" ] || { printf '%s\n' "-1"; return; }
    while IFS= read -r f; do
        rel="${f#"$src"/}"
        cmp -s "$f" "$cache/skills/$rel" || n=$((n+1))
    done < <(find "$src" -name SKILL.md 2>/dev/null)
    printf '%s\n' "$n"
}

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
    return 0
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
        return 1
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
                STALE="$(codex_cache_stale_count)"
                if [ "$STALE" = "0" ]; then
                    ok "cached plugin matches the current adapters"
                    STATUS_CODEX="ready"
                elif [ "$STALE" = "-1" ]; then
                    warn "cannot locate the Codex plugin cache — refresh with: ./install.sh --stage agents"
                    STATUS_CODEX="unknown"
                else
                    warn "cached plugin is STALE ($STALE skill(s) differ) — Codex is running old instructions. Refresh: ./install.sh --stage agents"
                    STATUS_CODEX="stale"
                fi
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
                STALE="$(codex_cache_stale_count)"
                if [ "$STALE" = "0" ]; then
                    ok "plugin refreshed from the current adapters ($N_SKILLS skills)"
                    STATUS_CODEX="ready"
                else
                    warn "plugin re-added but the cache still differs ($STALE skill(s)) — check: codex plugin add $PLUGIN_NAME@$MARKET_NAME"
                    STATUS_CODEX="stale"
                fi
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
                warn "skipped — register later with: ./install.sh --stage agents"
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
echo "  Check status without changing anything:     ./install.sh --check --stage agents"
return $VALID
}

# ══════════════════════════════════════════════════════════════════════
#  stage: global  — /mbg-* for the whole user account
# ══════════════════════════════════════════════════════════════════════
is_ours() {  # path
    case "$(basename "$1")" in mbg-*) return 0 ;; *) return 1 ;; esac
}

link_one() {  # src dest
    local src="$1" dest="$2" name; name="$(basename "$dest")"
    if [ "$MODE" = "check" ]; then
        if [ -L "$dest" ]; then
            if [ "$(readlink -f "$dest")" = "$(readlink -f "$src")" ]; then
                ok "$name" "-> repo"
            else
                bad "$name" "symlink points elsewhere: $(readlink "$dest")"
            fi
        elif [ -e "$dest" ]; then
            miss "$name" "present but not linked to the repo (stale copy?)"
        else
            miss "$name" "not installed"
        fi
        return 0
    fi
    if [ -e "$dest" ] || [ -L "$dest" ]; then
        if [ -L "$dest" ] || is_ours "$dest"; then
            rm -rf -- "$dest"
        else
            bad "$name" "refusing to overwrite an unrelated entry"
            return 0
        fi
    fi
    mkdir -p -- "$(dirname "$dest")"
    if [ "$LINK" -eq 1 ]; then
        ln -s -- "$src" "$dest"
        ok "$name" "-> $src"
    else
        cp -r -- "$src" "$dest"
        ok "$name" "copied (will go stale; re-run after a sync)"
    fi
}

remove_one() {  # dest
    local dest="$1" name; name="$(basename "$dest")"
    is_ours "$dest" || return 0
    if [ -L "$dest" ] || [ -e "$dest" ]; then
        [ "$MODE" = "check" ] || rm -rf -- "$dest"
        ok "$name" "removed"
    fi
}

install_platform() {  # label repo_skills repo_cmds dest_skills dest_cmds
    local label="$1" rs="$2" rc="$3" ds="$4" dc="$5"
    printf '\n%s%s%s\n' "$B" "$label" "$N"
    printf '  skills   -> %s\n  commands -> %s\n' "$ds" "$dc"
    [ "$MODE" = "check" ] || mkdir -p -- "$ds" "$dc"

    local n=0
    for d in "$rs"/mbg-*; do
        [ -d "$d" ] || continue
        if [ "$MODE" = "uninstall" ]; then remove_one "$ds/$(basename "$d")"
        else link_one "$d" "$ds/$(basename "$d")"; fi
        n=$((n+1))
    done
    for f in "$rc"/mbg-*.md; do
        [ -f "$f" ] || continue
        if [ "$MODE" = "uninstall" ]; then remove_one "$dc/$(basename "$f")"
        else link_one "$f" "$dc/$(basename "$f")"; fi
        n=$((n+1))
    done
    [ "$n" -gt 0 ] || bad "$label" "nothing found under $rs — run scripts/sync_agent_tools.py first"
}

do_global() {

# Only ever manage our own entries.
is_ours() {  # path
    case "$(basename "$1")" in mbg-*) return 0 ;; *) return 1 ;; esac
}

# Safe to replace only if we made it: a symlink into this repo, or (for
# --copy re-installs) a directory we previously wrote. Never clobber a real
# directory that is not ours.
link_one() {  # src dest
    local src="$1" dest="$2" name; name="$(basename "$dest")"
    if [ "$MODE" = "check" ]; then
        if [ -L "$dest" ]; then
            if [ "$(readlink -f "$dest")" = "$(readlink -f "$src")" ]; then
                ok "$name" "-> repo"
            else
                bad "$name" "symlink points elsewhere: $(readlink "$dest")"
            fi
        elif [ -e "$dest" ]; then
            miss "$name" "present but not linked to the repo (stale copy?)"
        else
            miss "$name" "not installed"
        fi
        return 0
    fi
    if [ -e "$dest" ] || [ -L "$dest" ]; then
        if [ -L "$dest" ] || is_ours "$dest"; then
            rm -rf -- "$dest"
        else
            bad "$name" "refusing to overwrite an unrelated entry"
            return 0
        fi
    fi
    mkdir -p -- "$(dirname "$dest")"
    if [ "$LINK" -eq 1 ]; then
        ln -s -- "$src" "$dest"
        ok "$name" "-> $src"
    else
        cp -r -- "$src" "$dest"
        ok "$name" "copied (will go stale; re-run after a sync)"
    fi
}

remove_one() {  # dest
    local dest="$1" name; name="$(basename "$dest")"
    is_ours "$dest" || return 0
    if [ -L "$dest" ] || [ -e "$dest" ]; then
        [ "$MODE" = "check" ] || rm -rf -- "$dest"
        ok "$name" "removed"
    fi
}

install_platform() {  # label repo_skills repo_cmds dest_skills dest_cmds
    local label="$1" rs="$2" rc="$3" ds="$4" dc="$5"
    printf '\n%s%s%s\n' "$B" "$label" "$N"
    printf '  skills   -> %s\n  commands -> %s\n' "$ds" "$dc"
    [ "$MODE" = "check" ] || mkdir -p -- "$ds" "$dc"

    local n=0
    for d in "$rs"/mbg-*; do
        [ -d "$d" ] || continue
        if [ "$MODE" = "uninstall" ]; then remove_one "$ds/$(basename "$d")"
        else link_one "$d" "$ds/$(basename "$d")"; fi
        n=$((n+1))
    done
    for f in "$rc"/mbg-*.md; do
        [ -f "$f" ] || continue
        if [ "$MODE" = "uninstall" ]; then remove_one "$dc/$(basename "$f")"
        else link_one "$f" "$dc/$(basename "$f")"; fi
        n=$((n+1))
    done
    [ "$n" -gt 0 ] || bad "$label" "nothing found under $rs — run scripts/sync_agent_tools.py first"
}

printf '%sMBG global agent installation%s\n' "$B" "$N"
printf 'repository: %s\n' "$REPO_ROOT"
[ "$LINK" -eq 1 ] && printf 'method: symlink (stays in sync with the repo)\n' \
                  || printf 'method: copy (snapshot — re-run after each sync)\n'

install_platform "Claude Code" \
    "$REPO_ROOT/.claude/skills" "$REPO_ROOT/.claude/commands" \
    "$CLAUDE_SKILLS" "$CLAUDE_CMDS"

install_platform "OpenCode" \
    "$REPO_ROOT/.opencode/skills" "$REPO_ROOT/.opencode/commands" \
    "$OC_SKILLS" "$OC_CMDS"

printf '\n%sCodex%s\n' "$B" "$N"
if command -v codex >/dev/null 2>&1; then
    printf '  Codex has no user-level skill directory; it loads a plugin.\n'
    printf '  Register it with:  ./install.sh --stage agents\n'
else
    printf '  codex CLI not found — skipping.\n'
fi

printf '\n'
if [ "$MODE" = "check" ]; then
    if [ "$FAILED" -gt 0 ] || [ "$MISSING" -gt 0 ]; then
        printf '%s%d not installed, %d problem(s).%s Run ./install.sh --stage global\n' \
            "$Y" "$MISSING" "$FAILED" "$N"
        return 1
    fi
    printf '%sGlobal installation is consistent with the repository.%s\n' "$G" "$N"
    return 0
fi
if [ "$MODE" = "uninstall" ]; then
    printf '%sRemoved the MBG entries. Nothing else was touched.%s\n' "$G" "$N"
    return 0
fi
printf '%sInstalled.%s /mbg-* is now available outside the repository.\n' "$G" "$N"
printf 'Verify with: ./install.sh --check --stage global\n'
}

# ══════════════════════════════════════════════════════════════════════
#  dispatcher
# ══════════════════════════════════════════════════════════════════════
list_stages() {
    head_ "Stages"
    printf '  %-8s %s\n' python "venv + pinned dependencies + editable install"
    printf '  %-8s %s\n' pdk    "GF180MCU via volare"
    printf '  %-8s %s\n' eda    "Magic, netgen, KLayout (reused when compatible)"
    printf '  %-8s %s\n' shell  "~/.mbg/activate.sh + one line in ~/.bashrc"
    printf '  %-8s %s\n' agents "repo adapters + Codex plugin   (optional)"
    printf '  %-8s %s\n' global "/mbg-* for the user account    (optional)"
}

wanted() { [ -z "$ONLY" ] || [ "$ONLY" = "$1" ]; }

run_optional() {   # name fn
    local name="$1" f="$2"
    wanted "$name" || return 0
    "$f"
    local rc=$?
    [ $rc -eq 0 ] || { OPTIONAL_SKIPPED=$((OPTIONAL_SKIPPED+1))
        warn "$name" "optional stage did not complete (exit $rc)"; }
    return 0
}

detect_distro

case "$MODE" in
    list) list_stages; exit 0 ;;
    deps) do_deps; exit 0 ;;
esac

if [ -n "$ONLY" ]; then
    case "$ONLY" in
        python|pdk|eda|shell|agents|global) ;;
        *) printf '%sunknown stage: %s%s\n' "$R" "$ONLY" "$N" >&2; list_stages >&2; exit 2 ;;
    esac
fi

printf '%sMBG installation%s  (%s)\n' "$B" "$N" "$MODE"
printf 'repository: %s\n' "$REPO_ROOT"

if [ "$MODE" = "check" ]; then
    # One report for the whole environment; the per-stage checks below would
    # otherwise repeat it three times.
    do_check; CHECK_RC=$?
    wanted shell  && { head_ "Shell integration"; do_shell; }
    wanted agents && { head_ "Agent integration"; do_agents; }
    wanted global && { head_ "Global /mbg-*";     do_global; }
    exit "$CHECK_RC"
fi

if [ "$MODE" = "uninstall" ]; then
    # The venv, PDK and built tools are deliberately left alone: they cost
    # hours to rebuild, so removing them stays a deliberate manual act.
    wanted shell  && do_shell
    wanted agents && do_agents
    wanted global && do_global
    say ""
    printf '%sShell and agent integration removed.%s\n' "$G" "$N"
    say "The venv, PDK and built tools were kept — delete them yourself if you mean to."
    exit 0
fi

wanted python && do_python
wanted pdk    && do_pdk
wanted eda    && do_eda
wanted shell  && { head_ "Shell integration"; do_shell; }
run_optional agents do_agents
run_optional global do_global

say ""
if [ "$FAILED" -gt 0 ]; then
    printf '%s%d required item(s) failed.%s\n' "$R" "$FAILED" "$N"
    exit 1
fi
[ "$OPTIONAL_SKIPPED" -gt 0 ] && \
    printf '%s%d optional stage(s) incomplete%s — MBG itself is usable.\n' \
        "$Y" "$OPTIONAL_SKIPPED" "$N"
printf '%sInstalled.%s Open a new shell, then:  mbg check\n' "$G" "$N"
