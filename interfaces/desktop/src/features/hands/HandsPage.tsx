import { PageHeader } from "@/components/PageHeader";
import { StatusPill, type SamState } from "@/components/StatusPill";
import { useTaskSession } from "@/stores/taskSession";
import type { HealthStatus } from "@/api/types";
import { CAPABILITIES, type HandsCapability, type HealthCheckField } from "./capabilities";

function checkState(health: HealthStatus | null, field: HealthCheckField): SamState {
  if (!health) return "UNVERIFIED";
  const value = health[field];
  if (value === null) return "UNVERIFIED";
  return value ? "SUCCESS" : "FAILED";
}

function checkLabel(state: SamState): string {
  return state === "SUCCESS" ? "PASS" : state === "FAILED" ? "FAIL" : "UNVERIFIED";
}

function CapabilityCard({ capability, health }: { capability: HandsCapability; health: HealthStatus | null }) {
  const unavailable = capability.availability === "not-implemented";

  return (
    <li className="space-y-3 rounded-lg border border-line bg-surface p-4 shadow-panel">
      <div className="flex items-start justify-between gap-3">
        <h2 className="text-sm font-medium text-ink">{capability.name}</h2>
        {unavailable && <StatusPill state="UNAVAILABLE" label="Not implemented" />}
        {capability.availability === "implemented" && (
          <span className="shrink-0 rounded-full border border-line px-2 py-0.5 text-[11px] text-mute">Implemented</span>
        )}
      </div>

      <p className={`text-sm ${unavailable ? "text-mute" : "text-ink"}`}>{capability.summary}</p>

      {capability.abilities.length > 0 && (
        <ul className="space-y-1 border-l border-line pl-3 text-xs text-mute">
          {capability.abilities.map((a) => (
            <li key={a}>{a}</li>
          ))}
        </ul>
      )}

      {capability.checks && (
        <div className="space-y-1.5 text-xs">
          {capability.checks.map((c) => {
            const state = checkState(health, c.field);
            return (
              <div key={c.label} className="flex items-center justify-between gap-3">
                <span className="text-mute">{c.label}</span>
                <StatusPill state={state} label={checkLabel(state)} />
              </div>
            );
          })}
        </div>
      )}

      <div className="space-y-0.5 text-xs text-mute">
        <p>{capability.needs}</p>
        <p className="font-mono-data text-[11px] text-unverified">{capability.source}</p>
      </div>
    </li>
  );
}

/**
 * The Hands: SAM's ways of acting on a computer. Browser control is one card
 * here, alongside desktop control, vision and the terminal — it is not the
 * product. The list is static (read from the code that executes each one,
 * see capabilities.ts); only the vision/Whisper rows are live, from the
 * gateway's health check.
 */
export function HandsPage() {
  const { health, healthError } = useTaskSession();

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <PageHeader
        title="Hands"
        description="How SAM acts on a computer. Each task uses whichever of these it needs; the browser is one of them."
      />
      <p className="text-xs text-mute">
        Only the vision and Whisper checks are reported by the gateway. For everything else, the code exists and SAM
        can call it, but whether it works on this machine (permissions, installed packages) isn't reported yet: run
        a task to find out. SAM doesn't count an action as done until it has checked the result.
      </p>
      {healthError && <p className="text-xs text-danger">{healthError}</p>}

      <ul className="grid gap-4 md:grid-cols-2">
        {CAPABILITIES.map((capability) => (
          <CapabilityCard key={capability.id} capability={capability} health={health} />
        ))}
      </ul>
    </div>
  );
}
