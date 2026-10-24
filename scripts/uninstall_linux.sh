#!/usr/bin/env bash
# Remove SAM on Linux. Keeps ~/.sam_data and Ollama models unless
# --remove-user-data is given (then you must type the exact path to confirm).
set -euo pipefail
remove_data=false
if [[ "${1:-}" == "--remove-user-data" ]]; then remove_data=true
elif [[ $# -gt 0 ]]; then echo "Usage: $0 [--remove-user-data]" >&2; exit 2; fi

pkill -x sam-desktop 2>/dev/null || true
if dpkg -s sam >/dev/null 2>&1; then
  echo "Removing the sam package (needs administrator rights)"
  sudo apt-get remove -y sam
fi
rm -f "$HOME/.local/bin/SAM.AppImage" "$HOME/.config/autostart/SAM.desktop" 2>/dev/null || true

if [[ "$remove_data" == true ]]; then
  data="$HOME/.sam_data"
  if [[ -e "$data" ]]; then
    echo "This permanently removes settings, memory and logs at: $data"
    read -r -p "Type DELETE $data to confirm: " confirmation
    [[ "$confirmation" == "DELETE $data" ]] || { echo "User data was preserved."; exit 1; }
    rm -rf -- "$data"
  fi
fi
echo "SAM removed. Ollama and downloaded models were left intact."
