import { useEffect, useRef } from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/Button";
import { ModeBadge } from "@/components/ModeBadge";
import { StatusPill } from "@/components/StatusPill";
import { TERMINAL_PHASES } from "@/api/types";
import type { TaskRecord } from "@/api/types";
import { useTaskSession } from "@/stores/taskSession";
import { phaseLabel, phaseToSamState } from "@/features/iqoo/phase";
import { ChatMessageBubble } from "./ChatMessageBubble";
import { ChatComposer } from "./ChatComposer";
import type { ChatMessage } from "./types";

function isTerminal(status: string): boolean {
  return TERMINAL_PHASES.has(status as never);
}

/** SAM's reply to one message = the outcome of the task it started. Only
 * finished tasks become text; a running one is a live status, never a
 * made-up answer. */
function replyFor(task: TaskRecord): ChatMessage | null {
  const base = { id: `${task.task_id}-reply`, role: "assistant" as const, timestamp: task.updated_at };
  if (task.status === "completed") {
    return { ...base, content: task.result_text || "Done.", tone: "default" };
  }
  if (task.status === "failed") {
    return { ...base, content: task.error || task.result_text || "That didn't complete.", tone: "danger" };
  }
  if (task.status === "cancelled") {
    return { ...base, content: "Cancelled.", tone: "muted" };
  }
  return null;
}

/**
 * Chat — a conversational view over SAM's real task pipeline.
 *
 * What's real: each message is submitted as a task (POST /api/iqoo/tasks,
 * text), runs through the actual Brain and ReAct loop, and SAM's reply is
 * that task's outcome. SAM may act on this computer, not just
 * answer — the same as the Command Center.
 *
 * What it isn't: a multi-turn conversation. The gateway builds each task's
 * Session with no chat history, so SAM doesn't see the earlier messages on
 * this screen; continuity comes only from SAM's persistent memory. There's
 * no token streaming either — a reply appears when the task finishes.
 */
export function ChatPage() {
  const {
    sessionTasks,
    selectedTaskId,
    selectTask,
    events,
    submitting,
    submitError,
    submitTask,
    cancelling,
    cancelSelected,
  } = useTaskSession();
  const bottomRef = useRef<HTMLDivElement>(null);

  const latest = sessionTasks.length > 0 ? sessionTasks[sessionTasks.length - 1] : null;
  const latestId = latest ? latest.task_id : null;
  const running = submitting || (latest !== null && !isTerminal(latest.status));

  // The store streams events for one task at a time. Chat's live edge is
  // the newest message, so make sure that's the task being watched (the
  // server replays a task's full history when it's re-selected).
  useEffect(() => {
    if (latestId && selectedTaskId !== latestId) selectTask(latestId);
  }, [latestId, selectedTaskId, selectTask]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [sessionTasks.length, events.length]);

  const handleSend = async (text: string) => {
    await submitTask({ instruction: text, input_type: "text", attachments: [] });
  };

  const lastEvent = events.length > 0 ? events[events.length - 1] : undefined;

  return (
    <div className="mx-auto flex h-full max-w-2xl flex-col">
      <div className="flex items-center gap-2 pb-3">
        <h1 className="text-lg font-semibold text-ink">Chat</h1>
        <ModeBadge mode="live" />
      </div>

      <p className="mb-4 rounded-md border border-line bg-surface px-3 py-2 text-xs text-mute">
        Every message runs as a SAM task, so SAM can act on this computer as well as answer. Messages are handled
        one at a time and SAM doesn't see the earlier ones on this screen; its memory carries context between
        them. Follow a task in detail on{" "}
        <Link to="/tasks" className="text-ember-text hover:underline">
          Tasks
        </Link>
        .
      </p>

      <div className="flex-1 space-y-3 overflow-y-auto">
        {sessionTasks.length === 0 && (
          <p className="pt-10 text-center text-sm text-mute">Ask SAM something, or tell it what to do.</p>
        )}

        {sessionTasks.map((task) => {
          const reply = replyFor(task);
          const isLive = task.task_id === selectedTaskId;
          const phase = isLive && lastEvent ? lastEvent.phase : task.status;
          return (
            <div key={task.task_id} className="space-y-3">
              <ChatMessageBubble
                message={{ id: task.task_id, role: "user", content: task.instruction, timestamp: task.created_at }}
              />
              {reply ? (
                <ChatMessageBubble message={reply} />
              ) : (
                <div className="flex justify-start">
                  <StatusPill
                    state={phaseToSamState(phase)}
                    label={(isLive && lastEvent ? lastEvent.message : null) ?? phaseLabel(phase)}
                    live={isLive}
                  />
                </div>
              )}
            </div>
          );
        })}
        <div ref={bottomRef} />
      </div>

      {submitError && <p className="pt-2 text-xs text-danger">{submitError}</p>}
      {running && !submitting && (
        <div className="flex justify-end pt-2">
          <Button variant="ghost" size="sm" onClick={cancelSelected} loading={cancelling}>
            Cancel this task
          </Button>
        </div>
      )}
      <div className="pt-3">
        <ChatComposer onSend={handleSend} disabled={running} />
      </div>
    </div>
  );
}
