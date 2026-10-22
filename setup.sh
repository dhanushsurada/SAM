#!/bin/bash
# SAM macOS source-based developer setup.
# Builds the Tauri .app from this checkout; this is not a consumer DMG installer.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [[ "$(uname)" != "Darwin" ]]; then
  echo "ERROR: setup.sh supports macOS only." >&2
  exit 1
fi

if ! command -v brew >/dev/null 2>&1; then
  echo "Homebrew is required. Install it from https://brew.sh, then rerun setup.sh." >&2
  exit 1
fi

for tool in python3 node npm cargo; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "Missing $tool. Install Python 3, Node.js, and Rust toolchain, then rerun." >&2
    exit 1
  fi
done

PYTHON=python3
if command -v python3.12 >/dev/null 2>&1; then PYTHON=python3.12; fi
if command -v python3.11 >/dev/null 2>&1; then PYTHON=python3.11; fi

if ! brew list portaudio >/dev/null 2>&1; then
  echo "Installing PortAudio (Homebrew)..."
  brew install portaudio
fi

if [[ ! -x .venv/bin/python ]]; then
  if [[ -e .venv ]]; then
    echo "An incomplete .venv exists. Move it aside yourself and rerun; setup will not delete it." >&2
    exit 1
  fi
  "$PYTHON" -m venv .venv
fi
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m playwright install chromium

mkdir -p "$HOME/.sam_data/logs" "$HOME/.sam_data/memory/chroma" \
  "$HOME/.sam_data/founder_mode/export" "$HOME/.sam_data/skills/compiled"

if ! command -v ollama >/dev/null 2>&1; then
  read -r -p "Ollama is required. Install it now using the official Ollama installer? [y/N] " answer
  if [[ "$answer" =~ ^[Yy]$ ]]; then
    curl -fsSL https://ollama.com/install.sh | sh
  else
    echo "Install Ollama from https://ollama.com/download and rerun setup.sh." >&2
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
