#!/bin/bash
# SAM macOS source-based developer setup.
# Builds the Tauri .app from this checkout; this is not a consumer DMG installer.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
MANIFEST_FILE="$SCRIPT_DIR/compatibility/manifest.json"
COMPATIBILITY_MODULE="$SCRIPT_DIR/runtime/compatibility.py"

if [[ "$(uname)" != "Darwin" ]]; then
  echo "ERROR: setup.sh supports macOS only." >&2
  exit 1
fi

if command -v brew >/dev/null 2>&1; then
  BREW="$(command -v brew)"
else
  echo "Homebrew is required to install the macOS developer prerequisites."
  read -r -p "Run the official Homebrew installer from https://brew.sh now? It may request administrator access. [y/N] " answer
  if [[ ! "$answer" =~ ^[Yy]$ ]]; then
    echo "Install Homebrew from https://brew.sh, then rerun setup.sh." >&2
    exit 1
  fi
  curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh | /bin/bash
  if [[ -x /opt/homebrew/bin/brew ]]; then
    BREW=/opt/homebrew/bin/brew
  elif [[ -x /usr/local/bin/brew ]]; then
    BREW=/usr/local/bin/brew
  else
    echo "Homebrew installer finished, but its brew executable was not found. Follow Homebrew's shell setup instructions and rerun." >&2
    exit 1
  fi
  eval "$("$BREW" shellenv)"
fi

manifest_value() {
  /usr/bin/plutil -extract "$1" raw -o - "$MANIFEST_FILE"
}

if ! xcode-select -p >/dev/null 2>&1; then
  echo "Apple Command Line Tools are required to build the developer app." >&2
  echo "Run: xcode-select --install, complete the installation, then rerun setup.sh." >&2
  exit 1
fi

PYTHON_FORMULA="$(manifest_value python.bootstrap_formula)"
PYTHON_BOOTSTRAP_EXECUTABLE="$(manifest_value python.bootstrap_executable)"
NODE_FORMULA="$(manifest_value tools.node.homebrew_formula)"
RUST_FORMULA="$(manifest_value tools.rust.homebrew_formula)"
PORTAUDIO_FORMULA="$(manifest_value tools.portaudio.homebrew_formula)"
OLLAMA_CASK="$(manifest_value platforms.macos.ollama.package)"
MISSING_BREW_PACKAGES=()
command -v node >/dev/null 2>&1 || MISSING_BREW_PACKAGES+=("$NODE_FORMULA")
command -v npm >/dev/null 2>&1 || { [[ " ${MISSING_BREW_PACKAGES[*]} " == *" $NODE_FORMULA "* ]] || MISSING_BREW_PACKAGES+=("$NODE_FORMULA"); }
command -v cargo >/dev/null 2>&1 || MISSING_BREW_PACKAGES+=("$RUST_FORMULA")
command -v rustc >/dev/null 2>&1 || { [[ " ${MISSING_BREW_PACKAGES[*]} " == *" $RUST_FORMULA "* ]] || MISSING_BREW_PACKAGES+=("$RUST_FORMULA"); }
if (( ${#MISSING_BREW_PACKAGES[@]} )); then
  echo "SAM's developer setup needs these build prerequisites: ${MISSING_BREW_PACKAGES[*]}"
  read -r -p "Install them now with Homebrew? [y/N] " answer
  if [[ "$answer" =~ ^[Yy]$ ]]; then
    "$BREW" install "${MISSING_BREW_PACKAGES[@]}"
  else
    echo "Install the listed Homebrew packages and rerun setup.sh." >&2
    exit 1
  fi
fi

for tool in node npm cargo rustc; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "'$tool' is still unavailable after prerequisite setup. Open a new terminal and rerun setup.sh." >&2
    exit 1
  fi
done

BOOTSTRAP_PYTHON=""
candidate_index=0
while candidate="$(/usr/bin/plutil -extract "python.bootstrap_candidates.$candidate_index" raw -o - "$MANIFEST_FILE" 2>/dev/null)"; do
  if command -v "$candidate" >/dev/null 2>&1; then
    BOOTSTRAP_PYTHON="$(command -v "$candidate")"
    break
  fi
  candidate_index=$((candidate_index + 1))
done
if [[ -z "$BOOTSTRAP_PYTHON" ]]; then
  echo "No Python interpreter is available to read the compatibility policy." >&2
  read -r -p "Install the preferred supported interpreter ($PYTHON_FORMULA) with Homebrew? [y/N] " answer
  if [[ ! "$answer" =~ ^[Yy]$ ]]; then
    echo "Install one of the Python versions listed in compatibility/manifest.json and rerun setup.sh." >&2
    exit 1
  fi
  "$BREW" install "$PYTHON_FORMULA"
  BOOTSTRAP_PYTHON="$(command -v "$PYTHON_BOOTSTRAP_EXECUTABLE" || true)"
  if [[ -z "$BOOTSTRAP_PYTHON" ]]; then
    echo "Homebrew installed $PYTHON_FORMULA, but $PYTHON_BOOTSTRAP_EXECUTABLE is not on PATH. Open a new terminal and rerun setup.sh." >&2
    exit 1
  fi
fi

if ! PYTHON="$("$BOOTSTRAP_PYTHON" "$COMPATIBILITY_MODULE" select-python)"; then
  echo "The Python interpreter currently on PATH is not compatible with SAM's dependency set." >&2
  read -r -p "Install the manifest's preferred supported Python ($PYTHON_FORMULA) with Homebrew? [y/N] " answer
  if [[ ! "$answer" =~ ^[Yy]$ ]]; then
    echo "Install one of the supported versions shown above, then rerun setup.sh. Existing files and environments were left unchanged." >&2
    exit 1
  fi
  "$BREW" install "$PYTHON_FORMULA"
  PYTHON="$("$BOOTSTRAP_PYTHON" "$COMPATIBILITY_MODULE" select-python)"
fi

"$PYTHON" "$COMPATIBILITY_MODULE" check-requirements
"$PYTHON" "$COMPATIBILITY_MODULE" check-tools node npm rust
"$PYTHON" "$COMPATIBILITY_MODULE" check-platform --os macos \
  --version "$(sw_vers -productVersion)" --architecture "$(uname -m)"

if ! "$BREW" list "$PORTAUDIO_FORMULA" >/dev/null 2>&1; then
  echo "Installing PortAudio (Homebrew)..."
  "$BREW" install "$PORTAUDIO_FORMULA"
fi

if [[ ! -x .venv/bin/python ]]; then
  if [[ -e .venv ]]; then
    echo "An incomplete .venv exists. Move it aside yourself and rerun; setup will not delete it." >&2
    exit 1
  fi
  "$PYTHON" -m venv .venv
else
  "$PYTHON" "$COMPATIBILITY_MODULE" check-python "$SCRIPT_DIR/.venv/bin/python" >/dev/null
fi
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m playwright install chromium

mkdir -p "$HOME/.sam_data/logs" "$HOME/.sam_data/memory/chroma" \
  "$HOME/.sam_data/founder_mode/export" "$HOME/.sam_data/skills/compiled"

if ! command -v ollama >/dev/null 2>&1; then
  read -r -p "Ollama is required. Install the macOS Ollama app using Homebrew cask '$OLLAMA_CASK'? [y/N] " answer
  if [[ "$answer" =~ ^[Yy]$ ]]; then
    "$BREW" install --cask "$OLLAMA_CASK"
  else
    echo "Install Ollama for macOS from https://ollama.com/download/mac and rerun setup.sh." >&2
    exit 1
  fi
  if ! command -v ollama >/dev/null 2>&1; then
    echo "Ollama installer completed but ollama is not on PATH. Restart the terminal and rerun setup.sh." >&2
    exit 1
  fi
fi

if ! curl --silent --fail --max-time 2 http://127.0.0.1:11434/api/tags >/dev/null; then
  echo "Starting Ollama..."
  (ollama serve >/dev/null 2>&1 &)
fi
OLLAMA_READY=false
for _ in {1..60}; do
  if curl --silent --fail --max-time 2 http://127.0.0.1:11434/api/tags >/dev/null; then
    OLLAMA_READY=true
    break
  fi
  sleep 1
done
if [[ "$OLLAMA_READY" != true ]]; then
  echo "Ollama did not become ready within 60 seconds. Start it and rerun setup.sh." >&2
  exit 1
fi

# Read existing Settings values. The setup script never rewrites settings.yaml
# and asks before downloading any model (which can require many GB of storage).
MODEL_LIST=$(.venv/bin/python - <<'PY'
from config.settings import Settings
s = Settings()
for item in (s.primary_model, s.fallback_model, s.embedding_model, s.vision_model):
    print(item or "")
PY
)
MODELS=()
while IFS= read -r model_line; do MODELS+=("$model_line"); done <<< "$MODEL_LIST"
LABELS=("Primary model" "Fallback model" "Embedding model" "Vision model")
for i in "${!MODELS[@]}"; do
  model="${MODELS[$i]}"
  [[ -n "$model" ]] || continue
  if ollama list 2>/dev/null | awk 'NR>1 {print $1}' | grep -Fxq "$model"; then
    echo "${LABELS[$i]} already installed: $model"
    continue
  fi
  read -r -p "Download ${LABELS[$i]} '$model'? Model downloads may be several GB. [y/N] " answer
  if [[ "$answer" =~ ^[Yy]$ ]]; then
    ollama pull "$model"
  else
    echo "Skipped $model; you can download it later from SAM Settings."
  fi
done

echo "Installing desktop frontend dependencies and building the native app..."
(
  cd interfaces/desktop
  npm ci
  npm run tauri -- build --bundles app
)

APP_PATH="$SCRIPT_DIR/interfaces/desktop/src-tauri/target/release/bundle/macos/SAM.app"
if [[ ! -d "$APP_PATH" ]]; then
  echo "Tauri build completed but expected app was not found: $APP_PATH" >&2
  exit 1
fi

# Configuration is deliberately outside the source tree. Refresh checkout
# paths while preserving the user's configured API endpoint.
RUNTIME_CONFIG="$HOME/.sam_data/desktop-runtime.json"
if [[ ! -e "$RUNTIME_CONFIG" ]]; then
  API_PORT=$(.venv/bin/python -c 'from config.settings import Settings; print(Settings().api_port)')
  SAM_ROOT="$SCRIPT_DIR" SAM_PYTHON="$SCRIPT_DIR/.venv/bin/python" \
  SAM_CLI="$SCRIPT_DIR/sam_cli.py" SAM_API="http://127.0.0.1:$API_PORT" \
    .venv/bin/python - <<'PY'
import json, os
from pathlib import Path
path = Path.home() / ".sam_data" / "desktop-runtime.json"
config = {
    "app_root": os.environ["SAM_ROOT"],
    "resources_dir": os.environ["SAM_ROOT"],
    "sam_cli": os.environ["SAM_CLI"],
    "python": os.environ["SAM_PYTHON"],
    "api_base_url": os.environ["SAM_API"],
    "environment_path": os.environ.get("PATH", ""),
}
path.write_text(json.dumps(config, indent=2) + "\n")
PY
else
  SAM_ROOT="$SCRIPT_DIR" SAM_PYTHON="$SCRIPT_DIR/.venv/bin/python" \
  SAM_CLI="$SCRIPT_DIR/sam_cli.py" \
  SAM_PATH="$PATH" \
    .venv/bin/python - <<'PY'
import json, os
from pathlib import Path
path = Path.home() / ".sam_data" / "desktop-runtime.json"
existing = json.loads(path.read_text())
existing.update({
    "app_root": os.environ["SAM_ROOT"],
    "resources_dir": os.environ["SAM_ROOT"],
    "sam_cli": os.environ["SAM_CLI"],
    "python": os.environ["SAM_PYTHON"],
    "environment_path": os.environ["SAM_PATH"],
})
existing.setdefault("api_base_url", "http://127.0.0.1:8420")
path.write_text(json.dumps(existing, indent=2) + "\n")
PY
  echo "Updated runtime paths and preserved API endpoint: $RUNTIME_CONFIG"
fi

# Migrate the legacy backend launch agent only after the replacement app and
# runtime configuration are ready. Preserve the plist as a disabled backup.
LEGACY_PLIST="$HOME/Library/LaunchAgents/ai.sam.assistant.plist"
if [[ -f "$LEGACY_PLIST" ]]; then
  if ! launchctl bootout "gui/$(id -u)" "$LEGACY_PLIST" >/dev/null 2>&1 \
      && launchctl print "gui/$(id -u)/ai.sam.assistant" >/dev/null 2>&1; then
    echo "The legacy ai.sam.assistant launchd job is still loaded; refusing to start a second backend manager." >&2
    exit 1
  fi
  LEGACY_BACKUP="$LEGACY_PLIST.disabled"
  if [[ -e "$LEGACY_BACKUP" ]]; then LEGACY_BACKUP="$LEGACY_PLIST.disabled.$(date +%Y%m%d%H%M%S)"; fi
  mv "$LEGACY_PLIST" "$LEGACY_BACKUP"
  echo "Disabled legacy launch agent and preserved it at $LEGACY_BACKUP"
fi

echo "Setup complete. Launching the SAM app: $APP_PATH"
echo "The desktop app owns the SAM API lifecycle; no launchd backend job was installed."
open "$APP_PATH"
