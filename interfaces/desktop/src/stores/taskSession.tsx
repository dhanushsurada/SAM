import { createContext, useCallback, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { iqooService } from "@/services/iqoo";
import { ApiError } from "@/api/client";
import type { TaskRecord, TaskCreateRequest, HealthStatus, ExecutionEvent } from "@/api/types";
import { useTaskEvents } from "@/features/iqoo/useTaskEvents";

function errorMessage(e: unknown): string {
  return e instanceof ApiError ? e.detail : "Couldn't reach the gateway. Is it running on port 8420?";
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

  useEffect(() => {
    if (!selectedTaskId || events.length === 0) return;
    const latest = events[events.length - 1];
    setSessionTasks((prev) =>
      prev.map((t) => (t.task_id === selectedTaskId ? { ...t, status: latest.phase } : t))
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
