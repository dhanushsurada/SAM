import { Link } from "react-router-dom";
import { ModeBadge } from "@/components/ModeBadge";
import { StatusPill } from "@/components/StatusPill";
import { Card } from "@/components/Card";
import { useBrain } from "@/features/brain/useBrain";

/** Command Center's one-glance Brain summary. */
export function BrainCard() {
  const { status, loading, error } = useBrain();
  const ready = status?.status === "ready";

  return (
    <Card className="space-y-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-medium text-mute">Brain engine</h2>
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
            <span className="truncate font-mono text-xs text-ink">{status.active_model ?? "No active model"}</span>
          </div>
          <div className="flex items-center justify-between font-mono text-[11px] text-mute/80 border-t border-line/40 pt-2">
            <span>Provider: {status.provider === "ollama" ? "Ollama Local" : status.provider}</span>
            <span>{status.active_source === "fallback" ? "Fallback" : "Primary"}</span>
          </div>
          {status.detail && <p className="text-xs text-warn">{status.detail}</p>}
        </>
      )}
    </Card>
  );
}
