#!/bin/bash
# ============================================================
# MBG Full Environment Setup
# Installs ngspice, Magic VLSI, netgen, PDK, and Python deps.
# Usage: bash setup/install_all.sh
# ============================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MBG_DIR="$(dirname "$SCRIPT_DIR")"
LOG_FILE="/tmp/mbg_install_$(date +%Y%m%d_%H%M%S).log"

echo "============================================"
echo "  MBG — Full Environment Setup"
echo "============================================"
echo "  Log: $LOG_FILE"
echo "  Dir: $MBG_DIR"
echo "============================================"

# ── Detect OS ──────────────────────────────────────────
OS="$(uname -s)"
DISTRO=""
if [ "$OS" = "Linux" ]; then
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        DISTRO="$ID"
    elif [ -f /etc/debian_version ]; then
        DISTRO="debian"
    elif [ -f /etc/redhat-release ]; then
        DISTRO="rhel"
    fi
elif [ "$OS" = "Darwin" ]; then
    DISTRO="macos"
fi
echo "[INFO] OS: $OS, Distro: $DISTRO"

# ── Step 1: System Dependencies ────────────────────────
echo ""
echo "--- Step 1/6: System Dependencies ---"

install_system_deps() {
    case "$DISTRO" in
        ubuntu|debian)
            sudo apt-get update -qq
            sudo apt-get install -y -qq \
                build-essential python3 python3-pip python3-venv \
                git wget curl tcsh xvfb \
                libx11-dev libxft-dev libxrender-dev libxpm-dev \
                libxt-dev libsm-dev libice-dev \
                libgl1-mesa-dev libglu1-mesa-dev \
                libcairo2-dev libpango1.0-dev \
                libreadline-dev \
                tcl8.6-dev tk8.6-dev \
                libfftw3-dev libncurses-dev \
                || echo "[WARN] Some packages may have failed"
            ;;
        rhel|fedora|centos)
            sudo yum groupinstall -y "Development Tools"
            sudo yum install -y \
                python3 python3-pip git wget curl tcsh \
                libX11-devel libXft-devel libXrender-devel libXpm-devel \
                libXt-devel libSM-devel libICE-devel \
                mesa-libGL-devel mesa-libGLU-devel \
                cairo-devel pango-devel \
                readline-devel \
                tcl-devel tk-devel \
                fftw-devel ncurses-devel \
                || echo "[WARN] Some packages may have failed"
            ;;
        macos)
            if command -v brew &>/dev/null; then
                brew install python3 git wget curl \
                    libx11 libxft libxrender libxpm \
                    cairo pango readline tcl-tk \
                    fftw ncurses
            else
                echo "[ERROR] Homebrew not found. Install from https://brew.sh"
                exit 1
            fi
            ;;
        *)
            echo "[WARN] Unknown distro. Install build tools manually."
            ;;
    esac
}
install_system_deps 2>&1 | tee -a "$LOG_FILE"

# ── Step 2: Python Dependencies ────────────────────────
echo ""
echo "--- Step 2/6: Python Dependencies ---"

install_python_deps() {
    pip3 install --upgrade pip setuptools wheel 2>&1 | tee -a "$LOG_FILE"
    pip3 install numpy gdsfactory gdstk 2>&1 | tee -a "$LOG_FILE"
    pip3 install glayout@git+https://github.com/ReaLLMASIC/gLayout.git --no-deps 2>&1 | tee -a "$LOG_FILE"
}
install_python_deps

# ── Step 3: Install ngspice ────────────────────────────
echo ""
echo "--- Step 3/6: ngspice ---"

install_ngspice() {
    if command -v ngspice &>/dev/null; then
        echo "[SKIP] ngspice already installed: $(which ngspice)"
        ngspice --version 2>&1 | head -1
        return
    fi

    echo "[INFO] Building ngspice from source..."
    cd /tmp
    rm -rf ngspice-ngspice
    git clone --depth=1 https://git.code.sf.net/p/ngspice/ngspice ngspice-ngspice 2>&1 | tail -1
    cd ngspice-ngspice
    ./autogen.sh 2>&1 | tail -3
    mkdir -p release && cd release
    ../configure --quiet --enable-openmp --enable-xspice --enable-cider \
                 --with-readline=yes --disable-debug 2>&1 | tail -5
    make -j$(nproc) 2>&1 | tail -5
    sudo make install 2>&1 | tail -3
    echo "[OK] ngspice installed: $(which ngspice)"
}
install_ngspice 2>&1 | tee -a "$LOG_FILE"

# ── Step 4: Install Magic VLSI ─────────────────────────
echo ""
echo "--- Step 4/6: Magic VLSI ---"

install_magic() {
    if command -v magic &>/dev/null; then
        echo "[SKIP] Magic already installed: $(which magic)"
        magic --version 2>&1 | head -1
        return
    fi

    echo "[INFO] Building Magic VLSI from source..."
    cd /tmp
    rm -rf magic
    git clone --depth=1 https://github.com/RTimothyEdwards/magic.git 2>&1 | tail -1
    cd magic
    ./configure --quiet 2>&1 | tail -5
    make -j$(nproc) 2>&1 | tail -5
    sudo make install 2>&1 | tail -3
    echo "[OK] Magic installed: $(which magic)"
}
install_magic 2>&1 | tee -a "$LOG_FILE"

# ── Step 5: Install netgen ────────────────────────────
echo ""
echo "--- Step 5/6: netgen ---"

install_netgen() {
    if command -v netgen &>/dev/null; then
        echo "[SKIP] netgen already installed: $(which netgen)"
        netgen -version 2>&1 | head -1
        return
    fi

    echo "[INFO] Building netgen from source..."
    cd /tmp
    rm -rf netgen
    git clone --depth=1 https://github.com/RTimothyEdwards/netgen.git 2>&1 | tail -1
    cd netgen
    ./configure --quiet 2>&1 | tail -5
    make -j$(nproc) 2>&1 | tail -5
    sudo make install 2>&1 | tail -3
    echo "[OK] netgen installed: $(which netgen)"
}
install_netgen 2>&1 | tee -a "$LOG_FILE"

# ── Step 6: PDK Setup (GF180MCU via volare) ───────────
echo ""
echo "--- Step 6/6: PDK Setup ---"

install_pdk() {
    local pdk_root="${PDK_ROOT:-$HOME/.volare}"
    local pdk_ver="${GF_PDK_VERSION:-gf180mcuD}"

    if [ -d "$pdk_root/$pdk_ver/libs.tech/magic" ]; then
        echo "[SKIP] PDK already installed at $pdk_root/$pdk_ver"
        return
    fi

    echo "[INFO] Installing GF180MCU PDK via volare..."
    pip3 install volare 2>&1 | tail -1
    python3 -m volare enable --pdk-root "$pdk_root" "$pdk_ver" 2>&1 | tail -5
    
    if [ ! -f "$pdk_root/$pdk_ver/libs.tech/magic/$pdk_ver.magicrc" ]; then
        echo "[WARN] PDK magicrc not found. You may need to install manually."
    else
        echo "[OK] PDK installed at $pdk_root/$pdk_ver"
    fi
}
install_pdk 2>&1 | tee -a "$LOG_FILE"

# ── Verify Installation ───────────────────────────────
echo ""
echo "============================================"
echo "  Verification"
echo "============================================"

verify() {
    local all_ok=true
    for cmd in python3 ngspice magic netgen; do
        if command -v $cmd &>/dev/null; then
            echo "  ✅ $cmd: $(which $cmd)"
        else
            echo "  ❌ $cmd: NOT FOUND"
            all_ok=false
        fi
    done

    # Check Python packages
    for pkg in numpy gdsfactory gdstk glayout; do
        if python3 -c "import $pkg" 2>/dev/null; then
            echo "  ✅ Python: $pkg"
        else
            echo "  ❌ Python: $pkg — pip install $pkg"
            all_ok=false
        fi
    done

    # Check PDK
    local pdk_root="${PDK_ROOT:-$HOME/.volare}"
    if [ -f "$pdk_root/gf180mcuD/libs.tech/magic/gf180mcuD.magicrc" ]; then
        echo "  ✅ PDK: gf180mcuD"
    else
        echo "  ⚠️  PDK: not found at $pdk_root/gf180mcuD"
    fi

    echo ""
    if $all_ok; then
        echo "  ✅ All tools installed successfully!"
    else
        echo "  ⚠️  Some tools have issues. Check log: $LOG_FILE"
    fi
}
verify 2>&1 | tee -a "$LOG_FILE"

echo ""
echo "============================================"
echo "  Setup complete!"
echo "  Next: source pi-custom-mbg/common/env.sh"
echo "============================================"
