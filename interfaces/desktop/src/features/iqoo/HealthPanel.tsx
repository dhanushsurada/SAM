import { FiRefreshCw } from "react-icons/fi";
import { Button } from "@/components/Button";
import { StatusPill, type SamState } from "@/components/StatusPill";
import type { HealthStatus } from "@/api/types";

function boolState(value: boolean | null): SamState {
  if (value === null) return "UNVERIFIED";
  return value ? "SUCCESS" : "FAILED";
}

function formatUptime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const h = Math.floor(m / 60);
  if (h > 0) return `${h}h ${m % 60}m`;
  if (m > 0) return `${m}m ${Math.floor(seconds % 60)}s`;
  return `${Math.floor(seconds)}s`;
}

export function HealthPanel({
  health,
  loading,
  error,
  onRefresh,
}: {
  health: HealthStatus | null;
  loading: boolean;
  error: string | null;
  onRefresh: () => void;
}) {
  return (
    <div className="space-y-3 rounded-lg border border-line bg-surface p-4 shadow-panel">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-medium text-mute">Gateway health</h2>
        <Button variant="ghost" size="sm" onClick={onRefresh} loading={loading} aria-label="Refresh health">
          <FiRefreshCw size={14} />
        </Button>
      </div>

      {error && <p className="text-xs text-danger">{error}</p>}

      {health && (
        <div className="space-y-2 text-xs">
          <Row label="Worker" state={boolState(health.worker_alive)} />
          <Row label="Brain reachable" state={boolState(health.brain_reachable)} />
          <Row label="Vision model" state={boolState(health.vision_model_available)} />
          <Row label="Whisper" state={boolState(health.whisper_available)} />
          <div className="flex items-center justify-between border-t border-line pt-2 font-mono-data text-mute">
            <span>queue {health.queue_depth}</span>
            <span>up {formatUptime(health.uptime_seconds)}</span>
            <span>{health.version}</span>
          </div>
        </div>
      )}

      {!health && !error && <p className="text-xs text-mute">Loading…</p>}
    </div>
  );
}

function Row({ label, state }: { label: string; state: SamState }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-mute">{label}</span>
      <StatusPill state={state} label={state === "SUCCESS" ? "PASS" : state === "FAILED" ? "FAIL" : "UNVERIFIED"} />
    </div>
  );
}
