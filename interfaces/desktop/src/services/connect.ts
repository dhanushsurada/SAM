import { isNative, runtimeApiBaseUrl } from "@/lib/native";

export interface PairingSession {
  v: string;
  token: string;
  host: string;
  port: number;
  expires_at: string;
}

export interface ConnectDevice {
  id: number;
  channel: string;
  external_id: string;
  device_name: string | null;
  status: string;
  paired_at: string | null;
  last_active: string | null;
  platform: string | null;
  protocol_version: string | null;
  capabilities: Record<string, { available: boolean; permission: string }>;
  connection_state: string;
}

export interface ConnectTask {
  task_id: string;
  target_device_id: string;
  action: string;
  status: string;
  last_message: string | null;
  error: string | null;
  created_at: string;
  updated_at: string;
}

async function connectUrl(path: string): Promise<string> {
  const base = isNative()
    ? `${(await runtimeApiBaseUrl()).replace(/\/$/, "")}/api/connect`
    : "/api/connect";
  return `${base}${path}`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(await connectUrl(path), {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (!response.ok) {
    let message = response.statusText;
    try {
      const body = await response.json();
      if (typeof body?.detail === "string") message = body.detail;
    } catch { /* keep the HTTP status text */ }
    throw new Error(message || `SAM Connect returned HTTP ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export const connectService = {
  startPairing: () => request<PairingSession>("/pairing/start", { method: "POST" }),
  listDevices: () => request<ConnectDevice[]>("/devices?include_pending=true"),
  revokeDevice: (id: number) => request<{ revoked: boolean }>(`/devices/${id}/revoke`, { method: "POST" }),
  createNotificationTask: (target_device_id: string, title: string, message: string) =>
    request<ConnectTask>("/tasks", {
      method: "POST",
      body: JSON.stringify({
        target_device_id,
        action: "show_notification",
        required_capability: "notifications",
        payload: { title, message },
        idempotency_key: crypto.randomUUID(),
        timeout_seconds: 120,
      }),
    }),
  getTask: (taskId: string) => request<ConnectTask>(`/tasks/${encodeURIComponent(taskId)}`),
  cancelTask: (taskId: string) =>
    request<{ cancelled: boolean }>(`/tasks/${encodeURIComponent(taskId)}/cancel`, { method: "POST" }),
};
