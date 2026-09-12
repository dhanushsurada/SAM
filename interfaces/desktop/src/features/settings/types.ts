/**
 * Every key/default here is copied directly from config/settings.py (read
 * in full, not from memory of an earlier pass) — grouped for a user-facing
 * page rather than the dataclass's own Brain/Ears/Mouth/Vision comments,
 * but the values themselves aren't invented.
 *
 * `path` fields (chroma_path, log_path, etc.) are rendered read-only —
 * they're derived from SAM_DATA_DIR, not something a settings UI should
 * invite editing. Config has no HTTP layer either way (Settings.save()
 * writes local YAML directly) — see PHASE5_PLAN.md §F for the endpoint
 * this page would need to persist anything for real.
 */

export type FieldType = "text" | "number" | "toggle" | "select" | "password" | "path";

export interface SettingField {
  key: string;
  label: string;
  type: FieldType;
  default: string | number | boolean;
  description?: string;
  options?: string[];
}

export interface SettingSection {
  id: string;
  title: string;
  /** Shown once per section, above its fields — for the two sections with
   * a real behavioral or privacy consequence worth flagging up front. */
  note?: { tone: "warn" | "danger"; text: string };
  fields: SettingField[];
}

export const SETTINGS_SCHEMA: SettingSection[] = [
  {
    id: "general",
    title: "General",
    fields: [
      { key: "assistant_name", label: "Assistant name", type: "text", default: "SAM" },
      { key: "user_name", label: "Your name", type: "text", default: "Dhanush" },
    ],
  },
  {
    id: "model",
    title: "Model",
    fields: [
      { key: "ollama_host", label: "Ollama host", type: "text", default: "http://localhost:11434" },
      { key: "primary_model", label: "Primary model", type: "text", default: "qwen2.5:14b" },
      { key: "fallback_model", label: "Fallback model", type: "text", default: "qwen2.5:7b" },
      { key: "model_context_length", label: "Context length", type: "number", default: 8192 },
      { key: "temperature", label: "Temperature", type: "number", default: 0.7 },
      { key: "max_tokens", label: "Max tokens", type: "number", default: 1024 },
    ],
  },
  {
    id: "voice",
    title: "Voice",
    fields: [
      { key: "wake_word", label: "Wake word", type: "text", default: "hey sam" },
      { key: "wake_word_threshold", label: "Wake word threshold", type: "number", default: 0.5 },
      { key: "whisper_model", label: "Whisper model", type: "text", default: "base.en" },
      { key: "whisper_device", label: "Whisper device", type: "select", default: "auto", options: ["auto", "cpu", "cuda"] },
      { key: "recording_timeout", label: "Recording timeout (s)", type: "number", default: 8.0 },
      { key: "silence_threshold", label: "Silence threshold", type: "number", default: 0.01 },
      { key: "tts_engine", label: "TTS engine", type: "select", default: "kokoro", options: ["kokoro", "piper"] },
      { key: "kokoro_voice", label: "Kokoro voice", type: "text", default: "af_bella" },
      { key: "piper_model", label: "Piper model (fallback)", type: "text", default: "en_US-lessac-medium" },
      { key: "speech_rate", label: "Speech rate", type: "number", default: 1.0 },
    ],
  },
  {
    id: "vision",
    title: "Vision",
    fields: [
      { key: "vision_model", label: "Vision model", type: "text", default: "moondream" },
      { key: "screenshot_quality", label: "Screenshot quality", type: "number", default: 85 },
    ],
  },
  {
    id: "memory",
    title: "Memory",
    fields: [
      { key: "memory_top_k", label: "Search results (top k)", type: "number", default: 5 },
      { key: "embedding_model", label: "Embedding model", type: "text", default: "nomic-embed-text" },
      { key: "chroma_path", label: "Chroma path", type: "path", default: "~/.sam_data/memory/chroma" },
      { key: "sqlite_path", label: "SQLite path", type: "path", default: "~/.sam_data/memory/episodic.db" },
    ],
  },
  {
    id: "founder-mode",
    title: "Founder Mode",
    fields: [
      { key: "founder_mode_enabled", label: "Enabled", type: "toggle", default: true },
      {
        key: "founder_mode_llm_capture",
        label: "LLM auto-capture",
        type: "toggle",
        default: true,
        description: "Falls back to a lightweight heuristic if Ollama/the classifier is unavailable.",
      },
      { key: "founder_mode_classifier_model", label: "Classifier model", type: "text", default: "(uses primary model)" },
      { key: "founder_mode_min_confidence_to_show", label: "Min. confidence to show", type: "number", default: 0.3 },
      { key: "founder_mode_path", label: "Data path", type: "path", default: "~/.sam_data/founder_mode" },
    ],
  },
  {
    id: "agent",
    title: "Agent",
    fields: [
      { key: "planner_model", label: "Planner model", type: "text", default: "(uses primary model)" },
      { key: "reflection_model", label: "Reflection model", type: "text", default: "(uses primary model)" },
    ],
  },
  {
    id: "automation-safety",
    title: "Automation & safety",
    note: {
      tone: "danger",
      text: "Off by default on purpose — risky commands (rm, mv, sudo, kill) are refused with a clear message instead of running silently. This is an opt-in, not a convenience toggle.",
    },
    fields: [
      { key: "allow_risky_terminal_commands", label: "Allow risky terminal commands", type: "toggle", default: false },
    ],
  },
  {
    id: "integrations",
    title: "Integrations",
    note: {
      tone: "warn",
      text: "Telegram is an internet-relay bridge, not a local connection — command text passes through Telegram's own servers. The only network calls SAM's doctrine allows besides this are license verification and updates.",
    },
    fields: [
      { key: "telegram_bot_token", label: "Bot token", type: "password", default: "" },
      { key: "telegram_bot_username", label: "Bot username", type: "text", default: "" },
    ],
  },
  {
    id: "runtime",
    title: "Runtime",
    fields: [
      { key: "api_host", label: "API host", type: "text", default: "0.0.0.0" },
      { key: "api_port", label: "API port", type: "number", default: 8420 },
      { key: "incognito", label: "Incognito (skip memory writes)", type: "toggle", default: false },
      { key: "log_level", label: "Log level", type: "select", default: "INFO", options: ["DEBUG", "INFO", "WARNING", "ERROR"] },
      { key: "log_path", label: "Log path", type: "path", default: "~/.sam_data/logs/sam.log" },
      { key: "detected_ram_gb", label: "Detected RAM", type: "path", default: "16 GB" },
      { key: "detected_platform", label: "Detected platform", type: "path", default: "Darwin" },
    ],
  },
  {
    id: "licensing",
    title: "Licensing",
    fields: [
      {
        key: "license_enforcement_enabled",
        label: "Enforce license",
        type: "toggle",
        default: false,
        description: "Non-blocking warnings only while off — this never locks you out by default.",
      },
    ],
  },
  {
    id: "skills",
    title: "Skills",
    fields: [
      { key: "skills_path", label: "Skills path", type: "path", default: "~/.sam_data/skills" },
      { key: "compiled_skills_path", label: "Compiled skills path", type: "path", default: "~/.sam_data/skills/compiled" },
    ],
  },
];
