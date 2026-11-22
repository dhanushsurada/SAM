import { isNative, runtimeApiBaseUrl } from "../lib/native.ts";

export interface ChannelStatus {
  enabled: boolean;
  status: "active" | "configured" | "unconfigured" | "disabled" | "offline";
  configured: boolean;
  active_sessions: number;
  devices_count: number;
  devices: Array<{
    device_id: string;
    device_name: string;
    channel: string;
    paired_at: string;
    last_active: string;
  }>;
  bot_username?: string;
  phone_number_id?: string;
  webhook_status?: string;
  continuity?: Record<string, any>;
  pairing_mode?: string;
}

export interface BridgesStatusResponse {
  timestamp: string;
  stats: {
    total_trusted_devices: number;
    active_bridges: number;
    pending_pairing_tokens: number;
    clipboard_synced: boolean;
  };
  channels: {
    telegram: ChannelStatus;
    whatsapp: ChannelStatus;
    apple_ios: ChannelStatus;
    android: ChannelStatus;
  };
  mesh_nodes: number;
}

export interface BridgePairingResponse {
  channel: string;
  token?: string;
  deep_link?: string;
  qr_code?: string;
  instructions?: string;
  shortcut_def?: Record<string, any>;
  expires_in_seconds?: number;
}

export interface FabricNode {
  node_id: string;
  device_type: string;
  device_name: string;
  status: string;
  last_seen: string;
  capabilities: string[];
}

export interface FabricTopologyResponse {
  hub: {
    id: string;
    name: string;
    platform: string;
    protocol_version: string;
    status: string;
  };
  total_nodes: number;
  nodes: FabricNode[];
  shared_clipboard: {
    has_content: boolean;
    source: string;
    updated_at: string;
  };
}

export interface FabricClipboardResponse {
  content: string;
  source_device_id: string;
  updated_at: string;
}

export interface IOSShortcutConfigResponse {
  name: string;
  description: string;
  endpoint: string;
  method: string;
  headers: Record<string, string>;
  instructions: string[];
}

async function apiBase(): Promise<string> {
  return isNative()
    ? (await runtimeApiBaseUrl()).replace(/\/$/, "")
    : "";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const base = await apiBase();
  const res = await fetch(`${base}${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });

  if (!res.ok) {
    let msg = res.statusText;
    try {
      const data = await res.json();
      if (typeof data?.detail === "string") msg = data.detail;
    } catch {
      // keep fallback status text
    }
    throw new Error(msg || `Request to ${path} failed with HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export const bridgesService = {
  getStatus: () => request<BridgesStatusResponse>("/api/bridges/status"),
  startBridge: (channel: string) =>
    request<{ channel: string; started: boolean }>(`/api/bridges/${encodeURIComponent(channel)}/start`, { method: "POST" }),
  stopBridge: (channel: string) =>
    request<{ channel: string; stopped: boolean }>(`/api/bridges/${encodeURIComponent(channel)}/stop`, { method: "POST" }),
  pairChannel: (channel: string) =>
    request<BridgePairingResponse>(`/api/bridges/${encodeURIComponent(channel)}/pair`, { method: "POST" }),
  broadcast: (message: string, channels?: string[]) =>
    request<{ message: string; results: Record<string, boolean> }>("/api/bridges/broadcast", {
      method: "POST",
      body: JSON.stringify({ message, channels }),
    }),
  getTopology: () => request<FabricTopologyResponse>("/api/fabric/topology"),
  getClipboard: () => request<FabricClipboardResponse>("/api/fabric/clipboard"),
  setClipboard: (content: string, sourceDeviceId = "desktop") =>
    request<{ synced: boolean; length: number }>("/api/fabric/clipboard", {
      method: "POST",
      body: JSON.stringify({ content, source_device_id: sourceDeviceId }),
    }),
  getIOSShortcutConfig: (baseUrl?: string) => {
    const q = baseUrl ? `?base_url=${encodeURIComponent(baseUrl)}` : "";
    return request<IOSShortcutConfigResponse>(`/api/ios/shortcut/config${q}`);
  },
};
