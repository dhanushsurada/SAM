import { Link } from "react-router-dom";
import { ModeBadge } from "@/components/ModeBadge";
import { StatusPill } from "@/components/StatusPill";
import { useBrain } from "@/features/brain/useBrain";

/** Command Center's one-glance Brain summary. Same live endpoint as the
 * Brain page — this card only reads; switching happens over there. */
export function BrainCard() {
  const { status, loading, error } = useBrain();
  const ready = status?.status === "ready";

  return (
    <div className="space-y-2 rounded-lg border border-line bg-surface p-4 shadow-panel">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-medium text-mute">Brain</h2>
          <ModeBadge mode="live" />
        </div>
        <Link to="/brain" className="text-xs text-ember-text hover:underline">
          Manage
        </Link>
      </div>

      {error && <p className="text-xs text-danger">{error}</p>}
      {!status && !error && <p className="text-xs text-mute">{loading ? "Checking…" : "Unknown"}</p>}

      {status && (
        <>
          <div className="flex flex-wrap items-center gap-2">
            <StatusPill state={ready ? "SUCCESS" : "UNAVAILABLE"} label={ready ? "Ready" : "Unavailable"} />
            <span className="truncate font-mono-data text-sm text-ink">{status.active_model ?? "No active model"}</span>
          </div>
          <p className="text-xs text-mute">
            {status.provider === "ollama" ? "Ollama" : status.provider}
            {status.active_source === "fallback" ? ", using the fallback" : ""}
          </p>
          {status.detail && <p className="text-xs text-warn">{status.detail}</p>}
        </>
      )}
    </div>
  );
}
