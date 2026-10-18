// DEV-ONLY. `@tauri-apps/api` and `@tauri-apps/plugin-notification` aren't
// installed in the sandbox this was authored in (no network to `npm
// install` them), so this stubs just enough of their surface for local
// `tsc` to catch real mistakes in native.ts, main.tsx and PermissionsPage
// before a real install exists — same pattern, same reason, as this app's
// own react-shim.d.ts (see interfaces/desktop/README.md).
//
// Delete this file once `npm install` brings in the real packages. Keeping
// both around causes duplicate-declaration errors.
declare module "@tauri-apps/api/core" {
  export function invoke<T>(cmd: string, args?: Record<string, unknown>): Promise<T>;
}

declare module "@tauri-apps/api/window" {
  export interface TauriWindow {
    label: string;
  }
  export function getCurrentWindow(): TauriWindow;
}

declare module "@tauri-apps/api/event" {
  export interface TauriEvent<T> {
    payload: T;
  }
  export function listen<T>(
    event: string,
    handler: (event: TauriEvent<T>) => void,
  ): Promise<() => void>;
}

// Shape confirmed against the plugin's published guest-js source
// (tauri-apps/plugins-workspace, v2 branch) — isPermissionGranted checks
// window.Notification.permission directly when it's not "default",
// otherwise asks the Rust side; requestPermission and sendNotification
// both delegate straight to the Web Notification API on desktop.
declare module "@tauri-apps/plugin-notification" {
  export function isPermissionGranted(): Promise<boolean>;
  export function requestPermission(): Promise<"granted" | "denied" | "default">;
  export function sendNotification(options: string | { title: string; body?: string }): void;
}
