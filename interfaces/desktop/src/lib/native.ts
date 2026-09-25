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

/** Which window this JS runtime is mounted in ("main" vs
 * "quick-assistant"). Browser mode has no Tauri window label at all, so it
 * always resolves to "main" — the ordinary app is the only thing a plain
 * browser tab can be. */
export async function currentWindowLabel(): Promise<string> {
  if (!isNative()) return "main";
  const { getCurrentWindow } = await import("@tauri-apps/api/window");
  return getCurrentWindow().label;
}
