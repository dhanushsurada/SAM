import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { StatusPill, type SamState } from "@/components/StatusPill";
import { ModeBadge, type DataMode } from "@/components/ModeBadge";

const ALL_STATES: SamState[] = [
  "IDLE",
  "LISTENING",
  "THINKING",
  "EXECUTING",
  "WAITING",
  "NEEDS_CONFIRMATION",
  "SUCCESS",
  "FAILED",
  "CANCELLED",
  "UNAVAILABLE",
  "UNVERIFIED",
];
const ALL_MODES: DataMode[] = ["planned", "demo", "live"];

/** Living style guide, not a product screen — deliberately outside ROUTES
 * and the sidebar nav. Reachable at /_dev/design-system for reference while
 * building the rest of this app. */
export function DesignSystemPage() {
  return (
    <div className="mx-auto max-w-2xl space-y-8">
      <Card as="section" padding="md" className="space-y-3">
        <h2 className="text-sm font-medium text-mute">Buttons</h2>
        <div className="flex flex-wrap items-center gap-3">
          <Button variant="primary">Run task</Button>
          <Button variant="secondary">Cancel</Button>
          <Button variant="ghost">Dismiss</Button>
          <Button variant="danger">Delete</Button>
          <Button variant="primary" loading>
            Executing
          </Button>
          <Button variant="primary" disabled>
            Unavailable
          </Button>
        </div>
      </Card>

      <Card as="section" padding="md" className="space-y-3">
        <h2 className="text-sm font-medium text-mute">Status vocabulary</h2>
        <div className="flex flex-wrap gap-2">
          {ALL_STATES.map((state) => (
            <StatusPill key={state} state={state} />
          ))}
        </div>
      </Card>

      <Card as="section" padding="md" className="space-y-3">
        <h2 className="text-sm font-medium text-mute">Data mode</h2>
        <div className="flex flex-wrap gap-2">
          {ALL_MODES.map((mode) => (
            <ModeBadge key={mode} mode={mode} />
          ))}
        </div>
      </Card>

      <Card as="section" padding="md" className="space-y-3">
        <h2 className="text-sm font-medium text-mute">Card padding (sm / md / lg)</h2>
        <div className="flex flex-wrap items-start gap-3">
          <Card padding="sm" className="w-32 text-xs text-mute">
            sm — p-4, most panels
          </Card>
          <Card padding="md" className="w-32 text-xs text-mute">
            md — p-5, this page
          </Card>
          <Card padding="lg" className="w-32 text-xs text-mute">
            lg — p-6, onboarding
          </Card>
        </div>
      </Card>

      <Card as="section" padding="md" className="space-y-2">
        <h2 className="text-sm font-medium text-mute">Technical readout (mono, earned by content)</h2>
        <p className="font-mono-data text-sm text-ink">
          model qwen2.5:14b · fallback qwen2.5:7b · port 8420 · ollama{" "}
          <span className="text-success">PASS</span> · license{" "}
          <span className="text-unverified">UNVERIFIED</span>
        </p>
      </Card>
    </div>
  );
}
