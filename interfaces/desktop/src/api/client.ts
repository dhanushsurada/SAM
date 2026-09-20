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

async function request<T>(path: string, init?: RequestInit, base: string = BASE): Promise<T> {
  const res = await fetch(`${base}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      // body wasn't JSON — statusText stands.
    }
    throw new ApiError(res.status, detail);
  }
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
  const source = new EventSource(`${BASE}/tasks/${encodeURIComponent(taskId)}/events`);

  source.onmessage = (msg: MessageEvent<string>) => {
    try {
      const event = JSON.parse(msg.data) as ExecutionEvent;
      onEvent(event);
      if (TERMINAL_PHASES.has(event.phase as never)) {
        source.close();
      }
    } catch {
      // A malformed payload shouldn't take the whole stream down.
    }
  };
  if (onError) source.onerror = onError;

  return () => source.close();
}
