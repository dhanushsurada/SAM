import { FiServer, FiHardDrive, FiWifi, FiCpu } from "react-icons/fi";
import { PageHeader } from "@/components/PageHeader";
import { StatusPill, type SamState } from "@/components/StatusPill";

interface CheckRow {
  label: string;
  icon: typeof FiServer;
  state: SamState;
  detail: string;
}

// Deliberately mixes real states with UNVERIFIED rather than defaulting
// everything to SUCCESS — the brief is explicit that UNVERIFIED must never
// be shown as healthy, so the demo data models that distinction too.
const CHECKS: CheckRow[] = [
  { label: "Python", icon: FiCpu, state: "SUCCESS", detail: "3.11.6" },
  { label: "Ollama", icon: FiServer, state: "SUCCESS", detail: "running, port 11434" },
  { label: "Configured model present", icon: FiCpu, state: "SUCCESS", detail: "qwen2.5:14b" },
  { label: "Data directory", icon: FiHardDrive, state: "SUCCESS", detail: "~/.sam/data" },
  { label: "API port 8420", icon: FiWifi, state: "SUCCESS", detail: "listening" },
  { label: "Telegram integration", icon: FiWifi, state: "UNVERIFIED", detail: "token configured, not pinged" },
  { label: "License", icon: FiHardDrive, state: "UNVERIFIED", detail: "see Licensing" },
];

export function DiagnosticsPage() {
  return (
    <div className="mx-auto max-w-2xl space-y-4">
      <PageHeader
        title="Diagnostics"
        mode="demo"
        description="sam doctor–style status. runtime/health/status.py computes real PASS/WARN/FAIL/UNVERIFIED states internally — nothing exposes them over HTTP yet."
      />

      <div className="space-y-1.5">
        {CHECKS.map((c) => (
          <div key={c.label} className="flex items-center justify-between rounded-md border border-line bg-surface px-3 py-2.5">
            <div className="flex items-center gap-2.5">
              <c.icon size={15} className="text-mute" />
              <span className="text-sm text-ink">{c.label}</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="font-mono-data text-xs text-mute">{c.detail}</span>
              <StatusPill state={c.state} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
