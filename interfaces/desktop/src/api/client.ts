import type {
  TaskCreateRequest,
  TaskRecord,
  HealthStatus,
  DemoResetResult,
  ExecutionEvent,
  BrainStatus,
  ModelSelectRequest,
} from "./types";
import { TERMINAL_PHASES } from "./types";
import { isNative, runtimeApiBaseUrl } from "@/lib/native";

const BASE = "/api/iqoo";
// SAM Core routes (Brain/model selection) sit beside /api/iqoo, not under it:
// choosing the Brain isn't part of the phone-task contract.
const CORE_BASE = "/api";

export class ApiError extends Error {
  constructor(
    public status: number,
    /** FastAPI's HTTPException body shape: {"detail": "..."}. */
    public detail: string
  ) {
    super(`${status}: ${detail}`);
    this.name = "ApiError";
  }
}

async function endpoint(path: string, base: string): Promise<string> {
  if (isNative()) return `${(await runtimeApiBaseUrl()).replace(/\/$/, "")}${base}${path}`;
  return `${base}${path}`;
}

async function apiError(res: Response): Promise<ApiError> {
  let detail = res.statusText;
  try {
    const body = await res.json();
    if (typeof body?.detail === "string") detail = body.detail;
  } catch {
    // body wasn't JSON — statusText stands.
  }
  return new ApiError(res.status, detail);
}

async function request<T>(path: string, init?: RequestInit, base: string = BASE): Promise<T> {
  const res = await fetch(await endpoint(path, base), {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) throw await apiError(res);
  return res.json() as Promise<T>;
}

export function createTask(req: TaskCreateRequest): Promise<TaskRecord> {
  return request<TaskRecord>("/tasks", { method: "POST", body: JSON.stringify(req) });
}

export function getTask(taskId: string): Promise<TaskRecord> {
  return request<TaskRecord>(`/tasks/${encodeURIComponent(taskId)}`);
}

export function cancelTask(taskId: string): Promise<TaskRecord> {
  return request<TaskRecord>(`/tasks/${encodeURIComponent(taskId)}/cancel`, { method: "POST" });
}

/** Returns a *new* TaskRecord — retry resubmits as a fresh task_id, it
 * doesn't reset the original in place (matches server.py exactly: 409 if
 * the original is still active, 404 if it never existed). */
export function retryTask(taskId: string): Promise<TaskRecord> {
  return request<TaskRecord>(`/tasks/${encodeURIComponent(taskId)}/retry`, { method: "POST" });
}

export function getHealth(): Promise<HealthStatus> {
  return request<HealthStatus>("/health");
}

export function demoReset(): Promise<DemoResetResult> {
  return request<DemoResetResult>("/demo/reset", { method: "POST" });
}

/** Provider status, selected/fallback/active model and every installed
 * model. An unreachable Ollama comes back as status "unavailable", not an
 * error — only an unreachable gateway rejects. */
export function getBrainStatus(): Promise<BrainStatus> {
  return request<BrainStatus>("/models", undefined, CORE_BASE);
}

/** Makes an installed model the Brain and returns the fresh status. Rejects
 * with an ApiError carrying the server's reason: 409 a task is running,
 * 404 not installed, 422 unusable as a Brain, 502/503 Ollama problems. */
export function selectModel(model: string): Promise<BrainStatus> {
  const body: ModelSelectRequest = { model };
  return request<BrainStatus>(
    "/models/select",
    { method: "POST", body: JSON.stringify({ model: body.model }) },
    CORE_BASE
  );
}

/** Read/write the persisted local SAM settings used by the settings form.
 * The API redacts credentials on read; a blank credential is omitted by the
 * form unless the user explicitly edits it. */
export function getSettings(): Promise<Record<string, string | number | boolean | null>> {
  return request<Record<string, string | number | boolean | null>>("/settings", undefined, CORE_BASE);
}

export function updateSettings(
  changes: Record<string, string | number | boolean | null>
): Promise<Record<string, string | number | boolean | null>> {
  return request<Record<string, string | number | boolean | null>>(
    "/settings",
    { method: "PATCH", body: JSON.stringify(changes) },
    CORE_BASE
  );
}

export interface EnvironmentReport {
  environment: {
    os: { name: string; version: string; architecture: string };
    python: { current: string; executable: string; supported: string[]; selected: { path: string | null; supported: boolean; detail?: string } };
    hardware: { memory_gb: number | null; cpu_count: number | null; disk: { free_gb: number | null; total_gb: number | null } };
    tools: Record<string, { installed: boolean; path: string | null; version?: string; minimum_version?: string }>;
  };
  diagnostics: Array<{ severity: string; area: string; message: string }>;
  dependencies: Record<string, { required: boolean; available: boolean; missing: string[]; incompatible: Array<{ name: string; installed: string; required: string }> }>;
  capabilities: {
    ollama: { installed: boolean; available: boolean; state: string; detail: string; models: string[]; configured_model: string | null; configured_model_available: boolean };
    features: Record<string, { available: boolean; missing_packages: string[]; incompatible_packages: unknown[]; missing_system_prerequisites: string[]; reason: string }>;
  };
  setup: { journey: { state: string; selected_model: string | null }; installation: { steps?: Record<string, { state: string; detail?: string }>; state?: string }; dependency_repair_supported?: boolean };
}

/** SAM's own voice (Kokoro, then Piper) rendered to a complete WAV file.
 * Rejects with an ApiError: 409 speech is turned off (stay silent), 501 no
 * installed engine can return audio (the caller may use the web view's own
 * voice), 422 nothing to say. The first request after install can be slow:
 * Kokoro loads, and downloads, its model then. `signal` aborts the wait. */
export async function synthesizeSpeech(text: string, signal?: AbortSignal): Promise<ArrayBuffer> {
  const res = await fetch(await endpoint("/speech", CORE_BASE), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
    signal,
  });
  if (!res.ok) throw await apiError(res);
  return res.arrayBuffer();
}

export function getEnvironmentReport(): Promise<EnvironmentReport> {
  return request<EnvironmentReport>("/environment", undefined, CORE_BASE);
}

export function repairEnvironment(groups: string[]): Promise<{ state: string; groups: string[] }> {
  return request<{ state: string; groups: string[] }>("/environment/repair", {
    method: "POST", body: JSON.stringify({ groups }),
  }, CORE_BASE);
}

/**
 * Native EventSource against /tasks/{id}/events. Deliberately not
 * hand-rolling reconnect logic: server.py's SSE framing sends `id: {seq}`
 * per event specifically so the browser's built-in reconnect-with-
 * Last-Event-ID does the right thing on its own (see that file's own
 * comments) — re-implementing it here would be duplicating something the
 * platform already does correctly.
 *
 * One thing that *does* need handling on this side: EventSource's default
 * behavior is to auto-reconnect after ANY stream close, including the
 * server's own clean close once a task hits a terminal phase (server.py's
 * generator just `return`s — nothing tells the browser "don't reconnect").
 * Left alone, that reopens the connection every few seconds forever on a
 * finished task. So: close explicitly on seeing a terminal phase, once
 * that event has been delivered to the caller.
 */
export function subscribeToTaskEvents(
  taskId: string,
  onEvent: (event: ExecutionEvent) => void,
  onError?: (err: Event) => void
): () => void {
  let source: EventSource | undefined;
  let cancelled = false;
  void endpoint(`/tasks/${encodeURIComponent(taskId)}/events`, BASE).then((url) => {
    if (cancelled) return;
    source = new EventSource(url);
    source.onmessage = (msg: MessageEvent<string>) => {
      try {
        const event = JSON.parse(msg.data) as ExecutionEvent;
        onEvent(event);
        if (TERMINAL_PHASES.has(event.phase as never)) source?.close();
      } catch {
        // A malformed payload shouldn't take the whole stream down.
      }
    };
    if (onError) source.onerror = onError;
  }).catch(() => {
    if (!cancelled && onError) onError(new Event("error"));
  });

  return () => {
    cancelled = true;
    source?.close();
  };
}

export interface CloudModel {
  id: string;
  name: string;
  context: number;
  fast: boolean;
}

export interface CloudProvider {
  id: string;
  name: string;
  description: string;
  configured: boolean;
  masked_key: string;
  default_model: string;
  models: CloudModel[];
}

export interface ModelNotification {
  id: string;
  title: string;
  provider: string;
  model: string;
  description: string;
  badge: string;
  action_url: string | null;
  configured: boolean;
  type: string;
}

export function submitTaskFeedback(
  taskId: string,
  rating: "positive" | "negative",
  comment?: string
): Promise<{ ok: boolean; feedback_recorded: boolean; rating: string }> {
  return request<{ ok: boolean; feedback_recorded: boolean; rating: string }>(
    `/tasks/${encodeURIComponent(taskId)}/feedback`,
    {
      method: "POST",
      body: JSON.stringify({ rating, comment: comment || "" }),
    }
  );
}

export function getCloudProviders(): Promise<{ providers: CloudProvider[] }> {
  return request<{ providers: CloudProvider[] }>("/models/providers", undefined, CORE_BASE);
}

export function saveProviderKey(provider: string, apiKey: string): Promise<{ ok: boolean; provider: string }> {
  return request<{ ok: boolean; provider: string }>(
    "/models/keys",
    {
      method: "POST",
      body: JSON.stringify({ provider, api_key: apiKey }),
    },
    CORE_BASE
  );
}

export function deleteProviderKey(provider: string): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>(
    `/models/keys/${encodeURIComponent(provider)}`,
    {
      method: "DELETE",
    },
    CORE_BASE
  );
}

export function getModelUpdates(): Promise<{ notifications: ModelNotification[] }> {
  return request<{ notifications: ModelNotification[] }>("/models/updates", undefined, CORE_BASE);
}

export interface ChatResponsePayload {
  reply: string;
  model: string;
  conversation_id?: string;
}

export function sendChatMessage(
  message: string,
  conversationId?: string,
  history?: Array<{ role: string; content: string }>
): Promise<ChatResponsePayload> {
  return request<ChatResponsePayload>(
    "/chat",
    {
      method: "POST",
      body: JSON.stringify({
        message,
        conversation_id: conversationId,
        history: history || [],
      }),
    },
    CORE_BASE
  );
}

export interface MCPServer {
  id: string;
  name: string;
  description: string;
  enabled: boolean;
  command: string;
  args: string[];
  url: string;
  transport: string;
  masked_env: Record<string, string>;
  tools_count: number;
  status: string;
}

export interface MCPCatalogItem {
  id: string;
  name: string;
  description: string;
  icon: string;
  category: string;
  auth_type: string;
  token_label?: string;
  docs_url?: string;
  command: string;
  args: string[];
  env_keys: string[];
  installed: boolean;
  enabled: boolean;
}

export function getMCPServers(): Promise<{ servers: MCPServer[]; catalog: MCPCatalogItem[] }> {
  return request<{ servers: MCPServer[]; catalog: MCPCatalogItem[] }>("/mcp/servers", undefined, CORE_BASE);
}

export function configureMCPServer(data: {
  id: string;
  name: string;
  description?: string;
  command?: string;
  args?: string[];
  url?: string;
  transport?: string;
  env?: Record<string, string>;
  enabled?: boolean;
}): Promise<{ ok: boolean; server: MCPServer }> {
  return request<{ ok: boolean; server: MCPServer }>(
    "/mcp/servers",
    {
      method: "POST",
      body: JSON.stringify(data),
    },
    CORE_BASE
  );
}

export function toggleMCPServer(id: string, enabled: boolean): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>(
    `/mcp/servers/${encodeURIComponent(id)}`,
    {
      method: "PATCH",
      body: JSON.stringify({ enabled }),
    },
    CORE_BASE
  );
}

export function deleteMCPServer(id: string): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>(
    `/mcp/servers/${encodeURIComponent(id)}`,
    {
      method: "DELETE",
    },
    CORE_BASE
  );
}

export function testMCPServer(id: string): Promise<{ ok: boolean; message?: string; error?: string }> {
  return request<{ ok: boolean; message?: string; error?: string }>(
    `/mcp/servers/${encodeURIComponent(id)}/test`,
    {
      method: "POST",
    },
    CORE_BASE
  );
}
