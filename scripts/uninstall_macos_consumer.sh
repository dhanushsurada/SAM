#!/bin/bash
# Remove SAM.app while preserving user-owned settings, memory, credentials,
# and Ollama models by default. Full data deletion requires a typed phrase.
set -euo pipefail

remove_data=false
if [[ "${1:-}" == "--remove-user-data" ]]; then
  remove_data=true
elif [[ $# -gt 0 ]]; then
  echo "Usage: $0 [--remove-user-data]" >&2
  exit 2
fi

apps=("/Applications/SAM.app" "$HOME/Applications/SAM.app")
for app in "${apps[@]}"; do
  if [[ -d "$app" ]]; then
    echo "Removing application bundle: $app"
    /bin/rm -rf -- "$app"
  fi
done

if [[ "$remove_data" == true ]]; then
  data="$HOME/.sam_data"
  if [[ -e "$data" ]]; then
    echo "This permanently removes settings, memory, credentials, and local SAM configuration at: $data"
    read -r -p "Type DELETE $data to confirm: " confirmation
    if [[ "$confirmation" != "DELETE $data" ]]; then
      echo "User data was preserved."
      exit 1
    fi
    /bin/rm -rf -- "$data"
  fi
fi
echo "SAM app removal complete. Ollama and downloaded models were left intact."
