# SAM Architecture & System Design

SAM is engineered as a sovereign, privacy-first autonomous intelligence machine. It functions without mandatory cloud dependencies or subscription accounts, running completely on your local computer and edge hardware.

```
┌────────────────────────────────────────────────────────────────────────┐
│                        SAM Native Desktop Shell                       │
│        (Tauri v2 + React 18 + TailwindCSS + Glassmorphic UI)           │
├────────────────────────────────────────────────────────────────────────┤
│                       Interfaces & Ingestion                           │
│  ┌──────────────────┐  ┌───────────────────┐  ┌─────────────────────┐  │
│  │  Command Center  │  │ Conversational    │  │ Tasks & Lifecycle   │  │
│  │  & Quick Assistant│ │ Chat (Fork/Retry) │  │ Strip (ReAct Loop)  │  │
│  └──────────────────┘  └───────────────────┘  └─────────────────────┘  │
├────────────────────────────────────────────────────────────────────────┤
│                         Ears & Voice Layer                             │
│  - Wake Word: openWakeWord ("Hey SAM")                                 │
│  - STT: Faster-Whisper (local on-device int8)                          │
│  - TTS: Kokoro 82M (24kHz WAV) + MacAudioGuard hardware un-mute        │
├────────────────────────────────────────────────────────────────────────┤
│                     Core Intelligence & Routing                        │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ Tier 1: Deterministic Fast Reflex (<5ms, media/briefing/audits)  │  │
│  ├──────────────────────────────────────────────────────────────────┤  │
│  │ Tier 2: Local Edge LLM (Ollama - SparkLLM / Qwen 2.5 / DeepSeek) │  │
│  ├──────────────────────────────────────────────────────────────────┤  │
│  │ Tier 3: Frontier Fallback (BYOK OpenRouter / Groq / OpenAI)      │  │
│  └──────────────────────────────────────────────────────────────────┘  │
├────────────────────────────────────────────────────────────────────────┤
│                     Hands & Automation Subsystem                       │
│  - Background Browser: Playwright (Headless non-interfering isolation) │
│  - Native Shell: Sandboxed terminal runner                             │
│  - Screen Vision: Moondream + Window Context Fallback                  │
│  - Verifier: Pre/post state verification with automatic single-retry   │
├────────────────────────────────────────────────────────────────────────┤
│                     Memory & Executive Alignment                       │
│  - SQLite Conversations: Persistent multi-thread chat history          │
│  - Notes Vault: Personal markdown & task plate integration             │
│  - Founder Mode: User taste heuristics, rules, and decision feedback   │
│  - Privacy Redactor: Automated credential and key scrubbing            │
├────────────────────────────────────────────────────────────────────────┤
│                     Connect & Omnichannel Bridges                      │
│  - WhatsApp Bridge: Direct local URL scheme + desktop automation       │
│  - Telegram Bridge: Sovereign long-polling bot tunnel                  │
│  - Android Native: Foreground service + 10 mobile action intents       │
│  - Apple iOS: Siri Shortcuts bridge + Webhook endpoint                │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 1. Desktop Shell & Native Integration
- Built with **Tauri v2** (`sam-desktop`), loading the React 18 single-page application inside a hardware-accelerated WebKit webview.
- **macOS Design Language**: Conforms to Apple Human Interface Guidelines (HIG) with continuous squircle curvature, transparent margins, and native menu bar template icon (`tray.png`) that dynamically inverts for light and dark macOS menu bars.
- **Quick Assistant**: Global shortcut (`Cmd+Shift+Space`) reveals a native HUD palette for rapid voice or text commands without disturbing the user's active window focus.

## 2. Voice Pipeline & Independent Volume
- **Hardware-Independent SAM Volume**: The `MacAudioGuard` AppleScript engine checks macOS master volume and mute state. SAM temporarily un-mutes and adjusts volume for spoken responses, then immediately restores your prior mute and volume settings.
- In-app volume slider (0% to 100%) and mute toggle give complete audio control from inside the application.

## 3. Tiered Execution Router & Reflex Actions
- **Tier 1 (Fast Deterministic Reflex)**: Executes in `<5ms` without LLM token latency for routine actions:
  - Morning executive briefings
  - Platform & profile audits (LinkedIn, GitHub, Twitter) using connected profile context
  - Media controls and application launches
  - Skills scans
- **Tier 2 (Local LLM Inference)**: Executes complex tool planning via local Ollama models with prompt-injected Founder Mode context.
- **Tier 3 (Frontier BYOK Cloud)**: Optional user-supplied API keys (Groq, OpenRouter, Anthropic) for extreme complex reasoning.

## 4. Hands & Desktop Automation
- **Playwright Browser Agent**: Runs in `headless` mode by default, preventing unexpected window popups or stealing mouse focus while you work.
- **Verifier Engine**: Verifies action results before declaring completion, employing automated single-retry self-healing on transient glitches.
- **Graceful Vision Fallback**: Screen perception smoothly falls back to macOS window inspection if screen recording permissions are restricted.

## 5. Omnichannel Mobile Continuity
- Enables remote commands and audits from **WhatsApp**, **Telegram**, **Android Companion App**, and **iOS Siri Shortcuts**.
- Security is guaranteed through **Ed25519 pairing tokens**, canonical request signing, and replay protection windows.
