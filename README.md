# SAM 2.0 — Unified Cross-Device AI Assistant

**Self-learning Autonomous Mind with Hermes Intelligence, Taste Heuristics & Cross-Device Coordination**

> Fully local · Privacy-first · Desktop + Android · Voice & Text · Zero Cloud Dependency

---

## What SAM 2.0 Does

- **Unified Cross-Device Intelligence:** Seamlessly bridges your Desktop (macOS, Windows, Linux) and Android mobile device with shared memory and automatic capability routing.
- **3-Tier Execution Architecture:**
  - **Tier 1 (Direct Deterministic):** Sub-5ms execution for calculations, app launches, browser navigation, and screenshots without unnecessary LLM calls.
  - **Tier 2 (Fast Intent):** Fast single-step tool selection and routing using compact models.
  - **Tier 3 (Advanced Reasoning):** Deep multi-step planning, reflection, and recovery with Qwen 2.5 14B.
- **Native Android Agent:** Native Kotlin Jetpack Compose app with on-device AI inference, Scoped Storage file sync, accessibility automation, and notification summarization.
- **Cryptographic Security:** Mutual Ed25519 request signing, one-time QR pairing, sliding replay-prevention nonces, and user confirmation gating for destructive actions.
- **Voice & Hands Automation:** openWakeWord 24/7 listening, Whisper STT, Kokoro TTS, Playwright browser agent, and AppleScript/system automation.
- **Taste & Memory Layer:** ChromaDB + SQLite episodic memory with **Founder Mode** capturing your taste, decisions, and reasoning across sessions.
- **Zero Cloud.** Zero API keys. Zero subscription fees.

---

## Hardware Requirements

| Component | Minimum | Recommended |
|---|---|---|
| Desktop OS | Windows 10/11 · macOS 14+ · Ubuntu/Debian (x86_64) | macOS Apple Silicon / Windows 11 |
| Mobile OS | Android 8.0+ (API 26) | Android 12+ (Snapdragon / Tensor SoC) |
| Desktop Chip | Any 64-bit CPU (Apple Silicon recommended on Mac) | M2/M3/M4 or modern x86-64 |
| RAM | 8GB (small models) | 16GB+ (14B default model) |
| Storage | 20GB free | 50GB+ for several models |

---

## Install

**Download the installer for your platform — no Python, Node, Rust or Git needed.**

| Windows 10/11 | macOS 14+ | Linux (Ubuntu/Debian) | Android Mobile |
|---|---|---|---|
| `SAM_2.0.0_windows-x86_64-setup.exe` | `SAM_2.0.0_macos-arm64.dmg` / `…-x86_64.dmg` | `SAM_2.0.0_linux-x86_64.deb` | `SAM_2.0.0_android.apk` |
| Double-click to install | Drag to Applications | `sudo apt install ./SAM_*.deb` | `adb install -r SAM_*.apk` or tap APK |

Get them from the **Releases** page, or use the one-line installer (verifies SHA-256):

```bash
# Desktop (macOS / Linux)
curl -fsSL https://raw.githubusercontent.com/dhanushsurada/SAM/main/scripts/install.sh | bash

# Android (Downloads APK & installs via adb if phone connected)
curl -fsSL https://raw.githubusercontent.com/dhanushsurada/SAM/main/scripts/install.sh | bash -s -- --android

# Windows (PowerShell)
irm https://raw.githubusercontent.com/dhanushsurada/SAM/main/scripts/install.ps1 | iex
```

SAM bundles its own Python runtime. The only prerequisite is [Ollama](https://ollama.com) for local models. Full guide: **[INSTALL.md](INSTALL.md)**.

### Developers

Build from source with `setup.sh` (macOS), `setup_linux.sh` (Debian/Ubuntu
backend) or `setup_windows.ps1`, or build the installers yourself — see
[`docs/deployment/DESKTOP_INSTALL.md`](docs/deployment/DESKTOP_INSTALL.md).

---

## Running SAM

### Start SAM

```bash
# For command-line development only; the installed desktop app starts the API.
source .venv/bin/activate

# Start the separate voice loop manually
python main.py
```

The desktop app starts and manages the SAM API. “Open SAM at login” is
controlled from Settings; setup does not install a second launchd manager.

### Wake SAM

Say: **"Hey SAM"**

First time after boot: SAM loads Qwen (~20 seconds). Says *"SAM is ready."*

After first load: responds immediately until you say *"SAM sleep"* or shut down.

---

## Voice Commands

| You say | SAM does |
|---|---|
| "Hey SAM, what's 15% of 3400?" | Calculates and tells you |
| "Hey SAM, open Safari" | Opens Safari via AppleScript |
| "Hey SAM, take a screenshot" | Takes screenshot |
| "Hey SAM, read my screen" | Describes what's on screen |
| "Hey SAM, go to github.com" | Opens URL in browser |
| "Hey SAM, run ls in terminal" | Executes terminal command |
| "Hey SAM, incognito mode" | Switches to incognito — nothing stored |
| "Hey SAM, exit incognito" | Back to normal mode |
| "model" / "model qwen3:8b" | Shows the Brain and installed models / switches the Brain (saved for next start) |
| "SAM sleep" | Unloads model from RAM |
| "SAM stop" | Shuts down completely |

---

## Founder Mode

Founder Mode is SAM's taste layer — the feature no competitor has.

Every time you:
- Reject something and explain why → stored permanently
- Make a decision → stored with your reasoning
- Express a preference → captured

Next session SAM starts already knowing your taste.

### Manual Founder Mode CLI

```bash
# Add a decision
python sam_cli.py decision "Using FastAPI over Flask" "Django is overkill for skill endpoints, FastAPI is faster" --category tech

# Add a rejection
python sam_cli.py rejection "Dark mode with pure black background" "Too harsh on eyes, prefer dark grey #1a1a1a" --category design

# View all decisions
python sam_cli.py founder

# Export full decision log
python sam_cli.py export
```

---

## CLI Reference

`sam_cli.py` provides complete runtime, diagnostic, process, memory, and device management:

```bash
# System Diagnostics & Health Check
python sam_cli.py doctor                  # Run full diagnostic suite
python sam_cli.py status                  # Inspect active SAM processes & Ollama health

# Process Lifecycle Management
python sam_cli.py start [voice|api|telegram]   # Start managed service (or all)
python sam_cli.py stop [voice|api|telegram]    # Stop service gracefully
python sam_cli.py restart [voice|api|telegram] # Restart service

# Local Model & Ollama Control
python sam_cli.py ollama status           # Check Ollama connection & pulled models
python sam_cli.py ollama pull <model>     # Pull a new local LLM (e.g. qwen2.5:14b)

# Cross-Device & Pairing Management
python sam_cli.py devices                 # List trusted paired devices (phones, laptops)
python sam_cli.py revoke-device <id>      # Instantly revoke trust for a paired device

# Memory & Founder Mode
python sam_cli.py memory --limit 10       # View recent episodic memories
python sam_cli.py founder                 # View Founder Mode decisions & taste profile
python sam_cli.py skills                  # List auto-compiled task execution skills

# Profile Portability & Maintenance
python sam_cli.py export-profile <path>   # Export personal profile & memory archive
python sam_cli.py import-profile <path>   # Restore personal profile
python sam_cli.py sync-status             # Inspect cross-device sync state
python sam_cli.py logs --lines 50         # View latest runtime logs
python sam_cli.py reset-memory            # Clear episodic memory (retains identity)
python sam_cli.py reset-all               # Factory reset SAM data
```

---

## Architecture

```
SAM/
├── main.py                  ← Cross-device entry point & dispatch chokepoint
├── sam_cli.py               ← Comprehensive CLI management & diagnostic tool
├── core/
│   ├── tiered_router.py     ← 3-tier execution optimizer (Tier 1 sub-5ms bypass)
│   ├── brain.py             ← Ollama Brain integration (Qwen 2.5 14B default)
│   ├── model_manager.py     ← Dynamic model discovery & RAM-tier selection
│   ├── instrumentation.py   ← Performance telemetry (TTFT, LLM ms, tool ms)
│   └── session.py           ← Context assembly & session state
├── connect/
│   ├── services/
│   │   ├── coordinator.py   ← Cross-device coordinator with 60s execution leases
│   │   ├── task_handoff.py  ← Device task router & handoff state machine
│   │   └── workflows.py     ← End-to-end multi-device workflow recipes
│   ├── transports/
│   │   └── lan_http.py      ← Authenticated LAN HTTP & SSE with Ed25519 signatures
│   ├── bridges/
│   │   └── remote_relay.py  ← Outbound-only TLS 1.3 / WSS remote relay client
│   └── core/
│       ├── crypto.py        ← Asymmetric Ed25519 identity & canonical signing
│       ├── security_policy.py ← 3-tier risk classification & approval gating
│       ├── shared_memory.py ← Scoped memory sync with vector clocking
│       └── capabilities.py  ← Central capability discovery & registry
├── sam-android/             ← Native Android mobile agent (Kotlin + Jetpack Compose)
│   ├── app/src/main/
│   │   ├── ai/              ← On-device mobile AI (LiteRT / llama.cpp / GGUF)
│   │   ├── automation/      ← AccessibilityService & NotificationListener
│   │   ├── data/transport/  ← OkHttp SSE client & Ed25519 identity store
│   │   └── ui/              ← Compose screens (Pairing, Chat, Diagnostics)
├── hands/
│   ├── control/             ← PyAutoGUI + AppleScript OS automation
│   ├── vision/              ← Moondream screen reader & OCR
│   ├── browser/             ← Playwright browser agent (with system fallback)
│   └── terminal/            ← Sandboxed terminal runner
├── ears/
│   ├── wake_word.py         ← openWakeWord (24/7 background listener)
│   └── stt.py               ← Whisper STT engine
├── mouth/
│   └── tts.py               ← Kokoro TTS + Piper fallback
├── founder_mode/
│   └── manager.py           ← Taste heuristics, decisions & permanent rejections
├── memory/
│   ├── store.py             ← ChromaDB embeddings + SQLite episodic storage
│   └── retrieve.py          ← Semantic vector memory search
└── interfaces/
    └── desktop/             ← Tauri v2 cross-platform desktop frontend
```

---

## Session Flow

```
Boot → openWakeWord starts (always on, ~0% CPU)
     ↓
"Hey SAM" detected
     ↓
Whisper STT activated → transcribes speech
     ↓
Identity loaded + memories retrieved + Founder Mode context injected
     ↓
Qwen 2.5 14B processes full context
     ↓
Agent decides: conversation | control | browser | terminal | vision
     ↓
Action executed (if needed) → observed → next step decided (ReAct)
     ↓
Kokoro TTS speaks response
     ↓
Memory extracted + saved
     ↓
Back to listening
```

---

## Privacy

- **Zero cloud.** Nothing leaves your machine. Ever.
- **Incognito mode.** Cryptographically no storage — not even locally.
- **Your data is yours.** All memory in local SQLite + ChromaDB.
- **Open source.** AGPL v3. Audit every line.

---

## License

AGPL v3 for open source use.
Commercial license available for products built on SAM.

---

## Built By

Dhanush Surada — Visakhapatnam, India
github.com/dhanushsurada | linkedin.com/in/dhanushsurada

Waitlist: smtg-is-cmg.carrd.co
