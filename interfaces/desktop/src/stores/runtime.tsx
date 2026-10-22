import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import {
  runtimeStatus,
  runtimeStart,
  runtimeStop,
  runtimeRestart,
  ollamaStart,
  modelsList,
  modelSelect,
  modelPull,
  cancelModelPull,
  onModelPullProgress,
  getSetupState,
  setSetupState,
} from "@/lib/native";
import type {
  RuntimeSnapshot,
  LifecycleResponse,
  OllamaActionResult,
  ModelPullProgress,
  ProcessName,
  SetupState,
  SetupJourneyState,
} from "@/lib/native";
import type { BrainStatus } from "@/api/types";
import { isNative } from "@/lib/native";

/**
 * The one place Onboarding, Settings, and Permissions all read runtime
 * state from — Phase C §15/§20's explicit requirement: none of them
 * invents its own query. A component that needs live data calls
 * useRuntimePolling() in its own effect; polling only runs while at
 * least one such component is mounted, never on a fixed background
 * timer the whole app pays for (Phase C §15: "only while runtime-
 * sensitive UI is visible... do not poll every second").
 *
 * Errors here are messages meant to reach a UI, same rule native.ts
 * already follows and the Internal-Server-Error incident two rounds
 * back exists to not repeat: every action below returns/throws a real
 * message from the layer that actually failed (the Rust bridge's Err
 * string, which is itself either sam_cli.py's own failure text or the
 * gateway's `detail` field) — never a caught exception's generic
 * toString(), and never a guess.
 */

interface RuntimeContextValue {
  snapshot: RuntimeSnapshot | null;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;

  startProcess: (name?: ProcessName) => Promise<LifecycleResponse>;
  stopProcess: (name?: ProcessName) => Promise<LifecycleResponse>;
  restartProcess: (name?: ProcessName) => Promise<LifecycleResponse>;
  startOllama: () => Promise<OllamaActionResult>;

  models: BrainStatus | null;
  modelsLoading: boolean;
  modelsError: string | null;
  refreshModels: () => Promise<void>;
  selectModel: (name: string) => Promise<BrainStatus>;

  pulling: boolean;
  pullProgress: ModelPullProgress | null;
  pullError: string | null;
  pullModel: (name: string) => Promise<void>;
  cancelPull: () => Promise<void>;

  setupState: SetupState | null;
  advanceSetupState: (state: SetupJourneyState, model?: string) => Promise<void>;

  /** A component calls this in its own effect to opt into polling while
   * it's mounted. Returns the unsubscribe to call on cleanup. Multiple
   * mounted consumers share one interval, not one each. */
  subscribeToPolling: () => () => void;
}

const RuntimeContext = createContext<RuntimeContextValue | null>(null);

const POLL_INTERVAL_MS = 4000;

function describeError(e: unknown): string {
  return e instanceof Error ? e.message : "an unexpected error occurred";
}

export function RuntimeProvider({ children }: { children: ReactNode }) {
  const [snapshot, setSnapshot] = useState<RuntimeSnapshot | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [models, setModels] = useState<BrainStatus | null>(null);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [modelsError, setModelsError] = useState<string | null>(null);

  const [pulling, setPulling] = useState(false);
  const [pullProgress, setPullProgress] = useState<ModelPullProgress | null>(null);
  const [pullError, setPullError] = useState<string | null>(null);

  const [setupState, setSetupStateValue] = useState<SetupState | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const result = await runtimeStatus();
      setSnapshot(result);
      setError(null);
    } catch (e) {
      setError(describeError(e));
    } finally {
      setLoading(false);
    }
  }, []);

  const refreshModels = useCallback(async () => {
    setModelsLoading(true);
    try {
      const result = await modelsList();
      setModels(result);
      setModelsError(null);
    } catch (e) {
      setModelsError(describeError(e));
    } finally {
      setModelsLoading(false);
    }
  }, []);

  // ─── Polling: ref-counted, shared across every mounted subscriber ──────
  const subscriberCount = useRef(0);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const subscribeToPolling = useCallback((): (() => void) => {
    subscriberCount.current += 1;
    if (subscriberCount.current === 1 && intervalRef.current === null) {
      void refresh();
      intervalRef.current = setInterval(() => void refresh(), POLL_INTERVAL_MS);
    }
    return () => {
      subscriberCount.current = Math.max(0, subscriberCount.current - 1);
      if (subscriberCount.current === 0 && intervalRef.current !== null) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [refresh]);

  useEffect(() => {
    return () => {
      if (intervalRef.current !== null) clearInterval(intervalRef.current);
    };
  }, []);

  // Setup state is read once on mount, not polled — it only changes when
  // this same app writes it (onboarding finishing), never from outside.
  useEffect(() => {
    getSetupState()
      .then(setSetupStateValue)
      .catch(() => setSetupStateValue({ state: "first_run", selected_model: null }));
  }, []);

  // Pull progress arrives as events, independent of the polling above —
  // a pull can easily outlast several poll cycles.
  useEffect(() => {
    let unlisten: (() => void) | undefined;
    onModelPullProgress((progress) => {
      setPullProgress(progress);
      if (progress.status === "error") {
        setPullError(progress.error ?? "the model download failed");
        setPulling(false);
      } else if (progress.status === "success") {
        setPulling(false);
      } else if (progress.status === "cancelled") {
        setPulling(false);
      }
    }).then((fn) => {
      unlisten = fn;
    });
    return () => unlisten?.();
  }, []);

  const startProcess = useCallback((name?: ProcessName) => runtimeStart(name).then((r) => {
    void refresh();
    return r;
  }), [refresh]);

  const stopProcess = useCallback((name?: ProcessName) => runtimeStop(name).then((r) => {
    void refresh();
    return r;
  }), [refresh]);

  const restartProcess = useCallback((name?: ProcessName) => runtimeRestart(name).then((r) => {
    void refresh();
    return r;
  }), [refresh]);

  const startOllama = useCallback(() => ollamaStart().then((r) => {
    void refresh();
    return r;
  }), [refresh]);

  const selectModel = useCallback((name: string) => modelSelect(name).then((r) => {
    void refresh();
    void refreshModels();
    return r;
  }), [refresh, refreshModels]);

  const pullModel = useCallback(async (name: string) => {
    setPulling(true);
    setPullError(null);
    setPullProgress(null);
    try {
      await modelPull(name);
    } catch (e) {
      setPullError(describeError(e));
    } finally {
      setPulling(false);
      void refreshModels();
    }
  }, [refreshModels]);

  const cancelPull = useCallback(async () => {
    try {
      await cancelModelPull();
    } catch (e) {
      setPullError(describeError(e));
    }
  }, []);

  const advanceSetupState = useCallback(async (state: SetupJourneyState, model?: string) => {
    const result = await setSetupState(state, model);
    setSetupStateValue(result);
  }, []);

  const value: RuntimeContextValue = {
    snapshot, loading, error, refresh,
    startProcess, stopProcess, restartProcess, startOllama,
    models, modelsLoading, modelsError, refreshModels, selectModel,
    pulling, pullProgress, pullError, pullModel, cancelPull,
    setupState, advanceSetupState,
    subscribeToPolling,
  };

  return <RuntimeContext.Provider value={value}>{children}</RuntimeContext.Provider>;
}

export function useRuntime(): RuntimeContextValue {
  const ctx = useContext(RuntimeContext);
  if (!ctx) throw new Error("useRuntime must be used within a RuntimeProvider");
  return ctx;
}

/** Call in a component's own effect to opt into live polling while it's
 * mounted — e.g. `useRuntimePolling()` at the top of Settings' runtime
 * section or Onboarding's system-check step. Does nothing by itself
 * beyond subscribing/unsubscribing; read `snapshot` via useRuntime(). */
export function useRuntimePolling(): void {
  const { subscribeToPolling } = useRuntime();
  useEffect(() => (isNative() ? subscribeToPolling() : undefined), [subscribeToPolling]);
}
