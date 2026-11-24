# SAM Documentation Index

**SAM (Sovereign Autonomous Machine)** is a private, local-first autonomous AI operating system designed to execute complex computer tasks, provide real-time conversational intelligence, and bridge seamlessly across mobile devices (Android, iPhone, WhatsApp, Telegram).

---

## 📚 Core Documentation

| Document | Description |
|---|---|
| [System Architecture](ARCHITECTURE.md) | Complete end-to-end design: Desktop Shell, Brain, Hands, Connect, Voice, Memory, and Security |
| [Product User Guide](USER_GUIDE.md) | Consumer guide: Command Center, Conversational Chat with prompt editing, Task execution, Voice volume controls |
| [Product Roadmap](ROADMAP.md) | Live release roadmap for `v2.1.1` and future capabilities without obsolete sprint tags |
| [Mobile Setup & Bridge Guide](guides/MOBILE_SETUP_AND_COMMANDS_GUIDE.md) | Setup instructions for WhatsApp, Telegram, Android, and iOS Shortcuts |
| [Feature Acceptance Checklist](FEATURE_ACCEPTANCE_CHECKLIST.md) | Comprehensive engineering checklist and verification matrix |
| [Desktop Installation](deployment/DESKTOP_INSTALL.md) | macOS and cross-platform installation and setup instructions |
| [Local Runtime Guide](deployment/LOCAL_RUNTIME.md) | Embedded Python runtime, Ollama model management, and background services |

---

## 🏛 Subsystem Architecture

- **[Brain & Reasoning](architecture/RUNTIME.md)**: Local LLM orchestration (Ollama), 3-tier execution router, and optional cloud fallbacks.
- **[Hands & Desktop Control](architecture/ENVIRONMENT_COMPATIBILITY.md)**: Headless/headed Playwright browser agent, native terminal execution, vision screen reader, and verified execution.
- **[Cross-Device Continuity](architecture/UNIFIED_CROSS_DEVICE_ARCHITECTURE.md)**: Ed25519 pairing, LAN discovery, execution leases, and mobile handoff.
- **[Sovereign Security](architecture/CROSS_DEVICE_PROTOCOL.md)**: Network egress proof, socket guards, document trust boundaries, and automatic credential redaction.

---

## 🗄 Historical Archives

Internal developer sprint plans and preliminary logs are archived in [archive/historical_phases/](archive/historical_phases/).
