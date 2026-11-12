export type DataMode = "planned" | "demo" | "live";

export function ModeBadge({ mode }: { mode: DataMode }) {
  if (mode === "live") {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-500/10 px-2 py-0.5 font-mono-data text-[10px] font-medium tracking-wide text-emerald-400 border border-emerald-500/20 shadow-sm">
        <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
        Live
      </span>
    );
  }
  if (mode === "demo") {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full bg-amber-500/10 px-2 py-0.5 font-mono-data text-[10px] font-medium tracking-wide text-amber-400 border border-amber-500/20">
        Demo
      </span>
    );
  }
  return null;
}
