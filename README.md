# SAM 2.0 — Sovereign Autonomous Mind

**Self-learning Autonomous Mind with Multi-Tier Intelligence, Founder Mode Taste Heuristics & Cross-Device Coordination**

> Fully local · Privacy-first · Desktop (macOS / Windows / Linux) + Android · Voice & Text · Zero Cloud Dependency

[![CI](https://github.com/dhanushsurada/SAM/actions/workflows/ci.yml/badge.svg)](https://github.com/dhanushsurada/SAM/actions/workflows/ci.yml)
[![Version](https://img.shields.io/badge/version-2.1.1-blue.svg)](https://github.com/dhanushsurada/SAM/releases)
[![Tests](https://img.shields.io/badge/python%20tests-491%20passed-brightgreen.svg)](tests/)
[![Frontend Tests](https://img.shields.io/badge/frontend%20tests-118%20passed-brightgreen.svg)](interfaces/desktop/)
[![Android Tests](https://img.shields.io/badge/android%20tests-78%20passed-brightgreen.svg)](sam-android/)
[![License](https://img.shields.io/badge/license-AGPL%20v3-orange.svg)](LICENSE)

---

## What SAM 2.0 Does

- **Unified Cross-Device Intelligence:** Seamlessly bridges your Desktop (macOS, Windows, Linux) and Android companion with capability-based routing and synchronized state.
- **System 1 Streaming Reflex Engine with JEV Integration:** Evaluates speech mid-sentence in sub-80ms to trigger speculative app launching, window focusing, and web search *before* you finish speaking.
  - *Leap-Ahead:* **Speculative Context Injection** — pre-fetches notes and agenda into the Brain's prompt buffer while you speak, slashing time-to-first-token.
- **Autonomous Morning Briefing & Daily Digest (`sam briefing`):** Aggregates Calendar, Mail, daily Notes, and weather into spoken and executive markdown briefings without cloud subscriptions.
  - *Leap-Ahead:* **Proactive Actionable Agenda Optimizer** — analyzes schedule conflicts, schedules deep-work focus blocks, and auto-stages meeting windows 5 minutes in advance.
- **Local Notes Vault & Personal Memory (`sam notes`):** "My own notes are the memory." Indexes local markdown vaults (Obsidian / local notes) to answer "what's on my plate from my real life".
  - *Leap-Ahead:* **Bidirectional Note Auto-Log** — automatically logs completed actions, decisions, and outcomes into today's daily note under `# SAM Activity Log`.
- **Multi-Engine Hardware & Energy Profiler (`sam hardware`):** Auto-detects Apple Silicon Metal, NVIDIA CUDA, and CPU runtimes, probing Ollama, vLLM, llama.cpp, and SGLang.
  - *Leap-Ahead:* **Constraint-Aware Intelligence Per Watt** — profiles energy consumption (Joules/token), token throughput (tokens/sec), and memory footprint.
- **OpenAI-Compatible Local Server (`sam serve`):** Exposes standard `/v1/chat/completions` and `/v1/models` endpoints with streaming support so Claude Code, Cursor, and Open-WebUI can connect directly.
- **Modern Minimalist Desktop Interface:** Fast, distraction-free desktop application (Tauri v2 + React) with parallel chat threads, global Command Center palette (`Cmd+Shift+Space`), live system diagnostics, and zero branding.
- **3-Tier Execution Architecture:**
  - **Tier 1 (Direct Deterministic):** Sub-5ms execution for math calculations, application launch/close, morning briefings, notes plate queries, WhatsApp direct messaging, YouTube playback, URL navigation, and screenshots without unnecessary LLM overhead.
  - **Tier 2 (Fast Intent):** Fast single-step tool selection and device routing using compact local models.
  - **Tier 3 (Advanced Reasoning):** Deep multi-step planning, iterative execution, verification, and error recovery.
- **Native Android Companion (`sam-android`):** Kotlin Jetpack Compose app featuring Ed25519 pairing, on-device mobile AI inference, Scoped Storage file sync, notification mirroring, and a 10-action task executor (`AndroidConnectTaskExecutor`).
- **Cryptographic Security & Verification:** Mutual Ed25519 request signing, one-time pairing tokens, sliding nonce replay-prevention, 60s execution leases (`ExecutionLease`), and offline task queueing (`queued_offline`) with reconnect de-duplication.
- **Voice, Ears & Mouth:** 24/7 background listening with openWakeWord ("Hey SAM"), Faster-Whisper on-demand STT, and Kokoro 82M neural TTS with in-app Web Audio playback.
- **Founder Mode & Taste Heuristics:** Persistent SQLite + ChromaDB memory with **Founder Mode** capturing your taste, rationale, rules, and permanent rejections across sessions.
- **Model Context Protocol (MCP) & BYOK:** Plug-and-play integrations with GitHub, Slack, local filesystems, and PostgreSQL databases, plus optional frontier cloud API keys (Groq, Gemini, Anthropic, OpenRouter) with automatic fallback to local Ollama.
- **Zero Cloud by Default:** All core intelligence runs fully on your local machine.

---

## Hardware Requirements

| Component | Minimum | Recommended |
|---|---|---|
| **Desktop OS** | macOS 14+ (Apple Silicon / Intel) · Windows 10/11 · Ubuntu/Debian (x86_64) | macOS Apple Silicon (M2/M3/M4) / Windows 11 |
| **Mobile OS** | Android 8.0+ (API 26) | Android 12+ (Snapdragon / Tensor SoC) |
| **Desktop CPU** | Any 64-bit CPU | Apple Silicon (M-series) or modern x86_64 |
| **RAM** | 8GB (compact 4B models) | 16GB+ (default 14B models) |
| **Free Storage** | 20GB free | 50GB+ for multiple local models |

---

## Installation & Updates

### Pre-built Installers (Version 2.1.1)

Download verified installers directly from the [GitHub Releases](https://github.com/dhanushsurada/SAM/releases) page:

| macOS 14+ | Windows 10/11 | Linux (Ubuntu/Debian) | Android Mobile |
|---|---|---|---|
| `SAM_2.1.1_macos-arm64.dmg`<br>`SAM_2.1.1_macos-x86_64.dmg` | `SAM_2.1.1_windows-x86_64-setup.exe` | `SAM_2.1.1_linux-x86_64.deb`<br>`SAM_2.1.1_linux-x86_64.AppImage` | `SAM_2.1.1_android.apk`<br>`SAM_2.1.1_android.aab` |
| Drag to `/Applications` | Run setup executable | `sudo apt install ./SAM_*.deb` | Tap APK or `adb install -r` |

### One-Line Automated Installer & Updater

The automated installer downloads the release for your operating system, cryptographically verifies its SHA-256 checksum against `SHA256SUMS.txt`, and installs or updates SAM:

```bash
# macOS & Linux Desktop (Fresh install or update to latest)
curl -fsSL https://raw.githubusercontent.com/dhanushsurada/SAM/main/scripts/install.sh | bash

# Android (Downloads latest APK and installs via adb if phone is connected)
curl -fsSL https://raw.githubusercontent.com/dhanushsurada/SAM/main/scripts/install.sh | bash -s -- --android

# Windows (PowerShell)
irm https://raw.githubusercontent.com/dhanushsurada/SAM/main/scripts/install.ps1 | iex
```

SAM bundles its own managed Python runtime. The only prerequisite for local inference is [Ollama](https://ollama.com). See **[INSTALL.md](INSTALL.md)** for detailed environment troubleshooting.

---

## Developer Setup & Building from Source

```bash
# 1. Clone repository
git clone https://github.com/dhanushsurada/SAM.git
cd SAM

# 2. Setup Python environment and install dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. Build Desktop Frontend
cd interfaces/desktop
npm install
npm test          # Runs 118 unit tests
npm run build     # Production Vite build
cd ../..

# 4. Run Python Verification Suite
python -m pytest tests -q --ignore=tests/test_founder_mode_live.py --ignore=tests/test_sovereign_e2e_live.py
```

---

## Running SAM

### 1. Launch the Desktop Application
Open **SAM.app** from `/Applications` (or start via application launcher on Windows/Linux). The desktop shell automatically starts and monitors the local SAM API and worker processes.

### 2. Command Line Development
```bash
source .venv/bin/activate

# Run health diagnostics
python sam_cli.py doctor

# Start backend services manually
python sam_cli.py start api
python sam_cli.py start voice
```

### 3. Voice Interaction
Say: **"Hey SAM"**  
- On first start, SAM loads the configured local brain model and announces *"SAM is ready."*
- Responses are delivered with low latency via Kokoro TTS through the desktop Web Audio pipeline.
- Say *"SAM sleep"* to unload model weights from RAM, or *"SAM stop"* to shut down.

---

## 3-Tier Execution Reference

SAM eliminates unnecessary LLM calls by routing instructions according to complexity:

| Tier | Typical Latency | Examples | Mechanism |
|---|---|---|---|
| **Tier 1 (Direct)** | `< 5ms` | "open Chrome", "calculate 125 * 8", "open youtube and play aya sher", "take a screenshot", "text Alice 'Hello' on WhatsApp" | Deterministic pattern match & OS AppleScript/PyAutoGUI automation |
| **Tier 2 (Fast Intent)** | `< 800ms` | "what is the weather today?", "find my notes about budget", "list mobile notifications" | Fast single-step tool execution with compact local model |
| **Tier 3 (Advanced)** | `1.5s - 5s` | "organize my downloads folder, summarize invoices, and email the report" | ReAct planning loop with step-by-step verification and error recovery |

---

## Cross-Device Actions Matrix (`AndroidConnectTaskExecutor`)

When paired via SAM Connect, the desktop coordinator can dispatch tasks across 10 specialized Android capabilities:

| Action | Description | Android Execution Mechanism |
|---|---|---|
| `show_notification` | Displays high-priority private notification on device | `SamNotifications` / `NotificationManagerCompat` |
| `app_launch` | Launches mobile app by common name or Android package | `AndroidAppLauncher` intent dispatch |
| `view_url` | Opens web URL in default mobile browser | `Intent.ACTION_VIEW` |
| `share_content` | Sends text or link into Android system share sheet | `Intent.ACTION_SEND` chooser |
| `get_notifications` | Reads active notifications for cross-device summarization | `SamNotificationListener` |
| `accessibility_click` | Clicks accessibility node by target text or screen coordinates | `SamAccessibilityService` node inspection |
| `accessibility_type` | Types text into the currently focused input field | `AccessibilityNodeInfo.ACTION_SET_TEXT` |
| `accessibility_action` | Navigates Back, Home, or Recents on the phone | `performGlobalAction` |
| `receive_file` | Writes incoming file with SHA-256 integrity validation | `SamFileManager` Scoped Storage engine |
| `local_infer` | Runs on-device mobile AI inference with latency & token metrics | `SamMobileInferenceEngine` |

---

## CLI Management Reference (`sam_cli.py`)

`sam_cli.py` provides complete diagnostic, process, memory, and device management:

```bash
# Diagnostics & System Health
python sam_cli.py doctor                  # Run full diagnostic suite
python sam_cli.py status                  # Inspect active SAM processes & Ollama health

# Service Lifecycle
python sam_cli.py start [voice|api|telegram]   # Start managed service
python sam_cli.py stop [voice|api|telegram]    # Stop service gracefully
python sam_cli.py restart [voice|api|telegram] # Restart service

# OpenJarvis & JEV Reflex Extensions
python sam_cli.py briefing                # Generate executive morning briefing (Calendar + Mail + Notes)
python sam_cli.py briefing --speak        # Spoken morning briefing via Kokoro TTS
python sam_cli.py notes                   # Query 'what is on my plate from my real life' (local vault)
python sam_cli.py hardware                # Inspect Apple Silicon Metal / CUDA hardware & probe engines
python sam_cli.py serve --port 8420       # Launch OpenAI-compatible API server (/v1/chat/completions)

# Local Model Control
python sam_cli.py ollama status           # Check Ollama connection & pulled models
python sam_cli.py ollama pull <model>     # Pull a new local LLM (e.g. qwen2.5:14b)

# Cross-Device & Pairing
python sam_cli.py devices                 # List trusted paired devices (phones, laptops)
python sam_cli.py revoke-device <id>      # Instantly revoke trust for a paired device

# Memory & Founder Mode
python sam_cli.py memory --limit 10       # View recent episodic memories
python sam_cli.py founder                 # View Founder Mode decisions & taste profile
python sam_cli.py decision "Title" "Why"  # Record a founder decision with rationale
python sam_cli.py rejection "Title" "Why" # Record a founder rejection with rationale
python sam_cli.py skills                  # List auto-compiled task execution skills

# Maintenance & Reset
python sam_cli.py export-profile <path>   # Export personal profile & memory archive
python sam_cli.py import-profile <path>   # Restore personal profile
python sam_cli.py sync-status             # Inspect cross-device sync state
python sam_cli.py logs --lines 50         # View latest runtime logs
python sam_cli.py reset-memory            # Clear episodic memory (retains identity)
python sam_cli.py reset-all               # Factory reset SAM local data
```

---

## System Architecture

```
SAM/
├── main.py                  ← Cross-device entry point & dispatch coordinator
├── sam_cli.py               ← Comprehensive CLI management & diagnostic tool
├── core/
│   ├── jev_reflex_engine.py ← Sub-80ms streaming reflex & speculative context injection
│   ├── briefing_agent.py    ← Autonomous morning briefing & agenda optimizer
│   ├── engine_manager.py    ← Multi-engine hardware probe & Intelligence-Per-Watt profiler
│   ├── tiered_router.py     ← 3-tier execution optimizer (Tier 1 sub-5ms bypass)
│   ├── brain.py             ← Ollama Brain integration
│   ├── model_manager.py     ← Dynamic model discovery & RAM-tier selection
│   ├── cloud_providers.py   ← Frontier BYOK provider fallback (Groq, Anthropic, etc.)
│   ├── instrumentation.py   ← Performance telemetry (TTFT, LLM ms, tool ms)
│   └── session.py           ← Context assembly & session state
├── connect/
│   ├── services/
│   │   ├── coordinator.py   ← Cross-device coordinator with 60s execution leases
│   │   ├── task_handoff.py  ← Device task router, offline queue & state machine
│   │   └── workflows.py     ← End-to-end multi-device workflow recipes
│   ├── transports/
│   │   └── lan_http.py      ← Authenticated LAN HTTP & SSE with Ed25519 signatures
│   ├── bridges/
│   │   └── remote_relay.py  ← Outbound-only TLS 1.3 / WSS remote relay client
│   └── core/
│       ├── crypto.py        ← Asymmetric Ed25519 identity & canonical signing
│       ├── device_registry.py ← SQLite device registry & connection state tracking
│       ├── security_policy.py ← 3-tier risk classification & approval gating
│       └── capabilities.py  ← Central capability discovery & registry
├── sam-android/             ← Native Android mobile companion (Kotlin + Jetpack Compose)
│   ├── app/src/main/
│   │   ├── ai/              ← On-device mobile AI (LiteRT / llama.cpp / GGUF)
│   │   ├── automation/      ← SamFileManager, AppLauncher, Accessibility & Notifications
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
│   ├── notes_vault.py       ← Local markdown vault & bidirectional auto-log
│   ├── store.py             ← ChromaDB embeddings + SQLite episodic storage
│   └── retrieve.py          ← Semantic vector memory search
└── interfaces/
    └── desktop/             ← Tauri v2 cross-platform desktop frontend
```

---

## Documentation

Comprehensive product and technical documentation is organized in the [`docs/`](docs/README.md) directory:

- 📖 **[Master Documentation Index](docs/README.md)** — Overview of all system manuals, guides, and specifications.
- 💡 **[Product User Guide](docs/USER_GUIDE.md)** — Consumer guide for Chat with prompt editing, Command Center, and Task execution.
- 🏗 **[System Architecture](docs/ARCHITECTURE.md)** — Detailed technical design across Desktop, Brain, Hands, Voice, and Security.
- 🗺 **[Product Roadmap](docs/ROADMAP.md)** — Current capabilities and future horizons for `v2.1.1` and beyond.
- 📱 **[Mobile Setup & Bridges Guide](docs/guides/MOBILE_SETUP_AND_COMMANDS_GUIDE.md)** — Step-by-step setup for WhatsApp, Telegram, Android, and iOS.
- ✅ **[Feature Acceptance Checklist](docs/FEATURE_ACCEPTANCE_CHECKLIST.md)** — Feature status and verification matrix.

---

## Verification & Status

For detailed feature-by-feature classification across 🟢 **Verified**, 🟡 **Implemented (Unverified)**, and 🔴 **Not Implemented**, consult the **[Feature Acceptance Checklist](docs/FEATURE_ACCEPTANCE_CHECKLIST.md)**.

### Automated Test Suite Baseline
- **Python Backend:** `491 passed, 0 failed` in `pytest`.
- **Desktop Frontend:** `118 passed, 0 failed` in `node --test`.
- **Desktop Production Build:** Clean build via `tsc -b && vite build`.
- **Android JVM Unit Tests:** `78 passed, 0 failed` in `./gradlew testDebugUnitTest`.

---

## Privacy Principles

- **Zero Cloud by Default:** All AI inference, embeddings, and conversation histories remain strictly on your own hardware.
- **Incognito Mode:** Zero trace execution — no queries or memories are stored in incognito sessions.
- **Local Data Separation:** User account/device metadata and AI data (conversations, Founder Mode) are isolated locally in dedicated databases.
- **Open Source:** AGPL v3 license. Every line of code is inspectable and auditable.

---

## License

AGPL v3 for open source use.  
Commercial licenses available for proprietary integrations.

---

## Author & Acknowledgements

Developed by **Dhanush Surada** — Visakhapatnam, India  
GitHub: [github.com/dhanushsurada](https://github.com/dhanushsurada) · LinkedIn: [linkedin.com/in/dhanushsurada](https://www.linkedin.com/in/dhanushsurada)
