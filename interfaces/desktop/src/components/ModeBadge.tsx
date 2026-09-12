export type DataMode = "planned" | "demo" | "live";

const MODE_STYLES: Record<DataMode, { label: string; className: string }> = {
  // Quiet — nothing to build yet, no risk of being mistaken for real.
  planned: { label: "PLANNED", className: "border-line text-mute" },
  // Loud on purpose — this is the one that could be mistaken for real data
  // if it didn't stand out.
  demo: { label: "DEMO", className: "border-warn/40 bg-warn/10 text-warn" },
  // Quiet in a different way — "real" should read as the unremarkable
  // default, not something that needs to shout for attention.
  live: { label: "LIVE", className: "border-success/30 text-success" },
};

export function ModeBadge({ mode }: { mode: DataMode }) {
  const style = MODE_STYLES[mode];
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 font-mono-data text-[10px] font-medium tracking-wide ${style.className}`}
    >
      {style.label}
    </span>
  );
}
