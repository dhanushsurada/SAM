/**
 * Mirrors interfaces/api/schemas.py field-for-field. If that file changes,
 * this needs a matching edit — there's no codegen wiring them together yet
 * (a real gap, not an oversight: worth a §F entry if it starts drifting).
 */

export type InputType = "text" | "voice" | "image" | "image+text" | "image+voice";

export interface Attachment {
  kind: "image" | "audio";
  mime_type: string;
  /** Base64, no "data:" URL prefix — server strips/expects it stripped. */
  data: string;
  filename?: string;
}

export interface TaskCreateRequest {
  instruction: string;
  input_type: InputType;
  attachments: Attachment[];
}

/**
 * The real phase vocabulary from interfaces/api/task_store.py's
 * ALL_STATUSES / TERMINAL_STATUSES — distinct from the product brief's
 * generic IDLE/LISTENING/... vocabulary (src/components/StatusPill.tsx).
 * The mapping between the two lives in src/features/iqoo/phase.ts, not
 * here — this file stays pure wire-format types with no UI coupling.
 */
export type IqooPhase =
  | "queued"
  | "received"
  | "understanding"
  | "perceiving"
  | "planning"
  | "executing"
  | "testing"
  | "verifying"
  | "completed"
  | "failed"
  | "cancelled";

export const TERMINAL_PHASES: ReadonlySet<IqooPhase> = new Set(["completed", "failed", "cancelled"]);

export interface TaskRecord {
  task_id: string;
  instruction: string;
  input_type: string;
  attachments: unknown[];
  status: IqooPhase | string; // string fallback: server logs unknown statuses rather than rejecting them
  result_text: string | null;
  error: string | null;
  cancel_requested: boolean;
  created_at: string;
  updated_at: string;
}

export interface ExecutionEvent {
  type: string;
  task_id: string;
  phase: string;
  message: string;
  timestamp: string;
  /** Not in schemas.py's ExecutionEvent model — server.py's SSE framing
   * adds `id: {seq}` per-line and the JSON payload includes it too (used
   * for EventSource's native Last-Event-ID reconnect). Optional here since
   * it's a wire-format detail, not part of the Pydantic model proper. */
  seq?: number;
}

export interface HealthStatus {
  status: "ok" | "degraded";
  worker_alive: boolean;
  brain_reachable: boolean;
  vision_model_available: boolean | null;
  whisper_available: boolean;
  active_task: string | null;
  queue_depth: number;
  uptime_seconds: number;
  version: string;
}

export interface DemoResetResult {
  reset: boolean;
  tasks_cleared: number;
}
