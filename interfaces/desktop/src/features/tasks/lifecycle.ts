import type { ExecutionEvent } from "@/api/types";
import { TERMINAL_PHASES } from "@/api/types";

/**
 * SAM's task lifecycle as the user sees it:
 *
 *   understand -> plan -> execute -> verify -> result
 *
 * Derived only from the phases the gateway really emits (task_store.py's
 * ALL_STATUSES, published by interfaces/api/gateway.py and the ReAct loop):
 * there is no separate "observe" phase on the wire — observing what an
 * action did happens inside each execute/verify step — so it isn't drawn as
 * a stage of its own. A stage the task never entered is "skipped" (a direct
 * answer has no plan or execute stage), never invented.
 */
export type StageId = "understand" | "plan" | "execute" | "verify" | "result";
export type StageState = "pending" | "active" | "done" | "skipped" | "failed" | "cancelled";

export interface LifecycleStage {
  id: StageId;
  label: string;
  hint: string;
  state: StageState;
}

const ORDER: StageId[] = ["understand", "plan", "execute", "verify", "result"];

const META: Record<StageId, { label: string; hint: string }> = {
  understand: { label: "Understand", hint: "Reads the request and any attachment" },
  plan: { label: "Plan", hint: "Breaks the task into steps" },
  execute: { label: "Execute", hint: "Acts, then observes what happened" },
  verify: { label: "Verify", hint: "Checks each step's result before moving on" },
  result: { label: "Result", hint: "The outcome, reported honestly" },
};

const STAGE_OF_PHASE: Record<string, StageId> = {
  queued: "understand",
  received: "understand",
  understanding: "understand",
  perceiving: "understand",
  planning: "plan",
  executing: "execute",
  testing: "execute",
  verifying: "verify",
  completed: "result",
  failed: "result",
  cancelled: "result",
};

/** `events` is the selected task's full, ordered event history; `status` is
 * the task record's own status, used when no event has arrived yet. */
export function buildLifecycle(events: ExecutionEvent[], status: string): LifecycleStage[] {
  const phases = events.length > 0 ? events.map((e) => e.phase) : [status];
  const last = phases[phases.length - 1];
  const terminal = TERMINAL_PHASES.has(last as never) ? last : null;

  const reached = new Set<StageId>();
  for (const phase of phases) {
    const stage = STAGE_OF_PHASE[phase];
    if (stage) reached.add(stage);
  }
  const currentStage: StageId | undefined = STAGE_OF_PHASE[last];

  // Where a failed/cancelled task stopped: the last stage before "result".
  let stoppedAt: StageId | null = null;
  if (terminal === "failed" || terminal === "cancelled") {
    for (const id of ORDER) {
      if (id !== "result" && reached.has(id)) stoppedAt = id;
    }
  }

  const highestReached = ORDER.reduce((hi, id, i) => (reached.has(id) ? i : hi), -1);

  return ORDER.map((id, i): LifecycleStage => {
    const { label, hint } = META[id];
    let state: StageState;

    if (id === "result") {
      state = terminal === "completed" ? "done" : terminal === "failed" ? "failed" : terminal === "cancelled" ? "cancelled" : "pending";
    } else if (id === stoppedAt) {
      state = terminal === "cancelled" ? "cancelled" : "failed";
    } else if (reached.has(id)) {
      state = id === currentStage && terminal === null ? "active" : "done";
    } else if (terminal !== null || i < highestReached) {
      state = "skipped";
    } else {
      state = "pending";
    }
    return { id, label, hint, state };
  });
}
