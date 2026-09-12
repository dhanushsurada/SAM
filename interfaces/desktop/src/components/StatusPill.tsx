/**
 * The one component every execution-state surface shares: Command Center,
 * Task Execution / Agent Console, iQOO workspace, System Diagnostics. Using
 * a single source of truth for this mapping is what keeps "FAILED" red
 * everywhere and stops any screen from inventing its own status colors.
 */
export type SamState =
  | "IDLE"
  | "LISTENING"
  | "THINKING"
  | "EXECUTING"
  | "WAITING"
  | "NEEDS_CONFIRMATION"
  | "SUCCESS"
  | "FAILED"
  | "CANCELLED"
  | "UNAVAILABLE"
  | "UNVERIFIED";

interface StateVisual {
  label: string;
  dotClass: string;
  textClass: string;
  /** States where something is actively in progress get a pulsing dot;
   * everything else — including WAITING, which is passive, not active —
   * stays still. prefers-reduced-motion zeroes this globally either way. */
  pulse: boolean;
}

const STATES: Record<SamState, StateVisual> = {
  IDLE: { label: "Idle", dotClass: "bg-mute", textClass: "text-mute", pulse: false },
  LISTENING: { label: "Listening", dotClass: "bg-ember", textClass: "text-ember-text", pulse: true },
  THINKING: { label: "Thinking", dotClass: "bg-ember", textClass: "text-ember-text", pulse: true },
  EXECUTING: { label: "Executing", dotClass: "bg-ember", textClass: "text-ember-text", pulse: true },
  WAITING: { label: "Waiting", dotClass: "bg-warn", textClass: "text-warn", pulse: false },
  NEEDS_CONFIRMATION: {
    label: "Needs confirmation",
    dotClass: "bg-warn",
    textClass: "text-warn",
    pulse: true,
  },
  SUCCESS: { label: "Success", dotClass: "bg-success", textClass: "text-success", pulse: false },
  FAILED: { label: "Failed", dotClass: "bg-danger", textClass: "text-danger", pulse: false },
  CANCELLED: { label: "Cancelled", dotClass: "bg-mute", textClass: "text-mute", pulse: false },
  UNAVAILABLE: {
    label: "Unavailable",
    dotClass: "bg-unverified",
    textClass: "text-unverified",
    pulse: false,
  },
  UNVERIFIED: {
    label: "Unverified",
    dotClass: "bg-unverified",
    textClass: "text-unverified",
    pulse: false,
  },
};

export interface StatusPillProps {
  state: SamState;
  /** Override the default label — e.g. "Opening YouTube" instead of the
   * generic "Executing" — while keeping the shared color semantics. */
  label?: string;
  /** Marks this as the one live region a screen actually wants announced
   * on change. Default false — a list of past states shouldn't all talk. */
  live?: boolean;
}

export function StatusPill({ state, label, live = false }: StatusPillProps) {
  const visual = STATES[state];
  return (
    <span
      role="status"
      aria-live={live ? "polite" : undefined}
      className={`inline-flex items-center gap-1.5 rounded-full border border-line bg-surface px-2.5 py-1 text-xs font-medium ${visual.textClass}`}
    >
      <span className="relative flex h-1.5 w-1.5">
        {visual.pulse && (
          <span
            aria-hidden="true"
            className={`absolute inline-flex h-full w-full animate-ping rounded-full opacity-60 ${visual.dotClass}`}
          />
        )}
        <span className={`relative inline-flex h-1.5 w-1.5 rounded-full ${visual.dotClass}`} />
      </span>
      {label ?? visual.label}
    </span>
  );
}
