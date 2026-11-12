import { useState } from "react";
import { FiRefreshCw, FiXCircle, FiThumbsUp, FiThumbsDown, FiCheck } from "react-icons/fi";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { StatusPill } from "@/components/StatusPill";
import type { TaskRecord, ExecutionEvent } from "@/api/types";
import { TERMINAL_PHASES } from "@/api/types";
import { phaseToSamState, phaseLabel } from "./phase";
import { useTaskLabel } from "@/features/voice/VoiceControls";
import { submitTaskFeedback } from "@/api/client";

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
  const [feedbackSent, setFeedbackSent] = useState<"positive" | "negative" | null>(null);
  const [sendingFeedback, setSendingFeedback] = useState(false);
  const labelOf = useTaskLabel();
  const lastEvent = events.length > 0 ? events[events.length - 1] : undefined;
  const currentPhase = lastEvent?.phase ?? task.status;
  const currentMessage = lastEvent?.message;
  const isTerminal = TERMINAL_PHASES.has(task.status as never) || TERMINAL_PHASES.has(currentPhase as never);

  const handleFeedback = async (rating: "positive" | "negative") => {
    if (sendingFeedback || feedbackSent) return;
    setSendingFeedback(true);
    try {
      await submitTaskFeedback(task.task_id, rating);
      setFeedbackSent(rating);
    } catch {
      // ignore
    } finally {
      setSendingFeedback(false);
    }
  };

  return (
    <Card className="space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-sm text-ink">{labelOf(task)}</p>
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

      <div className="flex items-center justify-between gap-2 border-t border-line/40 pt-2">
        {isTerminal ? (
          <div className="flex items-center gap-2">
            {feedbackSent ? (
              <span className="flex items-center gap-1.5 text-xs text-mute font-medium">
                <FiCheck className="text-success" size={13} />
                {feedbackSent === "positive" ? "Feedback recorded: confirmed" : "Feedback recorded: critique saved"}
              </span>
            ) : (
              <div className="flex items-center gap-1.5">
                <span className="text-[11px] text-mute">Review:</span>
                <button
                  type="button"
                  onClick={() => void handleFeedback("positive")}
                  disabled={sendingFeedback}
                  className="flex items-center gap-1 rounded-md px-2 py-1 text-xs text-mute hover:bg-success/15 hover:text-success transition-colors cursor-pointer"
                  title="Correct execution — reinforces this path in Founder Mode"
                >
                  <FiThumbsUp size={12} /> Good
                </button>
                <button
                  type="button"
                  onClick={() => void handleFeedback("negative")}
                  disabled={sendingFeedback}
                  className="flex items-center gap-1 rounded-md px-2 py-1 text-xs text-mute hover:bg-danger/15 hover:text-danger transition-colors cursor-pointer"
                  title="Failed or inaccurate — logs rejection rule in Founder Mode"
                >
                  <FiThumbsDown size={12} /> Critique
                </button>
              </div>
            )}
          </div>
        ) : (
          <div />
        )}

        <div className="flex items-center gap-2">
          {!isTerminal && (
            <Button variant="secondary" size="sm" onClick={onCancel} loading={cancelling} disabled={task.cancel_requested}>
              <FiXCircle size={14} /> {task.cancel_requested ? "Cancelling…" : "Cancel"}
            </Button>
          )}
          {isTerminal && (
            <Button variant="secondary" size="sm" onClick={onRetry} loading={retrying}>
              <FiRefreshCw size={13} /> Retry
            </Button>
          )}
        </div>
      </div>
    </Card>
  );
}
