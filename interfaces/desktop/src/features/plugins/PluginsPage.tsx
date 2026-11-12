import { useEffect, useState, useCallback } from "react";
import {
  FiBox,
  FiGithub,
  FiFolder,
  FiDatabase,
  FiExternalLink,
  FiTrash2,
  FiCheck,
  FiRefreshCw,
  FiToggleLeft,
  FiToggleRight,
  FiKey,
  FiGlobe,
  FiCpu,
} from "react-icons/fi";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/Button";
import { StatusPill } from "@/components/StatusPill";
import {
  getMCPServers,
  configureMCPServer,
  toggleMCPServer,
  deleteMCPServer,
  testMCPServer,
  type MCPServer,
  type MCPCatalogItem,
} from "@/api/client";

function getIcon(iconName: string) {
  switch (iconName) {
    case "github":
      return <FiGithub size={20} className="text-ink" />;
    case "folder":
      return <FiFolder size={20} className="text-amber-400" />;
    case "google":
      return <FiGlobe size={20} className="text-blue-400" />;
    case "slack":
      return <FiBox size={20} className="text-emerald-400" />;
    case "database":
      return <FiDatabase size={20} className="text-purple-400" />;
    default:
      return <FiCpu size={20} className="text-ember" />;
  }
}

export function PluginsPage() {
  const [servers, setServers] = useState<MCPServer[]>([]);
  const [catalog, setCatalog] = useState<MCPCatalogItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Configure modal / drawer state
  const [activeTemplate, setActiveTemplate] = useState<MCPCatalogItem | null>(null);
  const [tokenInput, setTokenInput] = useState("");
  const [saving, setSaving] = useState(false);
  const [testResult, setTestResult] = useState<{ id: string; ok: boolean; message: string } | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getMCPServers();
      setServers(data.servers || []);
      setCatalog(data.catalog || []);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load MCP servers");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const handleToggle = async (id: string, currentState: boolean) => {
    try {
      await toggleMCPServer(id, !currentState);
      await refresh();
    } catch {
      // ignore
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await deleteMCPServer(id);
      await refresh();
    } catch {
      // ignore
    }
  };

  const handleTest = async (id: string) => {
    try {
      const res = await testMCPServer(id);
      setTestResult({
        id,
        ok: res.ok,
        message: res.ok ? (res.message || "Connection healthy ✓") : (res.error || "Connection failed"),
      });
      setTimeout(() => setTestResult(null), 5000);
    } catch (e: unknown) {
      setTestResult({
        id,
        ok: false,
        message: e instanceof Error ? e.message : "Test failed",
      });
    }
  };

  const handleSaveConnection = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!activeTemplate) return;

    setSaving(true);
    try {
      const envData: Record<string, string> = {};
      if (activeTemplate.env_keys && activeTemplate.env_keys.length > 0 && tokenInput.trim()) {
        envData[activeTemplate.env_keys[0]] = tokenInput.trim();
      }

      await configureMCPServer({
        id: activeTemplate.id,
        name: activeTemplate.name,
        description: activeTemplate.description,
        command: activeTemplate.command,
        args: activeTemplate.args,
        env: envData,
        enabled: true,
      });

      setActiveTemplate(null);
      setTokenInput("");
      await refresh();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to save configuration");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="mx-auto max-w-3xl space-y-6 pb-12">
      <PageHeader
        title="Plugins & MCP Integrations"
        mode="live"
        description="Connect SAM to your developer tools and workspace services via the Model Context Protocol (MCP). Extends SAM with GitHub, Google Workspace, Slack, filesystem, and custom tools."
      />

      {error && (
        <div className="rounded-md border border-danger/25 bg-danger/5 p-3 text-sm text-danger">
          {error}
        </div>
      )}

      {/* Active Integrations */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-ink flex items-center gap-2">
            <FiBox className="text-ember" />
            <span>Active Connections ({servers.length})</span>
          </h2>
          <Button variant="ghost" size="sm" onClick={refresh} loading={loading}>
            <FiRefreshCw size={13} />
          </Button>
        </div>

        {servers.length === 0 ? (
          <div className="rounded-lg border border-dashed border-line bg-surface p-6 text-center space-y-2">
            <p className="text-sm text-mute">No MCP integrations connected yet.</p>
            <p className="text-xs text-mute/80">
              Connect GitHub, Local Filesystem, or any custom MCP server below to give SAM direct access to your repos and tools.
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            {servers.map((s) => (
              <div
                key={s.id}
                className="flex items-start justify-between gap-4 rounded-lg border border-line bg-surface p-4"
              >
                <div className="flex items-start gap-3 min-w-0">
                  <div className="p-2 rounded bg-surface-raised border border-line shrink-0">
                    {getIcon(s.id)}
                  </div>
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-ink">{s.name}</span>
                      <StatusPill
                        state={s.enabled ? "SUCCESS" : "UNAVAILABLE"}
                        label={s.enabled ? "Active" : "Disabled"}
                        live
                      />
                    </div>
                    <p className="text-xs text-mute mt-0.5 line-clamp-1">{s.description}</p>
                    <div className="flex flex-wrap items-center gap-2 mt-2 text-[11px] text-mute font-mono-data">
                      <span>cmd: {s.command} {s.args.join(" ")}</span>
                      {Object.keys(s.masked_env || {}).map((k) => (
                        <span key={k} className="px-1.5 py-0.5 rounded bg-surface-raised border border-line text-ink">
                          {k}: {s.masked_env[k]}
                        </span>
                      ))}
                    </div>
                    {testResult && testResult.id === s.id && (
                      <p className={`text-xs mt-1.5 font-medium ${testResult.ok ? "text-emerald-500" : "text-danger"}`}>
                        {testResult.message}
                      </p>
                    )}
                  </div>
                </div>

                <div className="flex items-center gap-1.5 shrink-0">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => void handleTest(s.id)}
                    title="Test connection"
                  >
                    Test
                  </Button>
                  <button
                    type="button"
                    onClick={() => void handleToggle(s.id, s.enabled)}
                    className="p-1.5 text-mute hover:text-ink transition-colors"
                    title={s.enabled ? "Disable connection" : "Enable connection"}
                  >
                    {s.enabled ? (
                      <FiToggleRight size={22} className="text-ember" />
                    ) : (
                      <FiToggleLeft size={22} className="text-mute" />
                    )}
                  </button>
                  <button
                    type="button"
                    onClick={() => void handleDelete(s.id)}
                    className="p-1.5 text-mute hover:text-danger transition-colors"
                    title="Delete connection"
                  >
                    <FiTrash2 size={14} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Popular Providers Catalog */}
      <div className="space-y-3 pt-4 border-t border-line">
        <h2 className="text-sm font-semibold text-ink">Available Provider Plugins (MCP)</h2>
        <div className="grid gap-3 sm:grid-cols-2">
          {catalog.map((item) => {
            const isInstalled = servers.some((s) => s.id === item.id);
            return (
              <div
                key={item.id}
                className="flex flex-col justify-between rounded-lg border border-line bg-surface p-4 space-y-3"
              >
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2.5">
                      <div className="p-1.5 rounded bg-surface-raised border border-line">
                        {getIcon(item.id)}
                      </div>
                      <span className="text-sm font-semibold text-ink">{item.name}</span>
                    </div>
                    {isInstalled ? (
                      <span className="text-[11px] text-emerald-500 font-medium flex items-center gap-1">
                        <FiCheck size={12} /> Connected
                      </span>
                    ) : (
                      <span className="text-[10px] uppercase font-bold tracking-wider px-1.5 py-0.5 rounded bg-line/60 text-mute">
                        {item.category}
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-mute leading-relaxed">{item.description}</p>
                </div>

                <div className="flex items-center justify-between pt-2 border-t border-line/60">
                  {item.docs_url ? (
                    <a
                      href={item.docs_url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-[11px] text-mute hover:text-ink flex items-center gap-1 transition-colors"
                    >
                      <span>Docs</span>
                      <FiExternalLink size={10} />
                    </a>
                  ) : <span />}

                  <Button
                    variant={isInstalled ? "ghost" : "secondary"}
                    size="sm"
                    onClick={() => {
                      setActiveTemplate(item);
                      setTokenInput("");
                    }}
                  >
                    {isInstalled ? "Configure" : "Connect"}
                  </Button>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Connect / Configure Modal */}
      {activeTemplate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-void/70 backdrop-blur-sm p-4">
          <div className="w-full max-w-md rounded-lg border border-line bg-surface p-5 space-y-4 shadow-xl">
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-2.5">
                <div className="p-2 rounded bg-surface-raised border border-line">
                  {getIcon(activeTemplate.id)}
                </div>
                <div>
                  <h3 className="text-sm font-semibold text-ink">Connect {activeTemplate.name}</h3>
                  <p className="text-xs text-mute">Model Context Protocol Integration</p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setActiveTemplate(null)}
                className="text-mute hover:text-ink text-sm p-1"
              >
                ✕
              </button>
            </div>

            <p className="text-xs text-mute">{activeTemplate.description}</p>

            <form onSubmit={handleSaveConnection} className="space-y-3.5">
              {activeTemplate.auth_type !== "none" && (
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-ink flex items-center gap-1.5">
                    <FiKey size={12} className="text-mute" />
                    <span>{activeTemplate.token_label || "API Token / Key"}</span>
                  </label>
                  <input
                    type="password"
                    value={tokenInput}
                    onChange={(e) => setTokenInput(e.target.value)}
                    placeholder="Paste your token here..."
                    className="w-full rounded border border-line bg-surface-raised px-3 py-2 text-xs text-ink placeholder:text-mute/60 focus:border-ember focus:outline-none"
                    required={activeTemplate.auth_type === "token"}
                  />
                  {activeTemplate.docs_url && (
                    <p className="text-[11px] text-mute">
                      Get your token from{" "}
                      <a
                        href={activeTemplate.docs_url}
                        target="_blank"
                        rel="noreferrer"
                        className="text-ember hover:underline"
                      >
                        {activeTemplate.name} Settings
                      </a>
                    </p>
                  )}
                </div>
              )}

              <div className="rounded bg-surface-raised border border-line p-2.5 text-[11px] font-mono-data text-mute space-y-1">
                <p className="text-ink font-sans font-medium">Under the hood:</p>
                <p>Command: {activeTemplate.command} {activeTemplate.args.join(" ")}</p>
              </div>

              <div className="flex items-center justify-end gap-2 pt-2">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => setActiveTemplate(null)}
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  variant="primary"
                  size="sm"
                  loading={saving}
                >
                  Save & Enable
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
