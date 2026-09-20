import { useCallback, useEffect, useState } from "react";
import { ApiError } from "@/api/client";
import type { BrainStatus } from "@/api/types";
import { brainService } from "@/services/brain";

export interface BrainState {
  status: BrainStatus | null;
  loading: boolean;
  /** The gateway itself couldn't be reached. (Ollama being down is NOT an
   * error here — it arrives as status.status === "unavailable".) */
  error: string | null;
  /** Name of the model a switch is in flight for. */
  selecting: string | null;
  /** Why the last switch was refused, in the server's own words. */
  selectError: string | null;
  /** Set after a switch the server confirmed; cleared on the next action. */
  switchedTo: string | null;
  refresh: () => Promise<void>;
  select: (model: string) => Promise<void>;
}

function describe(e: unknown): string {
  return e instanceof ApiError ? e.detail : "Couldn't reach the SAM gateway. Is it running on port 8420?";
}

/**
 * Brain state for one screen. Every value comes from the server: a switch
 * is only shown as done once POST /api/models/select has returned the new
 * status, and a refused switch re-reads the server's state instead of
 * trusting the UI's copy (a 409 means a task started since the last read).
 */
export function useBrain(): BrainState {
  const [status, setStatus] = useState<BrainStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selecting, setSelecting] = useState<string | null>(null);
  const [selectError, setSelectError] = useState<string | null>(null);
  const [switchedTo, setSwitchedTo] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setSwitchedTo(null);
    try {
      setStatus(await brainService.getBrainStatus());
      setError(null);
    } catch (e) {
      setError(describe(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const select = useCallback(async (model: string) => {
    setSelecting(model);
    setSelectError(null);
    setSwitchedTo(null);
    try {
      const next = await brainService.selectModel(model);
      setStatus(next);
      setError(null);
      setSwitchedTo(next.selected_model);
    } catch (e) {
      setSelectError(describe(e));
      try {
        setStatus(await brainService.getBrainStatus());
      } catch {
        // Keep the last known status; the refusal message is already shown.
      }
    } finally {
      setSelecting(null);
    }
  }, []);

  return { status, loading, error, selecting, selectError, switchedTo, refresh, select };
}
