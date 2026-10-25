#!/usr/bin/env bash
# SAM installer for macOS and Linux — downloads the latest release from GitHub,
# verifies its SHA-256 checksum, and installs it.
#
#   curl -fsSL https://raw.githubusercontent.com/dhanushsurada/SAM/main/scripts/install.sh | bash
#
# Options (environment variables):
#   SAM_VERSION=v0.1.0     install a specific release tag instead of the latest
#   SAM_REPO=owner/name    install from a fork (default: dhanushsurada/SAM)
set -euo pipefail

REPO="${SAM_REPO:-dhanushsurada/SAM}"
VERSION="${SAM_VERSION:-latest}"
API="https://api.github.com/repos/${REPO}/releases"

say()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31mError:\033[0m %s\n' "$*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "'$1' is required but not installed."; }

need curl
need uname

OS="$(uname -s)"; ARCH="$(uname -m)"
case "$ARCH" in arm64|aarch64) ARCH_ID=arm64 ;; x86_64|amd64) ARCH_ID=x86_64 ;; *) die "Unsupported CPU architecture: $ARCH" ;; esac

if [[ "$VERSION" == "latest" ]]; then URL="$API/latest"; else URL="$API/tags/$VERSION"; fi
say "Looking up release ($VERSION) from github.com/$REPO"
RELEASE_JSON="$(curl -fsSL -H 'Accept: application/vnd.github+json' "$URL")" || die "Could not read release information. Is there a published release yet?"

# Pick the asset for this OS/arch. Asset names are produced by the release workflow.
case "$OS" in
  Darwin) PATTERN="SAM_.*_macos-${ARCH_ID}\\.dmg" ;;
  Linux)
    [[ "$ARCH_ID" == "x86_64" ]] || die "Linux builds are x86_64 only for now."
    if command -v dpkg >/dev/null 2>&1 && command -v apt-get >/dev/null 2>&1; then PATTERN="SAM_.*_linux-x86_64\\.deb"; else PATTERN="SAM_.*_linux-x86_64\\.AppImage"; fi ;;
  *) die "This installer supports macOS and Linux. On Windows use install.ps1 or download SAM-Setup.exe." ;;
esac
ASSET_URL="$(printf '%s' "$RELEASE_JSON" | grep -o '"browser_download_url": *"[^"]*"' | cut -d'"' -f4 | grep -E "/${PATTERN}\$" | head -n1 || true)"
SUMS_URL="$(printf '%s' "$RELEASE_JSON" | grep -o '"browser_download_url": *"[^"]*"' | cut -d'"' -f4 | grep -E '/SHA256SUMS\.txt$' | head -n1 || true)"
[[ -n "$ASSET_URL" ]] || die "No installer for $OS/$ARCH_ID found in that release."
[[ -n "$SUMS_URL"  ]] || die "The release has no SHA256SUMS.txt; refusing to install an unverifiable file."

TMP="$(mktemp -d)"
MOUNT=""
cleanup() {
  if [[ -n "$MOUNT" ]]; then hdiutil detach -quiet "$MOUNT" || true; fi
  rm -rf "$TMP"
}
trap cleanup EXIT
FILE="$TMP/$(basename "$ASSET_URL")"
say "Downloading $(basename "$ASSET_URL")"
curl -fL --progress-bar -o "$FILE" "$ASSET_URL"
curl -fsSL -o "$TMP/SHA256SUMS.txt" "$SUMS_URL"

say "Verifying checksum"
EXPECTED="$(grep -F "$(basename "$FILE")" "$TMP/SHA256SUMS.txt" | awk '{print $1}' | head -n1)"
[[ -n "$EXPECTED" ]] || die "Checksum for $(basename "$FILE") not listed in SHA256SUMS.txt."
if command -v sha256sum >/dev/null 2>&1; then ACTUAL="$(sha256sum "$FILE" | awk '{print $1}')"; else ACTUAL="$(shasum -a 256 "$FILE" | awk '{print $1}')"; fi
[[ "$EXPECTED" == "$ACTUAL" ]] || die "Checksum mismatch — the download is corrupt or tampered with. Nothing was installed."

case "$FILE" in
  *.dmg)
    say "Installing to /Applications"
    MOUNT="$(hdiutil attach -nobrowse "$FILE" | awk -F'\t' '/\/Volumes\//{print $NF; exit}')"
    [[ -n "$MOUNT" ]] || die "Could not determine the mounted disk image path."
    [[ -d "$MOUNT/SAM.app" ]] || die "SAM.app not found in the disk image."
    pkill -x sam-desktop 2>/dev/null || true
    rm -rf "/Applications/SAM.app" 2>/dev/null || sudo rm -rf "/Applications/SAM.app"
    cp -R "$MOUNT/SAM.app" /Applications/ 2>/dev/null || sudo cp -R "$MOUNT/SAM.app" /Applications/
    hdiutil detach -quiet "$MOUNT" || true
    MOUNT=""
    say "Done. Opening SAM"; open /Applications/SAM.app ;;
  *.deb)
    say "Installing the .deb (needs administrator rights)"
    sudo apt-get install -y "$FILE"
    say "Done. Launch SAM from your applications menu, or run: sam-desktop" ;;
  *.AppImage)
    DEST="$HOME/.local/bin"; mkdir -p "$DEST"
    install -m 0755 "$FILE" "$DEST/SAM.AppImage"
    say "Done. Run: $DEST/SAM.AppImage" ;;
esac

if ! command -v ollama >/dev/null 2>&1 && [[ ! -e /Applications/Ollama.app ]]; then
  say "SAM needs Ollama for local models. SAM's first-run screen will guide you through installing it."
fi
