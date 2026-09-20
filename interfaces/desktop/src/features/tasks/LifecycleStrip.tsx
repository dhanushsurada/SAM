import type { ExecutionEvent } from "@/api/types";
import { buildLifecycle, type StageState } from "./lifecycle";

const DOT: Record<StageState, string> = {
  pending: "bg-line",
  active: "bg-ember",
  done: "bg-success",
  skipped: "bg-line",
  failed: "bg-danger",
  cancelled: "bg-mute",
};

// Plain text-mute (not a faded variant) for the quiet states: the labels
// carry information, so they keep the token's full, checked contrast.
const TEXT: Record<StageState, string> = {
  pending: "text-mute",
  active: "text-ember-text",
  done: "text-ink",
  skipped: "text-mute line-through",
  failed: "text-danger",
  cancelled: "text-mute",
};

const STATE_WORD: Record<StageState, string> = {
  pending: "not reached yet",
  active: "in progress",
  done: "done",
  skipped: "not needed for this task",
  failed: "failed here",
  cancelled: "stopped here",
};

/** Where the selected task is in SAM's lifecycle. Reads the same event
 * history ActiveTask lists below it — one source, two presentations. */
export function LifecycleStrip({ events, status }: { events: ExecutionEvent[]; status: string }) {
  const stages = buildLifecycle(events, status);

  return (
    <ol aria-label="Task lifecycle" className="grid grid-cols-5 gap-2 rounded-lg border border-line bg-surface p-3 shadow-panel">
      {stages.map((stage) => (
        <li key={stage.id} className="min-w-0 space-y-1" title={`${stage.hint} (${STATE_WORD[stage.state]})`}>
          <span className="flex items-center gap-1.5">
            <span className="relative flex h-2 w-2 shrink-0">
              {stage.state === "active" && (
                <span aria-hidden="true" className="absolute inline-flex h-full w-full animate-ping rounded-full bg-ember opacity-60" />
              )}
              <span className={`relative inline-flex h-2 w-2 rounded-full ${DOT[stage.state]}`} />
            </span>
            <span className={`truncate text-xs font-medium ${TEXT[stage.state]}`}>{stage.label}</span>
          </span>
          <span className="sr-only">{STATE_WORD[stage.state]}</span>
        </li>
      ))}
    </ol>
  );
}
