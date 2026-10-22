import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { iqooService } from "@/services/iqoo";
import { ApiError } from "@/api/client";
import type { TaskRecord, TaskCreateRequest, HealthStatus, ExecutionEvent } from "@/api/types";
import { useTaskEvents } from "@/features/iqoo/useTaskEvents";
import { TERMINAL_PHASES } from "@/api/types";

const SESSION_STORAGE_KEY = "sam.desktop.task-session.v1";
const MAX_RESTORED_TASKS = 50;

/** The gateway publishes a task's final result/error text AS its terminal
 * event's message (gateway.py). Copy it onto the record so a task that has
 * finished can be read back without re-subscribing to its stream. */
function withOutcome(task: TaskRecord, latest: ExecutionEvent): TaskRecord {
  if (latest.phase === "completed") return { ...task, status: latest.phase, result_text: latest.message };
  if (latest.phase === "failed") return { ...task, status: latest.phase, error: latest.message };
  return { ...task, status: latest.phase };
}

function errorMessage(e: unknown): string {
  return e instanceof ApiError ? e.detail : "Couldn't reach the configured SAM gateway. Check runtime status in Settings.";
}

interface TaskSessionValue {
  sessionTasks: TaskRecord[];
  selectedTaskId: string | null;
  selectedTask: TaskRecord | null;
  selectTask: (id: string | null) => void;
  events: ExecutionEvent[];
  streamError: boolean;

  submitting: boolean;
  submitError: string | null;
  submitTask: (req: TaskCreateRequest) => Promise<void>;

  cancelling: boolean;
  cancelSelected: () => Promise<void>;
  retrying: boolean;
  retrySelected: () => Promise<void>;

  resetting: boolean;
  demoReset: () => Promise<void>;

  health: HealthStatus | null;
  healthLoading: boolean;
  healthError: string | null;
  refreshHealth: () => Promise<void>;
}

const TaskSessionContext = createContext<TaskSessionValue | null>(null);

/**
 * One iQOO task session, shared by every screen that touches it —
 * Command Center's quick input and `/iqoo`'s full workspace are two views
 * onto the *same* state, not two independent copies. Without this, a task
 * submitted from Home wouldn't show up if you navigated to `/iqoo`, and
 * vice versa (React Router unmounts the outgoing route's component tree on
 * navigation, so per-page useState alone doesn't survive the switch).
 */
export function TaskSessionProvider({ children }: { children: ReactNode }) {
  const [sessionTasks, setSessionTasks] = useState<TaskRecord[]>([]);
  const [sessionRestored, setSessionRestored] = useState(false);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const [resetting, setResetting] = useState(false);

  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [healthLoading, setHealthLoading] = useState(false);
  const [healthError, setHealthError] = useState<string | null>(null);

  const { events, streamError } = useTaskEvents(selectedTaskId);
  const selectedTask = sessionTasks.find((t) => t.task_id === selectedTaskId) ?? null;
  const pollInFlight = useRef(false);

  // Persist identifiers only. Task contents and attachments remain in SAM's
  // local task store and are reloaded from the API after an app restart.
  useEffect(() => {
    let active = true;
    const restore = async () => {
      let saved: { taskIds?: unknown; selectedTaskId?: unknown } = {};
      try {
        const raw = window.localStorage.getItem(SESSION_STORAGE_KEY);
        if (raw) saved = JSON.parse(raw);
      } catch {
        // A malformed browser preference is ignored; task records stay in Core.
      }
      const ids = Array.isArray(saved.taskIds)
        ? saved.taskIds.filter((id): id is string => typeof id === "string").slice(-MAX_RESTORED_TASKS)
        : [];
      const records = await Promise.all(ids.map(async (id) => {
        try { return await iqooService.getTask(id); } catch { return null; }
      }));
      if (!active) return;
      const restored = records.filter((task): task is TaskRecord => task !== null);
      setSessionTasks(restored);
      const wanted = typeof saved.selectedTaskId === "string" ? saved.selectedTaskId : null;
      setSelectedTaskId(wanted && restored.some((task) => task.task_id === wanted)
        ? wanted : restored[0]?.task_id ?? null);
      setSessionRestored(true);
    };
    void restore();
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!sessionRestored) return;
    try {
      window.localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify({
        taskIds: sessionTasks.slice(-MAX_RESTORED_TASKS).map((task) => task.task_id),
        selectedTaskId,
      }));
    } catch {
      // Storage can be disabled or full; live task sync continues in memory.
    }
  }, [sessionRestored, sessionTasks, selectedTaskId]);

  // Refresh every active task from Core. SSE is fast for the selected task;
  // this authoritative poll keeps background task rows in sync too and
  // repairs missed events after reconnects or route changes.
  useEffect(() => {
    const refreshActiveTasks = async () => {
      if (pollInFlight.current) return;
      const activeTasks = sessionTasks.filter((task) => !TERMINAL_PHASES.has(task.status as never));
      if (!activeTasks.length) return;
      pollInFlight.current = true;
      try {
        const updated = await Promise.all(activeTasks.map(async (task) => {
          try { return await iqooService.getTask(task.task_id); } catch { return null; }
        }));
        const byId = new Map(updated.filter((task): task is TaskRecord => task !== null)
          .map((task) => [task.task_id, task]));
        if (byId.size) setSessionTasks((current) => current.map((task) => byId.get(task.task_id) ?? task));
      } finally {
        pollInFlight.current = false;
      }
    };
    const interval = setInterval(() => void refreshActiveTasks(), 5000);
    return () => clearInterval(interval);
  }, [sessionTasks]);

  useEffect(() => {
    if (!selectedTaskId || events.length === 0) return;
    const latest = events[events.length - 1];
    setSessionTasks((prev) =>
      prev.map((t) => (t.task_id === selectedTaskId ? withOutcome(t, latest) : t))
    );
  }, [events, selectedTaskId]);

  const refreshHealth = useCallback(async () => {
    setHealthLoading(true);
    try {
      setHealth(await iqooService.getHealth());
      setHealthError(null);
    } catch (e) {
      setHealthError(errorMessage(e));
    } finally {
      setHealthLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshHealth();
    const interval = setInterval(refreshHealth, 15000);
    return () => clearInterval(interval);
  }, [refreshHealth]);

  const submitTask = async (req: TaskCreateRequest) => {
    setSubmitting(true);
    setSubmitError(null);
    try {
      const task = await iqooService.createTask(req);
      setSessionTasks((prev) => [...prev, task]);
      setSelectedTaskId(task.task_id);
    } catch (e) {
      setSubmitError(errorMessage(e));
    } finally {
      setSubmitting(false);
    }
  };

  const cancelSelected = async () => {
    if (!selectedTaskId) return;
    setCancelling(true);
    try {
      const updated = await iqooService.cancelTask(selectedTaskId);
      setSessionTasks((prev) => prev.map((t) => (t.task_id === updated.task_id ? updated : t)));
    } catch (e) {
      setSubmitError(errorMessage(e));
    } finally {
      setCancelling(false);
    }
  };

  const retrySelected = async () => {
    if (!selectedTaskId) return;
    setRetrying(true);
    try {
      const fresh = await iqooService.retryTask(selectedTaskId);
      setSessionTasks((prev) => [...prev, fresh]);
      setSelectedTaskId(fresh.task_id);
    } catch (e) {
      setSubmitError(errorMessage(e));
    } finally {
      setRetrying(false);
    }
  };

  const demoReset = async () => {
    setResetting(true);
    try {
      await iqooService.demoReset();
      setSessionTasks([]);
      setSelectedTaskId(null);
      await refreshHealth();
    } catch (e) {
      setSubmitError(errorMessage(e));
    } finally {
      setResetting(false);
    }
  };

  const value: TaskSessionValue = {
    sessionTasks,
    selectedTaskId,
    selectedTask,
    selectTask: setSelectedTaskId,
    events,
    streamError,
    submitting,
    submitError,
    submitTask,
    cancelling,
    cancelSelected,
    retrying,
    retrySelected,
    resetting,
    demoReset,
    health,
    healthLoading,
    healthError,
    refreshHealth,
  };

  return <TaskSessionContext.Provider value={value}>{children}</TaskSessionContext.Provider>;
}

export function useTaskSession(): TaskSessionValue {
  const ctx = useContext(TaskSessionContext);
  if (!ctx) throw new Error("useTaskSession must be used within a TaskSessionProvider");
  return ctx;
}
