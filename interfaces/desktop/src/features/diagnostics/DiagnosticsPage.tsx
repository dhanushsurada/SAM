import { useCallback, useEffect, useState } from "react";
import { FiServer, FiHardDrive, FiWifi, FiCpu, FiRefreshCw } from "react-icons/fi";
import { PageHeader } from "@/components/PageHeader";
import { StatusPill, type SamState } from "@/components/StatusPill";
import { Button } from "@/components/Button";
import { getEnvironmentReport, getHealth, type EnvironmentReport } from "@/api/client";
import type { HealthStatus } from "@/api/types";

interface CheckRow {
  label: string;
  icon: typeof FiServer;
  state: SamState;
  detail: string;
}

function issueState(severity: string): SamState {
  if (severity === "error") return "FAILED";
  if (severity === "warning") return "WAITING";
  if (severity === "ok") return "SUCCESS";
  return "UNAVAILABLE";
}

export function DiagnosticsPage() {
  const [report, setReport] = useState<EnvironmentReport | null>(null);
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [environment, gateway] = await Promise.all([getEnvironmentReport(), getHealth()]);
      setReport(environment);
      setHealth(gateway);
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "SAM environment diagnostics are unavailable.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  const rows: CheckRow[] = report ? [
    { label: "Operating system", icon: FiCpu, state: "SUCCESS", detail: `${report.environment.os.name} ${report.environment.os.version} · ${report.environment.os.architecture}` },
    { label: "Python", icon: FiCpu, state: report.environment.python.selected.supported ? "SUCCESS" : "FAILED", detail: report.environment.python.selected.path ?? report.environment.python.selected.detail ?? "No supported interpreter" },
    { label: "Available memory", icon: FiHardDrive, state: report.environment.hardware.memory_gb === null ? "UNVERIFIED" : "SUCCESS", detail: report.environment.hardware.memory_gb === null ? "not detected" : `${report.environment.hardware.memory_gb} GB` },
    { label: "Free disk space", icon: FiHardDrive, state: report.environment.hardware.disk.free_gb === null ? "UNVERIFIED" : report.environment.hardware.disk.free_gb < 5 ? "WAITING" : "SUCCESS", detail: report.environment.hardware.disk.free_gb === null ? "not detected" : `${report.environment.hardware.disk.free_gb} GB` },
    ...Object.entries(report.environment.tools).map(([name, tool]) => ({
      label: name,
      icon: FiServer,
      state: !tool.installed ? "UNAVAILABLE" as SamState : "SUCCESS" as SamState,
      detail: tool.version ?? (tool.installed ? tool.path ?? "installed" : "not installed"),
    })),
    { label: "Ollama", icon: FiServer, state: report.capabilities.ollama.available ? "SUCCESS" : report.capabilities.ollama.installed ? "WAITING" : "UNAVAILABLE", detail: `${report.capabilities.ollama.state} · ${report.capabilities.ollama.detail}` },
    { label: "Configured model", icon: FiCpu, state: report.capabilities.ollama.configured_model_available ? "SUCCESS" : "WAITING", detail: report.capabilities.ollama.configured_model ?? "no primary model selected" },
    { label: "SAM API and worker", icon: FiWifi, state: health?.status === "ok" && health.worker_alive ? "SUCCESS" : health ? "WAITING" : "UNVERIFIED", detail: health ? `${health.status} · worker ${health.worker_alive ? "running" : "stopped"}` : "gateway status unavailable" },
    ...Object.entries(report.capabilities.features).map(([name, feature]) => ({
      label: `${name[0].toUpperCase()}${name.slice(1)} capability`,
      icon: name === "vision" ? FiCpu : FiServer,
      state: feature.available ? "SUCCESS" as SamState : "UNAVAILABLE" as SamState,
      detail: feature.available ? "available" : [feature.missing_packages.join(", "), feature.missing_system_prerequisites.join(", ")].filter(Boolean).join(" · ") || feature.reason,
    })),
  ] : [];

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <div className="flex items-start justify-between gap-3">
        <PageHeader title="Diagnostics" mode="live" description="Live environment, dependency, runtime, and optional-capability status. Credential values are excluded." />
        <Button variant="secondary" size="sm" onClick={() => void refresh()} loading={loading} aria-label="Refresh diagnostics"><FiRefreshCw size={14} /></Button>
      </div>
      {error && <p role="alert" className="rounded-md border border-danger/25 bg-danger/5 px-3 py-2 text-xs text-danger">{error}. Check that SAM's local API is running, then refresh.</p>}
      {loading && !report && <p className="text-sm text-mute">Loading environment diagnostics…</p>}
      {report && <>
        <div className="space-y-1.5">
          {rows.map((row) => (
            <div key={row.label} className="flex items-center justify-between gap-3 rounded-md border border-line bg-surface px-3 py-2.5">
              <div className="flex min-w-0 items-center gap-2.5">
                <row.icon size={15} className="shrink-0 text-mute" />
                <span className="text-sm text-ink">{row.label}</span>
              </div>
              <div className="flex min-w-0 items-center gap-2">
                <span className="truncate text-right font-mono-data text-xs text-mute">{row.detail}</span>
                <StatusPill state={row.state} />
              </div>
            </div>
          ))}
        </div>
        <section className="space-y-2 rounded-md border border-line bg-surface p-3">
          <h2 className="text-sm font-medium text-ink">Installation and recovery</h2>
          <p className="text-xs text-mute">Onboarding: {report.setup.journey.state}. Free space: {report.environment.hardware.disk.free_gb ?? "unknown"} GB.</p>
          {Object.entries(report.setup.installation.steps ?? {}).map(([step, status]) => (
            <div key={step} className="flex items-center justify-between gap-2 text-xs">
              <span className="text-ink">{step.replaceAll("_", " ")}</span>
              <span className="text-mute">{status.state}{status.detail ? ` · ${status.detail}` : ""}</span>
            </div>
          ))}
        </section>
        <section className="space-y-2 rounded-md border border-line bg-surface p-3">
          <h2 className="text-sm font-medium text-ink">Prerequisites and recovery guidance</h2>
          {report.diagnostics.length === 0 && <p className="text-xs text-mute">No compatibility issues were reported.</p>}
          {report.diagnostics.map((issue, index) => (
            <div key={`${issue.area}-${index}`} className="flex items-start justify-between gap-3 text-xs">
              <span className="text-ink">{issue.message}</span>
              <StatusPill state={issueState(issue.severity)} />
            </div>
          ))}
        </section>
      </>}
    </div>
  );
}
