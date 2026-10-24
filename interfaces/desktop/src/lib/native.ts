/**
 * Bridge to the native Tauri shell. Every SAM Desktop screen should import
 * from here rather than calling `window.__TAURI_INTERNALS__` or
 * `@tauri-apps/plugin-notification` directly — that keeps "is this running
 * in Tauri or a plain browser tab" a single, testable question instead of
 * scattered feature-detection.
 *
 * Real vs demo, same rule the rest of this app follows: every function
 * here does a genuine check or performs a genuine action, native or
 * browser-fallback either way — nothing here is a placeholder.
 */

import type { BrainStatus } from "@/api/types";

declare global {
  interface Window {
    __TAURI_INTERNALS__?: unknown;
  }
}

export function isNative(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

export type PermissionStatus = "granted" | "denied" | "prompt" | "unavailable";

/**
 * Fire a native notification. In the Tauri shell this calls the official
 * `@tauri-apps/plugin-notification` guest bindings (isPermissionGranted /
 * requestPermission / sendNotification) — verified against the plugin's
 * published source, not guessed. In a plain browser tab it falls back to
 * the Web Notification API, which those same bindings wrap on desktop
 * anyway, so the two paths behave almost identically.
 */
export async function notify(title: string, body: string): Promise<void> {
  if (isNative()) {
    const { isPermissionGranted, requestPermission, sendNotification } = await import(
      "@tauri-apps/plugin-notification"
    );
    let granted = await isPermissionGranted();
    if (!granted) granted = (await requestPermission()) === "granted";
    if (granted) sendNotification({ title, body });
    return;
  }
  if (typeof Notification === "undefined") return;
  if (Notification.permission === "granted") {
    new Notification(title, { body });
    return;
  }
  if (Notification.permission !== "denied") {
    const permission = await Notification.requestPermission();
    if (permission === "granted") new Notification(title, { body });
  }
}

/** Read-only permission check — never prompts. For the Permissions screen,
 * which needs to show current state without a side effect on every visit. */
export async function notificationPermissionState(): Promise<PermissionStatus> {
  if (isNative()) {
    const { isPermissionGranted } = await import("@tauri-apps/plugin-notification");
    return (await isPermissionGranted()) ? "granted" : "prompt";
  }
  if (typeof Notification === "undefined") return "unavailable";
  if (Notification.permission === "granted") return "granted";
  if (Notification.permission === "denied") return "denied";
  return "prompt";
}

/** Prompts for notification permission. Only call this from a direct user
 * action (a button click) — same rule as the underlying Notification API;
 * calling it unprompted is exactly the pattern that gets a permission
 * request auto-denied or the app flagged as intrusive. */
export async function requestNotificationPermission(): Promise<PermissionStatus> {
  if (isNative()) {
    const { requestPermission } = await import("@tauri-apps/plugin-notification");
    return (await requestPermission()) === "granted" ? "granted" : "denied";
  }
  if (typeof Notification === "undefined") return "unavailable";
  const permission = await Notification.requestPermission();
  return permission === "granted" ? "granted" : permission === "denied" ? "denied" : "prompt";
}

/** Hide the Quick Assistant palette window. Native only — a no-op in a
 * plain browser tab, where there is no second window to hide. */
export async function hideQuickAssistant(): Promise<void> {
  if (!isNative()) return;
  const { invoke } = await import("@tauri-apps/api/core");
  await invoke<void>("hide_quick_assistant");
}

export async function launchAtLoginEnabled(): Promise<boolean> {
  if (!isNative()) return false;
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<boolean>("launch_at_login_enabled");
}

export async function setLaunchAtLogin(enabled: boolean): Promise<boolean> {
  if (!isNative()) return false;
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<boolean>("set_launch_at_login", { enabled });
}

/** Which window this JS runtime is mounted in ("main" vs
 * "quick-assistant"). Browser mode has no Tauri window label at all, so it
 * always resolves to "main" — the ordinary app is the only thing a plain
 * browser tab can be. */
export async function currentWindowLabel(): Promise<string> {
  if (!isNative()) return "main";
  const { getCurrentWindow } = await import("@tauri-apps/api/window");
  return getCurrentWindow().label;
}

/* ────────────────────────────────────────────────────────────────────────
 * Phase C4/C5 — runtime bridge wrappers.
 *
 * Two transports under the hood (src-tauri/src/runtime.rs), one calling
 * convention here: every one of these is a plain invoke() or listen(),
 * so a caller never needs to know runtime_status is a CLI subprocess
 * underneath while models_list is an HTTP call to the gateway — that
 * distinction stays inside runtime.rs, exactly per
 * docs/RUNTIME_BRIDGE_DESIGN.md §A/§B.
 * ──────────────────────────────────────────────────────────────────────── */

export type ProcessName = "voice" | "api" | "telegram";
export type RuntimeState = "STOPPED" | "STARTING" | "READY" | "DEGRADED" | "FAILED" | "STOPPING";
export type OllamaRuntimeState = "READY" | "STOPPED" | "NOT_INSTALLED";

export interface ProcessState {
  state: RuntimeState;
  pid: number | null;
  detail: string | null;
}

export interface OllamaState {
  state: OllamaRuntimeState;
  detail: string;
  models: string[];
}

/** Matches sam_cli.py's `status --json` payload field-for-field — see
 * PHASE_C1-C3_REPORT.md for how it was derived and tested. */
export interface RuntimeSnapshot {
  success: boolean;
  generated_at: string;
  ollama: OllamaState;
  processes: Record<ProcessName, ProcessState>;
  profile_dir: { path: string; exists: boolean };
}

export interface LifecycleResult {
  name: string;
  ok: boolean;
  pid?: number | null;
  already_running?: boolean;
  already_stopped?: boolean;
  forced?: boolean;
  message: string;
}

export interface LifecycleResponse {
  success: boolean;
  results: Record<string, LifecycleResult>;
}

export interface OllamaActionResult {
  ok: boolean;
  already_running: boolean;
  message: string;
}

/** Ollama's own NDJSON progress shape, passed through — not reshaped —
 * all the way from ModelManager.pull() through the SSE endpoint through
 * runtime.rs's relay. `total`/`completed` are absent until a layer
 * actually starts downloading; callers should treat both as optional. */
export interface ModelPullProgress {
  seq?: number;
  name: string;
  status: string;
  digest?: string;
  total?: number;
  completed?: number;
  error?: string | null;
}

async function invokeNative<T>(cmd: string, args?: Record<string, unknown>): Promise<T> {
  if (!isNative()) {
    throw new Error(`"${cmd}" needs the native SAM app — not available in a plain browser tab.`);
  }
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<T>(cmd, args);
}

export function runtimeStatus(): Promise<RuntimeSnapshot> {
  return invokeNative<RuntimeSnapshot>("runtime_status");
}

export function runtimeApiBaseUrl(): Promise<string> {
  return invokeNative<string>("runtime_api_base_url");
}

export function runtimeStart(process?: ProcessName): Promise<LifecycleResponse> {
  return invokeNative<LifecycleResponse>("runtime_start", { process: process ?? null });
}

export function runtimeStop(process?: ProcessName): Promise<LifecycleResponse> {
  return invokeNative<LifecycleResponse>("runtime_stop", { process: process ?? null });
}

export function runtimeRestart(process?: ProcessName): Promise<LifecycleResponse> {
  return invokeNative<LifecycleResponse>("runtime_restart", { process: process ?? null });
}

export function ollamaStatus(): Promise<OllamaState> {
  return invokeNative<OllamaState>("ollama_status");
}

export function ollamaStart(): Promise<OllamaActionResult> {
  return invokeNative<OllamaActionResult>("ollama_start");
}

export function openOllamaDownload(): Promise<string> {
  return invokeNative<string>("open_ollama_download");
}

export function repairRuntimeConfiguration(): Promise<void> {
  return invokeNative<void>("runtime_repair_configuration");
}

/** Return shape is ModelManager.status()'s existing dict, already
 * consumed today by the real /brain page — deliberately left as
 * `unknown` here rather than guessed at and re-typed; callers that need
 * fields from it should narrow from the same place /brain does, not
 * from a second, possibly-drifting type defined only in this file. */
export function modelsList(): Promise<BrainStatus> {
  return invokeNative<BrainStatus>("models_list");
}

export function modelSelect(name: string): Promise<BrainStatus> {
  return invokeNative<BrainStatus>("model_select", { name });
}

/** Starts a pull; progress arrives via onModelPullProgress(), not via
 * this promise's resolution. Resolves once the stream ends successfully,
 * rejects with the failure message otherwise (mirrors
 * runtime.rs::model_pull's Result<(), String>). */
export function modelPull(name: string): Promise<void> {
  return invokeNative<void>("model_pull", { name });
}

export function cancelModelPull(): Promise<boolean> {
  return invokeNative<boolean>("model_pull_cancel");
}

/** Subscribes to pull progress; returns an unsubscribe function. No-ops
 * (returns a function that does nothing) in a plain browser tab, where
 * there is no native event stream to listen to. */
export async function onModelPullProgress(
  handler: (progress: ModelPullProgress) => void,
): Promise<() => void> {
  if (!isNative()) return () => {};
  const { listen } = await import("@tauri-apps/api/event");
  return listen<ModelPullProgress>("model-pull-progress", (event) => handler(event.payload));
}

/* ────────────────────────────────────────────────────────────────────────
 * Phase C7 — setup state.
 * ──────────────────────────────────────────────────────────────────────── */

export type SetupJourneyState = "first_run" | "in_progress" | "complete";

export interface SetupState {
  state: SetupJourneyState;
  selected_model: string | null;
}

export function getSetupState(): Promise<SetupState> {
  return invokeNative<SetupState>("setup_state_get");
}

export function setSetupState(state: SetupJourneyState, model?: string): Promise<SetupState> {
  return invokeNative<SetupState>("setup_state_set", { state, model: model ?? null });
}
