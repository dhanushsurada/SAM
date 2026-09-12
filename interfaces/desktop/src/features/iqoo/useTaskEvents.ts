import { useEffect, useState } from "react";
import type { ExecutionEvent } from "@/api/types";
import { iqooService } from "@/services/iqoo";

export interface TaskEventsState {
  events: ExecutionEvent[];
  latestPhase: string | null;
  latestMessage: string | null;
  streamError: boolean;
}

const EMPTY: TaskEventsState = { events: [], latestPhase: null, latestMessage: null, streamError: false };

/** Subscribes for as long as `taskId` is set; unsubscribes and resets on
 * unmount or when `taskId` changes (including to null). One task at a time
 * by design — this hook doesn't try to multiplex several live streams. */
export function useTaskEvents(taskId: string | null): TaskEventsState {
  const [state, setState] = useState<TaskEventsState>(EMPTY);

  useEffect(() => {
    setState(EMPTY);
    if (!taskId) return;

    const unsubscribe = iqooService.subscribeToTaskEvents(
      taskId,
      (event) => {
        setState((prev) => ({
          events: [...prev.events, event],
          latestPhase: event.phase,
          latestMessage: event.message,
          streamError: false,
        }));
      },
      () => {
        setState((prev) => ({ ...prev, streamError: true }));
      }
    );

    return unsubscribe;
  }, [taskId]);

  return state;
}
