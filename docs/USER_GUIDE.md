# SAM User Guide

Welcome to **SAM** — your sovereign, local-first autonomous AI assistant. This guide explains how to use SAM's desktop application, conversational features, task execution engine, voice controls, and mobile bridges.

---

## 1. Quick Navigation & Navigation Groups

The left sidebar gives you instant access to all core subsystems:
- **Assistant**:
  - `Command Center`: System overview, quick task composer, active model, and health status.
  - `Chat`: Multi-thread conversational intelligence with prompt editing and response regeneration.
  - `Tasks`: Detailed task lifecycle console with real-time SSE progress streams, prompt editing, and retry controls.
- **Brain and Hands**:
  - `Brain`: Local Ollama model library, model switching, and cloud provider API keys.
  - `Hands`: Hardware permissions, desktop automation, browser agent, and terminal tools.
- **Workspaces**:
  - `Projects & Folders`: Context-bound directories, custom prompt rules, and project files.
  - `Connect & Bridges`: WhatsApp, Telegram, Android, and iOS bridge configuration.
  - `Mobile Companion`: Phone-to-PC task ledger and streaming execution monitor.
- **Understanding & Memory**:
  - `Memory`: Episodic memory search and notes vault integration.
  - `Founder Mode`: Personal taste rules, past decisions, and critique capture.
  - `Skills`: Compiled direct execution skills registry.
  - `Plugins & MCP`: Model Context Protocol servers (GitHub, Slack, Google Workspace).
- **System**:
  - `Diagnostics`: Subsystem health check (`sam doctor` equivalent).
  - `Licensing`: Cryptographic Ed25519 license verification.
  - `Permissions`: macOS accessibility, screen capture, and microphone permissions.
  - `Settings`: In-app theme presets (Obsidian Frost, Ice Cyan, Sage Emerald), voice volume, and launch at login.

---

## 2. Conversational Chat & Prompt Editing (ChatGPT/Claude Style)

SAM's Chat interface provides consumer-grade controls:
- **Multi-Thread Sidebar**: Click **+ New** to create a fresh conversation thread; switch between conversations anytime with persistent SQLite storage.
- **Editing Sent Prompts**:
  - Hover over any user message and click the **Edit** button.
  - Modify your prompt inline and press `⌘ Enter` (or click **Save & Submit**).
  - SAM will update your prompt, truncate subsequent messages from that point, and generate an updated answer automatically.
- **Reusing Prompts**:
  - Click **Reuse** on any user prompt to immediately load it into the bottom composer for modification.
- **Regenerating Assistant Answers**:
  - Click **Retry** on any assistant reply to re-generate the answer using the preceding prompt.
- **Copy & Read Aloud**:
  - Every message has one-click **Copy** and high-fidelity **Read aloud** buttons.

---

## 3. Task Execution & Queued Prompt Editing

In `Command Center` or `Tasks`:
- **Submitting a Task**: Type instructions such as *"give me my executive morning briefing"* or *"audit my linkedin profile"*.
- **Editing Queued Tasks**:
  - If a task is still in the queue, click **Edit Prompt** to modify your instruction.
  - Click **Update & Run** to cancel the queued task and immediately submit the updated instruction.
- **Editing Completed Tasks**:
  - On finished or failed tasks, click **Edit & Rerun** to tweak the instruction before executing again.

---

## 4. Voice Controls & Independent Audio Volume

SAM includes an independent audio control system:
- **Silent Mode Override**: When your Mac's hardware volume is lowered or muted, SAM temporarily raises volume to speak its reply, then restores your Mac's previous mute and volume settings.
- **SAM Voice Volume Slider**: Located in the voice controls panel (bottom right or Settings). Adjust SAM's voice from 0% to 100% independently of macOS system volume.
- **Mute / Active Toggle**: Mutes or un-mutes SAM directly inside the app without changing your Mac's volume.

---

## 5. Mobile Continuity (WhatsApp, Telegram & Android)

- **WhatsApp**: Type `!sam audit my linkedin` or `!sam briefing` to receive instant summaries on your mobile phone.
- **Telegram**: Send commands to your private sovereign Telegram bot; SAM executes them on your Mac and replies back.
- **Android App**: Pair your Android phone in `Connect & Bridges` to receive push notifications and execute on-device tasks.
- For complete setup steps, refer to [Mobile Setup & Bridge Guide](guides/MOBILE_SETUP_AND_COMMANDS_GUIDE.md).
