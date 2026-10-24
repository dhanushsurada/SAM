#!/bin/bash
# Sign every Mach-O binary inside the staged runtime (bundled Python, its
# extension modules and dylibs, and wheels' native libraries) with the
# hardened runtime. Tauri signs the app itself but not nested resources, and
# Apple's notary service rejects a bundle containing unsigned executables.
#
# Needs APPLE_SIGNING_IDENTITY (e.g. "Developer ID Application: Name (TEAMID)").
set -euo pipefail
: "${APPLE_SIGNING_IDENTITY:?APPLE_SIGNING_IDENTITY is required}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME="${1:-$ROOT/interfaces/desktop/src-tauri/resources/sam-runtime}"
ENTITLEMENTS="$ROOT/interfaces/desktop/src-tauri/Entitlements.plist"
[[ -d "$RUNTIME" ]] || { echo "Runtime not staged at $RUNTIME" >&2; exit 1; }

count=0
while IFS= read -r -d '' file; do
  if file -b "$file" | grep -q "Mach-O"; then
    codesign --force --options runtime --timestamp \
      --entitlements "$ENTITLEMENTS" --sign "$APPLE_SIGNING_IDENTITY" "$file"
    count=$((count + 1))
  fi
done < <(find "$RUNTIME" -type f -print0)
echo "Signed $count Mach-O binaries in $RUNTIME"
