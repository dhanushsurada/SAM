# SAM Product Roadmap & Release Status

**Current Version:** `v2.1.1`  
**License:** Sovereign Commercial & Private Developer Edition  
**Repository:** [github.com/dhanushsurada/SAM](https://github.com/dhanushsurada/SAM)

---

## 🚀 Shipped & Live in `v2.1.1`

### 1. Native Desktop Shell & Apple HIG Design
- [x] **macOS HIG Squircle App Icon**: Native rounded squircle with transparent margins, continuous curvature, and Display P3 wide color gamut.
- [x] **System-Adaptive Menu Bar Tray Icon**: Dedicated monochrome alpha-template icon (`tray.png`) that dynamically inverts for macOS Light and Dark menu bars.
- [x] **Glassmorphic Multi-Theme System**: 6 translucent presets (Obsidian Frost, Ice Cyan, Sage Emerald, Lavender Haze, Titanium Slate, Warm Amber).
- [x] **Clean Consumer UI**: Complete removal of internal development sprint terminology across all production screens.

### 2. Conversational Chat & Prompt Management
- [x] **Inline Prompt Editing**: Click "Edit" on any sent user prompt, modify text inline, and press `⌘ Enter` to fork and regenerate.
- [x] **Regenerate / Retry**: One-click regeneration on assistant responses.
- [x] **Reuse in Composer**: One-click quote/reuse of previous prompts.
- [x] **Queued Task Editing**: Edit prompt instructions while tasks are queued and immediately execute updated instructions.

### 3. Voice & Audio Architecture
- [x] **MacAudioGuard Independent Audio**: System-independent in-app volume slider (0% to 100%) and mute toggle.
- [x] **Hardware Silent Mode Override**: Temporarily un-mutes macOS hardware during speech synthesis and seamlessly restores the prior volume and mute status immediately upon completion.
- [x] **openWakeWord & Kokoro TTS**: Sub-100ms wake word activation with 24kHz neural speech.

### 4. Core Intelligence & Autonomous Automation
- [x] **Tier 1 Reflex Router**: Sub-5ms instant execution for morning briefings, profile audits, and media control.
- [x] **Connected Platform Audits**: Deep growth analysis, reach velocity, connection-to-follower ratios, and 7-day maintenance roadmaps without prompting for URLs.
- [x] **Isolated Background Browser**: Headless Playwright automation that runs without stealing mouse focus or popping up windows over the user's active work.
- [x] **Privacy Redaction Engine**: Automated scrubbing of API keys, bearer tokens, JWTs, and passwords from execution logs.

### 5. Omnichannel Mobile Continuity
- [x] **Omnichannel Bridges**: WhatsApp, Telegram, Android Companion, and iOS Siri Shortcuts.
- [x] **Ed25519 Device Cryptography**: Tamper-proof hardware pairing and execution leases.

---

## 🔮 Upcoming Capabilities & Future Horizons

1. **Document Ingestion & Local Semantic Graph**:
   - Deep vector indexing across local PDF, docx, and markdown directories with cross-reference citations.
2. **Recurring Task & Automation Scheduler**:
   - In-app visual cron scheduler for periodic morning reports, night-time backups, and automated profile health monitoring.
3. **Cross-Device Screen Mirroring**:
   - Live stream viewing of phone screen directly inside desktop Command Center.
