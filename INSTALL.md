# Installing SAM

SAM installs like any other desktop app: download, double-click, done. You do
**not** need Python, Node, Rust or Git. SAM ships its own private Python
runtime. The only separate piece is [Ollama](https://ollama.com) (the local
model engine), which SAM's first-run screen guides you through installing.

| | Windows 10/11 | macOS 14+ | Linux (Ubuntu/Debian) |
|---|---|---|---|
| **Download** | `SAM_<ver>_windows-x86_64-setup.exe` | `SAM_<ver>_macos-arm64.dmg` (Apple silicon) or `…-x86_64.dmg` (Intel) | `SAM_<ver>_linux-x86_64.deb` (or `.AppImage`) |
| **Install** | Double-click. No administrator prompt. | Open the DMG, drag **SAM** to Applications. | `.deb`: `sudo apt install ./SAM_*.deb`; AppImage: download and make executable, or use `scripts/install.sh`. |
| **Start** | Start menu → SAM | Applications → SAM | `.deb`: Applications menu; AppImage: run `SAM.AppImage` (the script installs it at `~/.local/bin/SAM.AppImage`). |

Get the files from the project's **Releases** page, or use the one-line
installer, which also verifies the download's SHA-256 checksum:

```bash
# macOS / Linux
curl -fsSL https://raw.githubusercontent.com/dhanushsurada/SAM/main/scripts/install.sh | bash
```
```powershell
# Windows (PowerShell)
irm https://raw.githubusercontent.com/dhanushsurada/SAM/main/scripts/install.ps1 | iex
```

## First launch

1. SAM starts its local backend automatically (nothing to configure).
2. **Onboarding → Model & voice**: if Ollama is missing, press **Get Ollama**.
   - Windows: SAM downloads Ollama's official installer, checks that it is
     validly signed by Ollama, then opens it.
   - macOS / Linux: SAM opens Ollama's download page (Linux shows the one-line
     install command).
3. Type a model name (for example `qwen2.5:7b`), press **Download model**
   (progress is shown; cancel any time), then **Use this model**.
4. Optional features (voice, vision, memory, Telegram) are installed from
   **Diagnostics** with one click; nothing optional is installed by default.

Hardware: 8 GB RAM minimum. A 7B-class model wants ~8 GB free RAM; the 14B
default wants 16 GB+. If your machine is small, pick a smaller model in step 3.

## Windows: "Windows protected your PC"

Until the installer is code-signed with a purchased certificate, SmartScreen
shows this warning for any new app. Choose **More info → Run anyway**. The
`install.ps1` route verifies the checksum before running it.

## macOS: "SAM can't be opened"

Unsigned builds need **right-click → Open** the first time. Builds produced
with an Apple Developer ID are signed and notarized and open normally.

## Updating

Install the newer version over the old one (run the new installer / replace the
app / `apt install` the new `.deb`). Your settings, memory and models are kept.

## Uninstalling

| OS | How | Your data (`~/.sam_data`) |
|---|---|---|
| Windows | Settings → Apps → SAM → Uninstall | Asked at the end (default: keep) |
| macOS | `scripts/uninstall_macos_consumer.sh` (or drag SAM to Trash) | Kept unless `--remove-user-data` |
| Linux | `scripts/uninstall_linux.sh` (or `sudo apt remove sam`) | Kept unless `--remove-user-data` |

Ollama and downloaded models are never touched by SAM's uninstallers.

## Something went wrong

- Logs: `~/.sam_data/logs` (Windows: `%USERPROFILE%\.sam_data\logs`).
- In the app: **Settings → Repair runtime setup**, and **Diagnostics**.
- "Can't reach the local SAM API": quit SAM from the tray icon and reopen it.
- Full reference: [`docs/deployment/DESKTOP_INSTALL.md`](docs/deployment/DESKTOP_INSTALL.md).

## For developers: building the installers

```bash
git tag v0.1.0 && git push --tags      # CI builds + smoke-tests all platforms, drafts a release
```

or locally, on the target OS: `cd interfaces/desktop && npm ci && npm run package`.
Source-based developer setup remains available: `setup.sh` (macOS),
`setup_linux.sh`, `setup_windows.ps1`.
