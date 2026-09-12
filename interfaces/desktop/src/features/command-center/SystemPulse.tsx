import { StatusPill, type SamState } from "@/components/StatusPill";
import { ModeBadge } from "@/components/ModeBadge";
import type { HealthStatus } from "@/api/types";

function overallState(health: HealthStatus | null, error: string | null): SamState {
  if (error) return "UNAVAILABLE";
  if (!health) return "UNVERIFIED";
  return health.status === "ok" ? "SUCCESS" : "WAITING";
}

export function SystemPulse({
  health,
  loading,
  error,
}: {
  health: HealthStatus | null;
  loading: boolean;
  error: string | null;
}) {
  const state = overallState(health, error);

  return (
    <div className="space-y-2 rounded-lg border border-line bg-surface p-4 shadow-panel">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-medium text-mute">System status</h2>
        <ModeBadge mode="live" />
      </div>
      <div className="flex items-center gap-2">
        <StatusPill state={state} label={loading ? "Checking…" : undefined} live />
        {health?.active_task && <span className="font-mono-data text-xs text-mute">1 task running</span>}
      </div>
      {error && <p className="text-xs text-danger">{error}</p>}
      {health && !error && (
        <p className="font-mono-data text-xs text-mute">
          queue {health.queue_depth} · gateway only — see Diagnostics for the rest, once it's real
        </p>
      )}
    </div>
  );
}
