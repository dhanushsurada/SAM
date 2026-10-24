# SAM — Personal AI Assistant

**Self-learning Autonomous Mind with Hermes Intelligence & Taste Heuristics Architecture**

> Fully local · Privacy-first · Voice-controlled · Self-improving · Founder Mode

---

## What SAM Does

- Listens for your wake word 24/7 at near-zero CPU cost
- Understands your speech via Whisper STT
- Thinks with Qwen 2.5 14B running entirely on your machine
- Speaks back with Kokoro TTS
- Controls your Mac — mouse, keyboard, apps, browser, terminal
- Remembers everything across sessions via ChromaDB + SQLite
- Learns your taste, decisions, and reasoning via **Founder Mode**
- Zero cloud. Zero API keys. Zero subscription.

---

## Hardware Requirements

| Component | Minimum | Recommended |
|---|---|---|
| OS | Windows 10/11 · macOS 14+ · Ubuntu/Debian (x86_64) | latest |
| Chip | Any 64-bit CPU (Apple silicon recommended on Mac) | M2/M3 or modern x86 |
| RAM | 8GB (small models) | 16GB+ (14B default model) |
| Storage | 20GB free | 50GB+ for several models |

---

## Install

**Download the installer for your OS — no Python, Node, Rust or Git needed.**

| Windows 10/11 | macOS 14+ | Linux (Ubuntu/Debian) |
|---|---|---|
| `…-setup.exe` — double-click | `.dmg` — drag to Applications | `.deb` — `sudo apt install ./SAM_*.deb` |

Get them from the **Releases** page, or run the one-liner (verifies SHA-256):

```bash
curl -fsSL https://raw.githubusercontent.com/dhanushsurada/SAM/main/scripts/install.sh | bash   # macOS / Linux
irm https://raw.githubusercontent.com/dhanushsurada/SAM/main/scripts/install.ps1 | iex          # Windows
```

SAM bundles its own Python runtime; first launch guides you through installing
Ollama and choosing a model. Full guide, first-run walkthrough, updating,
uninstalling and troubleshooting: **[INSTALL.md](INSTALL.md)**.

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

```bash
# Status check
python sam_cli.py status

# View logs (last 50 lines)
python sam_cli.py logs

# View recent memories
python sam_cli.py memory

# View Founder Mode
python sam_cli.py founder

# List compiled skills
python sam_cli.py skills

# Export Founder Mode to JSON
python sam_cli.py export
```

---

## Architecture

```
SAM/
├── main.py              ← Entry point
├── sam_cli.py           ← CLI management tool
├── setup.sh             ← One-command setup
├── requirements.txt     ← Python dependencies
├── config/
│   ├── settings.py      ← All config with auto-detection
│   └── settings.yaml    ← Override any setting here
├── ears/
│   ├── wake_word.py     ← openWakeWord (24/7, ~0% CPU)
│   └── stt.py           ← Whisper STT (activates on wake)
├── core/
│   ├── brain.py         ← The selected local model via Ollama (default Qwen 2.5 14B)
│   ├── model_manager.py ← Discover installed models, compatibility, validated selection
│   └── session.py       ← Session context management
├── mouth/
│   └── tts.py           ← Kokoro TTS + Piper fallback
├── hands/
│   ├── control/         ← PyAutoGUI + AppleScript
│   ├── vision/          ← Moondream screen reader
│   ├── browser/         ← Playwright browser agent
│   └── terminal/        ← Sandboxed terminal runner
├── memory/
│   ├── identity.py      ← User profile (always loaded)
│   ├── store.py         ← ChromaDB + SQLite write
│   └── retrieve.py      ← Semantic memory search
├── founder_mode/
│   └── manager.py       ← Decisions, rejections, taste profile
├── agent/
│   └── react_loop.py    ← ReAct multi-step task execution
├── skills/
│   └── compiler.py      ← Auto-compiles repeated tasks
└── logs/                ← Runtime logs
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
