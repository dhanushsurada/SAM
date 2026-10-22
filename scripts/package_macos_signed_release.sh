#!/bin/bash
# Build and notarize a macOS consumer DMG. Credentials are supplied through
# the environment and are never written to repository files.
set -euo pipefail

required=(APPLE_SIGNING_IDENTITY APPLE_ID APPLE_PASSWORD APPLE_TEAM_ID)
for name in "${required[@]}"; do
  if [[ -z "${!name:-}" ]]; then
    echo "Missing $name. Configure an Apple Developer ID and notarization credentials in the environment." >&2
    exit 2
  fi
done
command -v xcrun >/dev/null || { echo "Xcode Command Line Tools (xcrun) are required." >&2; exit 2; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DESKTOP="$ROOT/interfaces/desktop"
cd "$DESKTOP"
npm run package:macos-consumer

shopt -s nullglob
images=(src-tauri/target/release/bundle/dmg/*.dmg)
if (( ${#images[@]} != 1 )); then
  echo "Expected exactly one consumer DMG in src-tauri/target/release/bundle/dmg; found ${#images[@]}." >&2
  exit 1
fi
image="${images[0]}"
xcrun notarytool submit "$image" --apple-id "$APPLE_ID" --password "$APPLE_PASSWORD" \
  --team-id "$APPLE_TEAM_ID" --wait
xcrun stapler staple "$image"
echo "Signed and notarized release DMG: $DESKTOP/$image"
