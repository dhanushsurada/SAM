import type { IqooPhase } from "@/api/types";
import type { SamState } from "@/components/StatusPill";

const PHASE_TO_STATE: Record<IqooPhase, SamState> = {
  queued: "WAITING",
  received: "THINKING",
  understanding: "THINKING",
  perceiving: "THINKING",
  planning: "THINKING",
  executing: "EXECUTING",
  testing: "EXECUTING",
  verifying: "EXECUTING",
  completed: "SUCCESS",
  failed: "FAILED",
  cancelled: "CANCELLED",
};

/** Unknown phase strings (task_store.py logs but doesn't reject them) fall
 * back to UNVERIFIED rather than guessing — an honest "don't know" beats a
 * wrong color. */
export function phaseToSamState(phase: string): SamState {
  return PHASE_TO_STATE[phase as IqooPhase] ?? "UNVERIFIED";
}

const PHASE_LABELS: Record<IqooPhase, string> = {
  queued: "Queued",
  received: "Received",
  understanding: "Reading your request",
  perceiving: "Interpreting attachments",
  planning: "Planning",
  executing: "Executing",
  testing: "Testing",
  verifying: "Verifying",
  completed: "Completed",
  failed: "Failed",
  cancelled: "Cancelled",
};

/** Fallback label for a bare phase string with no event message attached
 * yet (e.g. optimistic UI right after task creation, before the first SSE
 * event arrives). Prefer the real event's `message` field when you have
 * one — it's the actual human-readable summary from gateway.py
 * (e.g. "Reading your request"), this is only for when you don't. */
export function phaseLabel(phase: string): string {
  return PHASE_LABELS[phase as IqooPhase] ?? phase;
}
