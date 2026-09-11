#!/bin/bash
# SAM Setup Script — Linux (Debian/Ubuntu family, apt-based)
#
# STATUS: implemented, NOT yet verified on a real machine. This mirrors
# setup.sh's (macOS) structure step-for-step so the two stay easy to compare
# and maintain together. Treat as "implemented, unverified" until someone
# actually runs it start-to-finish on real Debian/Ubuntu hardware — see
# docs/deployment/LOCAL_RUNTIME.md for the same convention already used for
# the Windows script's real-machine gap.
#
# v1 scope: no systemd unit / autostart-on-boot here on purpose (the
# macOS/launchd equivalent). Run manually for now; a --user systemd unit can
# be added once this base path is validated on real hardware.
#
# Run once on your machine after cloning the repo.
# Usage: chmod +x setup_linux.sh && ./setup_linux.sh

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}"
echo "  ╔═══════════════════════════════════╗"
echo "  ║          SAM — Setup (Linux)      ║"
echo "  ║  Personal AI. Fully Local.        ║"
echo "  ╚═══════════════════════════════════╝"
echo -e "${NC}"

# ─── Check Linux + apt ────────────────────────────────────────────────────
if [[ "$(uname)" != "Linux" ]]; then
    echo -e "${RED}ERROR: setup_linux.sh requires Linux${NC}"
    exit 1
fi
if ! command -v apt-get &> /dev/null; then
    echo -e "${RED}ERROR: this script only supports apt-based distributions (Debian/Ubuntu family).${NC}"
    echo -e "${RED}No other package manager is supported yet — see Phase 4 docs.${NC}"
    exit 1
fi

echo -e "${GREEN}[1/8] Checking Python...${NC}"
if command -v python3.11 >/dev/null 2>&1; then
    PYTHON=python3.11
elif command -v python3.12 >/dev/null 2>&1; then
    PYTHON=python3.12
elif command -v python3 >/dev/null 2>&1; then
    PYTHON=python3
else
    echo "Python3 not found. Installing via apt (requires sudo)..."
    sudo apt-get update
    sudo apt-get install -y python3 python3-venv python3-pip
    PYTHON=python3
fi
PYTHON_VERSION=$($PYTHON --version)
echo "  Found: $PYTHON_VERSION"

# venv module isn't always bundled with system python3 on Debian/Ubuntu —
# unlike macOS/Windows this is a real, distro-specific gap worth checking
# explicitly rather than letting `python3 -m venv` fail with a cryptic error.
if ! $PYTHON -c "import venv" >/dev/null 2>&1; then
    echo "  python3-venv not found. Installing (requires sudo)..."
    sudo apt-get update
    sudo apt-get install -y python3-venv
fi

echo -e "${GREEN}[1.5/8] Checking PortAudio...${NC}"
if ! dpkg -s portaudio19-dev >/dev/null 2>&1; then
    echo "  Installing PortAudio dev headers (requires sudo)..."
    sudo apt-get update
    sudo apt-get install -y portaudio19-dev
else
    echo "  PortAudio already installed"
fi

echo -e "${GREEN}[2/8] Installing Ollama...${NC}"
if ! command -v ollama &> /dev/null; then
    echo "  Downloading Ollama..."
    curl -fsSL https://ollama.com/install.sh | sh
    echo "  Ollama installed"
else
    echo "  Ollama already installed"
fi

echo -e "${GREEN}[3/8] Starting Ollama...${NC}"
if ! pgrep -x "ollama" > /dev/null; then
    ollama serve &>/dev/null &
    sleep 3
else
    echo "  Ollama already running"
fi

echo -e "${GREEN}[4/8] Pulling AI models (this takes time — grab a coffee)...${NC}"

# Detect RAM via /proc/meminfo directly rather than `free`, which is not
# guaranteed to be installed on minimal/container Debian images.
RAM_GB=$(awk '/MemTotal/{printf "%d", $2/1024/1024}' /proc/meminfo)
echo "  Detected RAM: ${RAM_GB}GB"

if [ "$RAM_GB" -ge 32 ]; then
    MODEL="qwen2.5:32b"
elif [ "$RAM_GB" -ge 16 ]; then
    MODEL="qwen2.5:14b"
else
    MODEL="qwen2.5:7b"
fi

echo "  Pulling brain model: $MODEL"
ollama pull $MODEL

echo "  Pulling embedding model: nomic-embed-text"
ollama pull nomic-embed-text

echo "  Pulling vision model: moondream"
ollama pull moondream

echo -e "${GREEN}[5/8] Creating Python virtual environment...${NC}"
if [ -d ".venv" ] && [ -x ".venv/bin/python3" ]; then
    echo "  Existing .venv found — reusing it (run 'rm -rf .venv' first for a clean rebuild)"
else
    if [ -d ".venv" ]; then
        echo -e "${YELLOW}  .venv exists but looks incomplete — recreating it${NC}"
        rm -rf .venv
    fi
    $PYTHON -m venv .venv
fi
source .venv/bin/activate
pip install --upgrade pip --quiet

echo -e "${GREEN}[6/8] Installing Python packages...${NC}"
# Safe to re-run: pip install is idempotent and repairs a partial/broken
# env (missing or outdated packages) without touching unrelated ones.
pip install -r requirements.txt --quiet

echo "  Installing Playwright browsers..."
playwright install chromium
# Playwright on Linux additionally needs OS-level shared libraries beyond
# what apt installs above (GTK/NSS/etc.) — `playwright install-deps` covers
# these but needs sudo and is a genuinely separate step from the Python
# package. Not run automatically here to avoid an unannounced sudo prompt
# mid-script; surfaced explicitly instead so it isn't silently skipped.
echo -e "${YELLOW}  If Chromium fails to launch at runtime, also run:${NC}"
echo -e "${YELLOW}    sudo .venv/bin/playwright install-deps${NC}"

echo -e "${GREEN}[7/8] Initializing ~/.sam_data...${NC}"
# Same canonical location as macOS/Windows (see config/settings.py's
# Path.home() / ".sam_data"). See setup.sh for why these are the real
# paths and not the old repo-relative ones.
mkdir -p "$HOME/.sam_data/logs"
mkdir -p "$HOME/.sam_data/memory/chroma"
mkdir -p "$HOME/.sam_data/founder_mode/export"
mkdir -p "$HOME/.sam_data/skills/compiled"

echo -e "${GREEN}[8/8] Auto-start on boot...${NC}"
echo -e "${YELLOW}  Not configured in this version — start SAM manually (see below).${NC}"
echo -e "${YELLOW}  A systemd --user unit is planned once this installer is verified${NC}"
echo -e "${YELLOW}  on real hardware; see setup_linux.sh header.${NC}"

echo ""
echo -e "${BLUE}╔═══════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║            SAM Setup Complete! (Linux)               ║${NC}"
echo -e "${BLUE}╠═══════════════════════════════════════════════════════╣${NC}"
echo -e "${BLUE}║  Brain model: ${GREEN}$MODEL${BLUE}                       ║${NC}"
echo -e "${BLUE}║                                                       ║${NC}"
echo -e "${BLUE}║  To start SAM now:                                    ║${NC}"
echo -e "${BLUE}║  ${GREEN}source .venv/bin/activate && python main.py${BLUE}        ║${NC}"
echo -e "${BLUE}║                                                       ║${NC}"
echo -e "${BLUE}║  No auto-start on boot yet on Linux — run manually    ║${NC}"
echo -e "${BLUE}║  after each reboot, or set up your own systemd unit.  ║${NC}"
echo -e "${BLUE}╚═══════════════════════════════════════════════════════╝${NC}"
echo ""
