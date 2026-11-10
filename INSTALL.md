# Installing SAM

SAM installs like any other desktop app: download, double-click, done. You do
**not** need Python, Node, Rust or Git. SAM ships its own private Python
runtime. The only separate piece is [Ollama](https://ollama.com) (the local
model engine), which SAM's first-run screen guides you through installing.

| | Windows 10/11 | macOS 14+ | Linux (Ubuntu/Debian) | Android 8.0+ (API 26+) |
|---|---|---|---|---|
| **Download** | `SAM_<ver>_windows-x86_64-setup.exe` | `SAM_<ver>_macos-arm64.dmg` (Apple silicon) or `…-x86_64.dmg` (Intel) | `SAM_<ver>_linux-x86_64.deb` (or `.AppImage`) | `SAM_<ver>_android.apk` (or `.aab` for Play Store) |
| **Install** | Double-click. No administrator prompt. | Open the DMG, drag **SAM** to Applications. | `.deb`: `sudo apt install ./SAM_*.deb`; AppImage: download and make executable, or use `scripts/install.sh`. | `adb install -r SAM_*.apk` or tap APK on phone |
| **Start** | Start menu → SAM | Applications → SAM | `.deb`: Applications menu; AppImage: run `SAM.AppImage` (installed at `~/.local/bin/SAM.AppImage`). | App launcher → SAM |

Get the files from the project's **Releases** page, or use the one-line
installer, which also verifies the download's SHA-256 checksum:

```bash
# macOS / Linux (Desktop)
curl -fsSL https://raw.githubusercontent.com/dhanushsurada/SAM/main/scripts/install.sh | bash

# Android APK (downloads and installs via adb if phone connected)
curl -fsSL https://raw.githubusercontent.com/dhanushsurada/SAM/main/scripts/install.sh | bash -s -- --android
```
```powershell
# Windows (PowerShell)
irm https://raw.githubusercontent.com/dhanushsurada/SAM/main/scripts/install.ps1 | iex
```

## Android Mobile Installation & Cross-Device Pairing

1. **Install Android APK:**
   - Option A (USB/ADB): Connect phone with USB Debugging enabled, run:
     ```bash
     adb install -r SAM_2.0.0_android.apk
     ```
   - Option B (Direct on Phone): Download `SAM_2.0.0_android.apk` from GitHub Releases in your phone browser, tap the downloaded file, and confirm install.
2. **Permissions:**
   - On first launch, grant **Notifications** (required for task updates).
   - To enable UI automation and app control, grant **Accessibility Service** in Android Settings.
   - To enable phone notification summarization, grant **Notification Access** in Android Settings.
3. **Pair with Desktop:**
   - Ensure phone and desktop are on the same Wi-Fi network (or configure the secure remote relay).
   - In Desktop SAM, navigate to **Settings → Connected Devices → Pair New Device** to display the QR code.
   - In Android SAM, tap **Pair Device** and scan the QR code (or enter the pairing token).
   - Both devices complete an Ed25519 mutual authentication handshake; status changes to **Connected**.

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

## Talking to SAM (voice)

Click the microphone in Chat, the Command Center or the Quick Assistant,
speak, and click it again to send. SAM shows what it heard, does the task and
speaks the answer. Stop cancels the task or playback. Escape cancels voice
work in the main window except when it closes a focused control or dialog; in
Quick Assistant it dismisses the window without cancelling a task SAM has
already accepted.

One-time setup, from **Diagnostics → Installation and recovery**:

- **Install speech-input capability** lets SAM hear you (Whisper).
- **Install speech-output capability** gives SAM its own voice (Kokoro). Until
  it is installed, SAM uses a system voice only when the OS reports it as
  local; otherwise the answer stays on screen.

Voice recordings are retained as task attachments in
`~/.sam_data/iqoo/tasks.db` and are returned by the task API. The API defaults
to listening on all network interfaces, task authentication is optional, and
the HTTP API does not encrypt traffic. Use voice tasks only on a trusted
machine and network until authorization, transport security, and a recording
retention policy are in place.

The first voice message downloads a speech model and the first spoken answer
downloads a voice model, so that first time needs internet and can take a few
minutes. After that, speech runs on your computer. Your operating system asks
for microphone access the first time; if you refused, allow SAM in the
system's microphone privacy settings.
Details and limits: [`docs/voice/PHASE_A_TOUCH_TO_TALK.md`](docs/voice/PHASE_A_TOUCH_TO_TALK.md).

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
git tag v2.0.0 && git push origin v2.0.0      # CI builds + smoke-tests all platforms, drafts a release
```

or locally, on the target OS: `cd interfaces/desktop && npm ci && npm run package`.
Source-based developer setup remains available: `setup.sh` (macOS),
`setup_linux.sh`, `setup_windows.ps1`.
