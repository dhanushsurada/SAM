#!/bin/bash
# SAM Setup Script — Linux (Debian/Ubuntu family, apt-based)
#
# Scope: Python backend developer setup for Debian/Ubuntu (apt-based) only.
# It does not install the Tauri desktop shell or configure login startup.
# The backend is started manually; its API process is controlled by SAMRuntime.
#
# v1 scope: no systemd unit / autostart-on-boot here on purpose (the
# macOS/launchd equivalent). Run manually for now; a --user systemd unit can
# be added once this base path is validated on real hardware.
#
# Run once on your machine after cloning the repo.
# Usage: chmod +x setup_linux.sh && ./setup_linux.sh

set -e
SETUP_STAGE="prerequisites"
SAM_PYTHON_FOR_JOURNAL=""
record_setup_failure() {
    status=$?
    if [[ -n "$SAM_PYTHON_FOR_JOURNAL" && -x "$SAM_PYTHON_FOR_JOURNAL" ]]; then
        "$SAM_PYTHON_FOR_JOURNAL" runtime/environment_manager.py record-step "$SETUP_STAGE" blocked --detail "Setup stopped with exit code $status; rerun setup_linux.sh to resume safely." >/dev/null 2>&1 || true
    fi
    exit "$status"
}
trap record_setup_failure ERR

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
if ! command -v curl >/dev/null 2>&1; then
    sudo apt-get update
    sudo apt-get install -y curl
fi

echo -e "${GREEN}[1/8] Checking Python...${NC}"
if ! command -v python3 >/dev/null 2>&1; then
    echo "A bootstrap Python is needed to read SAM's compatibility policy. Installing via apt (requires sudo)..."
    sudo apt-get update
    sudo apt-get install -y python3 python3-venv python3-pip
fi
BOOTSTRAP_PYTHON="$(command -v python3)"
SAM_PYTHON_FOR_JOURNAL="$BOOTSTRAP_PYTHON"
"$BOOTSTRAP_PYTHON" runtime/compatibility.py check-platform --os linux
"$BOOTSTRAP_PYTHON" runtime/compatibility.py check-requirements
PYTHON="$("$BOOTSTRAP_PYTHON" runtime/compatibility.py select-python 2>/dev/null || true)"
if [[ -z "$PYTHON" ]]; then
    SUPPORTED_MINOR="$(python3 -c 'import json; print(json.load(open("compatibility/manifest.json"))["python"]["preferred_versions"][0])')"
    PYTHON_APT_PACKAGES="$(python3 -c 'import json,sys; d=json.load(open("compatibility/manifest.json")); print(" ".join(d["platforms"]["linux"]["python_packages"][sys.argv[1]]))' "$SUPPORTED_MINOR")"
    echo "No supported Python was found on PATH. SAM requires Python $SUPPORTED_MINOR; install it from the configured apt repository."
    read -r -p "Install the manifest packages ($PYTHON_APT_PACKAGES) now? [y/N] " answer
    if [[ "$answer" =~ ^[Yy]$ ]]; then
        sudo apt-get update
        # Word splitting is deliberate: package names come from the checked-in manifest.
        sudo apt-get install -y $PYTHON_APT_PACKAGES
        PYTHON="$("$BOOTSTRAP_PYTHON" runtime/compatibility.py select-python)"
    else
        echo "Install a supported version from compatibility/manifest.json and rerun setup_linux.sh." >&2
        exit 1
    fi
fi
echo "  Selected: $PYTHON ($("$PYTHON" --version))"

# venv module isn't always bundled with system python3 on Debian/Ubuntu —
# unlike macOS/Windows this is a real, distro-specific gap worth checking
# explicitly rather than letting `python3 -m venv` fail with a cryptic error.
if ! "$PYTHON" -c "import venv" >/dev/null 2>&1; then
    echo "  python3-venv not found. Installing (requires sudo)..."
    sudo apt-get update
    sudo apt-get install -y python3-venv
fi

INSTALL_GROUPS=(core)
for group in voice vision memory integrations; do
    read -r -p "Install optional '$group' dependencies now? [y/N] " answer
    if [[ "$answer" =~ ^[Yy]$ ]]; then INSTALL_GROUPS+=("$group"); fi
done

echo -e "${GREEN}[1.5/8] Checking feature-specific system packages...${NC}"
if [[ " ${INSTALL_GROUPS[*]} " == *" voice "* ]]; then
    VOICE_SYSTEM_PACKAGES="$("$BOOTSTRAP_PYTHON" runtime/environment_manager.py system-dependencies --group voice --format packages)"
    for package in $VOICE_SYSTEM_PACKAGES; do
        if ! dpkg -s "$package" >/dev/null 2>&1; then
            echo "  Installing $package (requires sudo)..."
            sudo apt-get update
            sudo apt-get install -y "$package"
        fi
    done
fi

echo -e "${GREEN}[2/8] Checking Ollama...${NC}"
SETUP_STAGE="ollama-start"
"$BOOTSTRAP_PYTHON" runtime/environment_manager.py record-step ollama-start started
if ! command -v ollama &> /dev/null; then
    read -r -p "Ollama is required for local models. Install it now using the official installer? [y/N] " answer
    if [[ "$answer" =~ ^[Yy]$ ]]; then
        curl -fsSL https://ollama.com/install.sh | sh
    else
        echo "Install Ollama and rerun setup_linux.sh." >&2
        exit 1
    fi
    echo "  Ollama installed"
else
    echo "  Ollama already installed"
fi

echo -e "${GREEN}[3/8] Waiting for Ollama...${NC}"
if ! curl --silent --fail --max-time 2 http://127.0.0.1:11434/api/tags >/dev/null; then
    ollama serve &>/dev/null &
fi
OLLAMA_READY=false
for _ in {1..60}; do
    if curl --silent --fail --max-time 2 http://127.0.0.1:11434/api/tags >/dev/null; then OLLAMA_READY=true; break; fi
    sleep 1
done
if [[ "$OLLAMA_READY" != true ]]; then echo "Ollama failed to become ready." >&2; exit 1; fi
"$BOOTSTRAP_PYTHON" runtime/environment_manager.py record-step ollama-start complete

echo -e "${GREEN}[5/8] Creating Python virtual environment...${NC}"
SETUP_STAGE="python-environment"
"$BOOTSTRAP_PYTHON" runtime/environment_manager.py record-step python-environment started
"$BOOTSTRAP_PYTHON" runtime/environment_manager.py prepare-venv --python "$PYTHON" --path "$PWD/.venv"
"$BOOTSTRAP_PYTHON" runtime/environment_manager.py record-step python-environment complete --detail "$PWD/.venv/bin/python"
source .venv/bin/activate
pip install --upgrade pip --quiet

echo -e "${GREEN}[6/8] Installing Python packages...${NC}"
# Safe to re-run: pip install is idempotent and repairs a partial/broken
# env (missing or outdated packages) without touching unrelated ones.
DEPENDENCY_ARGS=()
for group in "${INSTALL_GROUPS[@]}"; do
    while IFS= read -r requirement; do
        [[ -n "$requirement" ]] && DEPENDENCY_ARGS+=("$requirement")
    done < <(.venv/bin/python runtime/environment_manager.py resolve-dependencies --group "$group" --format requirements)
done
"$BOOTSTRAP_PYTHON" runtime/environment_manager.py record-step python-dependencies started
SETUP_STAGE="python-dependencies"
READY_ARGS=()
for group in "${INSTALL_GROUPS[@]}"; do READY_ARGS+=(--group "$group"); done
if .venv/bin/python runtime/environment_manager.py dependencies-ready "${READY_ARGS[@]}" >/dev/null 2>&1; then
    echo "Selected dependency groups already satisfy the compatibility manifest; resuming after that stage."
else
    if ! pip install "${DEPENDENCY_ARGS[@]}" --quiet; then
        "$BOOTSTRAP_PYTHON" runtime/environment_manager.py record-step python-dependencies blocked --detail "Package installation failed; retry after resolving the reported dependency issue." >/dev/null
        "$BOOTSTRAP_PYTHON" runtime/environment_manager.py restore-venv --path "$PWD/.venv" >/dev/null || true
        echo "The previous Python environment was restored when available; the failed candidate was retained. Rerun after resolving the package issue." >&2
        exit 1
    fi
fi

if [[ " ${INSTALL_GROUPS[*]} " == *" vision "* ]]; then
    echo "  Installing Playwright Chromium..."
    .venv/bin/playwright install chromium
    MISSING_VISION_LIBS="$(.venv/bin/python runtime/environment_manager.py system-dependencies --group vision --format missing)"
    if [[ -n "$MISSING_VISION_LIBS" ]]; then
        echo "  Missing browser libraries detected: ${MISSING_VISION_LIBS//$'\n'/, }"
        read -r -p "Install Playwright's Debian/Ubuntu prerequisites with sudo now? [y/N] " answer
        if [[ "$answer" =~ ^[Yy]$ ]]; then
            sudo .venv/bin/playwright install-deps chromium
        else
            echo -e "${YELLOW}Chromium may not launch until its OS library prerequisites are installed.${NC}"
        fi
    else
        echo "  Playwright shared-library prerequisites are available."
    fi
fi
"$BOOTSTRAP_PYTHON" runtime/environment_manager.py record-step python-dependencies complete

echo -e "${GREEN}[7/8] Initializing ~/.sam_data...${NC}"
# Same canonical location as macOS/Windows (see config/settings.py's
# Path.home() / ".sam_data"). See setup.sh for why these are the real
# paths and not the old repo-relative ones.
mkdir -p "$HOME/.sam_data/logs"
mkdir -p "$HOME/.sam_data/memory/chroma"
mkdir -p "$HOME/.sam_data/founder_mode/export"
mkdir -p "$HOME/.sam_data/skills/compiled"

echo -e "${GREEN}[8/8] Review configured model downloads...${NC}"
SETUP_STAGE="model-downloads"
MODEL_LIST=$(.venv/bin/python - <<'PY'
from config.settings import Settings
s = Settings()
for item in (s.primary_model, s.fallback_model, s.embedding_model, s.vision_model): print(item or "")
PY
)
FREE_MODEL_GB=$(.venv/bin/python -c 'import shutil; from pathlib import Path; print(round(shutil.disk_usage(Path.home()).free / (1024**3), 1))')
echo "Available home-volume space before model downloads: ${FREE_MODEL_GB} GB. Ollama reports exact progress after a model is selected."
"$BOOTSTRAP_PYTHON" runtime/environment_manager.py record-step model-downloads started --detail "Downloads require per-model confirmation"
while IFS= read -r model; do
    [[ -n "$model" ]] || continue
    if ollama list 2>/dev/null | awk 'NR>1 {print $1}' | grep -Fxq "$model"; then echo "Already installed: $model"; continue; fi
    read -r -p "Download '$model'? This may require several GB. [y/N] " answer
    if [[ "$answer" =~ ^[Yy]$ ]]; then ollama pull "$model"; else echo "Skipped $model."; fi
done <<< "$MODEL_LIST"
"$BOOTSTRAP_PYTHON" runtime/environment_manager.py record-step model-downloads complete

echo -e "${GREEN}Startup behavior${NC}"
echo -e "${YELLOW}  Not configured in this version — start SAM manually (see below).${NC}"
echo -e "${YELLOW}  A systemd --user unit is planned once this installer is verified${NC}"
echo -e "${YELLOW}  on real hardware; see setup_linux.sh header.${NC}"

echo ""
echo -e "${BLUE}╔═══════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║            SAM Setup Complete! (Linux)               ║${NC}"
echo -e "${BLUE}╠═══════════════════════════════════════════════════════╣${NC}"
echo -e "${BLUE}║  Models: use current config; downloads were opt-in    ║${NC}"
echo -e "${BLUE}║                                                       ║${NC}"
echo -e "${BLUE}║  To start SAM now:                                    ║${NC}"
echo -e "${BLUE}║  ${GREEN}source .venv/bin/activate && python main.py${BLUE}        ║${NC}"
echo -e "${BLUE}║                                                       ║${NC}"
echo -e "${BLUE}║  No auto-start on boot yet on Linux — run manually    ║${NC}"
echo -e "${BLUE}║  after each reboot, or set up your own systemd unit.  ║${NC}"
echo -e "${BLUE}╚═══════════════════════════════════════════════════════╝${NC}"
echo ""
