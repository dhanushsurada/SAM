import { FiRefreshCw, FiXCircle } from "react-icons/fi";
import { Button } from "@/components/Button";
import { StatusPill } from "@/components/StatusPill";
import type { TaskRecord, ExecutionEvent } from "@/api/types";
import { TERMINAL_PHASES } from "@/api/types";
import { phaseToSamState, phaseLabel } from "./phase";

export interface ActiveTaskProps {
  task: TaskRecord;
  events: ExecutionEvent[];
  streamError: boolean;
  onCancel: () => void;
  onRetry: () => void;
  cancelling: boolean;
  retrying: boolean;
}

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  } catch {
    return iso;
  }
}

export function ActiveTask({ task, events, streamError, onCancel, onRetry, cancelling, retrying }: ActiveTaskProps) {
  // .at(-1) needs ES2022 lib; tsconfig targets ES2020, so index from length
  // instead rather than bumping the lib target for one call site.
  const lastEvent = events.length > 0 ? events[events.length - 1] : undefined;
  const currentPhase = lastEvent?.phase ?? task.status;
  const currentMessage = lastEvent?.message;
  const isTerminal = TERMINAL_PHASES.has(task.status as never) || TERMINAL_PHASES.has(currentPhase as never);

  return (
    <div className="space-y-4 rounded-lg border border-line bg-surface p-4 shadow-panel">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-sm text-ink">{task.instruction}</p>
          <p className="mt-0.5 font-mono-data text-[11px] text-mute">{task.task_id}</p>
        </div>
        <StatusPill state={phaseToSamState(currentPhase)} label={currentMessage ?? phaseLabel(currentPhase)} live />
      </div>

      {streamError && (
        <p className="rounded-md border border-warn/30 bg-warn/10 px-3 py-2 text-xs text-warn">
          Live updates disconnected — the task may still be running server-side. Reselecting it will
          reconnect and replay anything missed (the server keeps full event history per task).
        </p>
      )}

      <ol className="max-h-56 space-y-1.5 overflow-y-auto border-l border-line pl-3">
        {events.length === 0 && <li className="text-xs text-mute">Waiting for the first event…</li>}
        {events.map((event, i) => (
          <li key={i} className="text-xs">
            <span className="font-mono-data text-unverified">{formatTime(event.timestamp)}</span>{" "}
            <span className="text-mute">{phaseLabel(event.phase)}</span> —{" "}
            <span className="text-ink">{event.message}</span>
          </li>
        ))}
      </ol>

      {/* completed/failed message text comes from the terminal SSE event
          itself (gateway.py publishes the final result/error AS that
          event's message) — server.py replays full history on a fresh
          subscribe, so this is accurate even when re-selecting an old,
          already-finished task, not just for one watched live start-to-end.
          task.result_text/error are the fallback if events are somehow
          unavailable. */}
      {currentPhase === "completed" && (
        <div className="rounded-md border border-success/25 bg-success/5 p-3 text-sm text-ink">
          {currentMessage ?? task.result_text}
        </div>
      )}
      {currentPhase === "failed" && (
        <div className="rounded-md border border-danger/25 bg-danger/5 p-3 text-sm text-danger">
          {currentMessage ?? task.error}
        </div>
      )}

      <div className="flex justify-end gap-2">
        {!isTerminal && (
          <Button variant="secondary" size="sm" onClick={onCancel} loading={cancelling} disabled={task.cancel_requested}>
            <FiXCircle size={14} /> {task.cancel_requested ? "Cancelling…" : "Cancel"}
          </Button>
        )}
        {isTerminal && (
          <Button variant="secondary" size="sm" onClick={onRetry} loading={retrying}>
            <FiRefreshCw size={14} /> Retry
          </Button>
        )}
      </div>
    </div>
  );
}
