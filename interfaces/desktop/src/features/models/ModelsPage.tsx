import { FiCpu } from "react-icons/fi";
import { PageHeader } from "@/components/PageHeader";
import { StatusPill } from "@/components/StatusPill";

// Shaped as a list specifically so nothing here reads as a hardcoded
// permanent identity — swapping in Qwen3 or anything else later is a data
// change, not a UI change, per the brief's explicit requirement.
const DEMO_INSTALLED = [
  { name: "qwen2.5:14b", role: "active", size_gb: 9.0 },
  { name: "qwen2.5:7b", role: "fallback", size_gb: 4.7 },
];

export function ModelsPage() {
  return (
    <div className="mx-auto max-w-2xl space-y-4">
      <PageHeader
        title="Models"
        mode="demo"
        description="Active/fallback model and Ollama availability — nothing surfaces this over HTTP today; Brain._check_ollama() and _ensure_model() are internal."
      />

      <div className="flex items-center justify-between rounded-md border border-line bg-surface px-3 py-2.5">
        <span className="text-sm text-ink">Ollama</span>
        <StatusPill state="SUCCESS" label="PASS (demo)" />
      </div>

      <div className="space-y-2">
        {DEMO_INSTALLED.map((m) => (
          <div key={m.name} className="flex items-center gap-3 rounded-md border border-line bg-surface px-3 py-2.5">
            <FiCpu size={16} className="shrink-0 text-mute" />
            <div className="min-w-0 flex-1">
              <p className="font-mono-data text-sm text-ink">{m.name}</p>
              <p className="text-xs text-mute">{m.role}</p>
            </div>
            <span className="font-mono-data text-xs text-unverified">{m.size_gb} GB</span>
          </div>
        ))}
      </div>
    </div>
  );
}
