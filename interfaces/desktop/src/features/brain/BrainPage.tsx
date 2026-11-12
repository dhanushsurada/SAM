import { useState, useEffect, useCallback } from "react";
import { FiRefreshCw, FiZap, FiKey, FiTrash2, FiExternalLink, FiCpu } from "react-icons/fi";
import { Button } from "@/components/Button";
import { PageHeader } from "@/components/PageHeader";
import { StatusPill } from "@/components/StatusPill";
import type { BrainStatus, ModelInfo } from "@/api/types";
import {
  getCloudProviders,
  saveProviderKey,
  deleteProviderKey,
  getModelUpdates,
  type CloudProvider,
  type ModelNotification,
} from "@/api/client";
import { useBrain } from "./useBrain";
import { activeSourceLabel, describeOverrides, modelMeta, switchBlockedReason } from "./format";

function Chip({ children, tone }: { children: string; tone: "ember" | "plain" | "emerald" }) {
  let style = "border-line text-mute";
  if (tone === "ember") style = "border-ember/40 bg-ember/10 text-ember-text";
  if (tone === "emerald") style = "border-emerald-500/40 bg-emerald-500/10 text-emerald-400";

  return (
    <span className={`rounded-full border px-2 py-0.5 text-[11px] font-medium ${style}`}>
      {children}
    </span>
  );
}

function Summary({ status, onRefresh, loading }: { status: BrainStatus; onRefresh: () => void; loading: boolean }) {
  const ready = status.status === "ready";
  const source = activeSourceLabel(status);
  const pinned = describeOverrides(status.overrides);

  return (
    <div className="space-y-3 rounded-lg border border-line bg-surface p-4 shadow-panel">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs text-mute">Active Brain</p>
          <p className="truncate font-mono-data text-base text-ink">{status.active_model ?? "None"}</p>
          {source && <p className="text-xs text-mute">{source}</p>}
        </div>
        <div className="flex items-center gap-1">
          <StatusPill state={ready ? "SUCCESS" : "UNAVAILABLE"} label={ready ? "Ready" : "Unavailable"} live />
          <Button variant="ghost" size="sm" onClick={onRefresh} loading={loading} aria-label="Refresh Brain status">
            <FiRefreshCw size={14} />
          </Button>
        </div>
      </div>

      {status.detail && (
        <p
          className={`rounded-md border px-3 py-2 text-xs ${
            ready ? "border-warn/25 bg-warn/5 text-warn" : "border-danger/25 bg-danger/5 text-danger"
          }`}
        >
          {status.detail}
        </p>
      )}

      <dl className="grid gap-x-6 gap-y-1.5 text-xs sm:grid-cols-2">
        <div className="flex justify-between gap-3">
          <dt className="text-mute">Provider</dt>
          <dd className="text-ink">{status.provider === "ollama" ? "Ollama" : status.provider}</dd>
        </div>
        <div className="flex justify-between gap-3">
          <dt className="text-mute">Endpoint</dt>
          <dd className="truncate font-mono-data text-ink">{status.ollama_host}</dd>
        </div>
        <div className="flex justify-between gap-3">
          <dt className="text-mute">Selected</dt>
          <dd className="truncate font-mono-data text-ink">{status.selected_model}</dd>
        </div>
        <div className="flex justify-between gap-3">
          <dt className="text-mute">Fallback</dt>
          <dd className="truncate font-mono-data text-ink">{status.fallback_model}</dd>
        </div>
        <div className="flex justify-between gap-3 sm:col-span-2">
          <dt className="text-mute">Last used by SAM</dt>
          <dd className="truncate font-mono-data text-ink">{status.last_used_model ?? "nothing yet since start-up"}</dd>
        </div>
      </dl>

      {pinned.length > 0 && (
        <p className="text-xs text-mute">
          Pinned separately, so these keep their own model when you switch: {pinned.join("; ")}.
        </p>
      )}
    </div>
  );
}

function ModelRow({
  status,
  model,
  selecting,
  onSelect,
}: {
  status: BrainStatus;
  model: ModelInfo;
  selecting: string | null;
  onSelect: (name: string) => void;
}) {
  const blocked = switchBlockedReason(status, model);
  const meta = modelMeta(model);
  const incompatible = model.compatibility === "incompatible";

  return (
    <li
      className={`space-y-2 rounded-md border px-3 py-2.5 ${
        model.is_selected ? "border-ember/30 bg-ember/5" : "border-line bg-surface"
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 space-y-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <p className="font-mono-data text-sm text-ink">{model.name}</p>
            {model.is_active && <Chip tone="ember">Active</Chip>}
            {model.is_selected && <Chip tone="plain">Selected</Chip>}
            {model.is_fallback && <Chip tone="plain">Fallback</Chip>}
          </div>
          {meta.length > 0 && (
            <p className="flex flex-wrap gap-x-3 font-mono-data text-xs text-mute">
              {meta.map((part) => (
                <span key={part}>{part}</span>
              ))}
            </p>
          )}
        </div>

        {model.is_selected ? (
          <span className="shrink-0 pt-1 text-xs text-mute">In use</span>
        ) : (
          <Button
            variant="secondary"
            size="sm"
            onClick={() => onSelect(model.name)}
            disabled={blocked !== null || selecting !== null}
            loading={selecting === model.name}
            aria-label={`Use ${model.name} as the Brain`}
          >
            Use as Brain
          </Button>
        )}
      </div>

      {model.capabilities && model.capabilities.length > 0 && (
        <p className="flex flex-wrap gap-1.5">
          {model.capabilities.map((c) => (
            <span key={c} className="rounded border border-line px-1.5 py-0.5 font-mono-data text-[10px] text-mute">
              {c}
            </span>
          ))}
        </p>
      )}

      <p className={`text-xs ${incompatible ? "text-danger" : "text-unverified"}`}>
        {incompatible ? "Incompatible" : "Compatibility unknown"}: {model.compatibility_reason}
      </p>
      {model.notes.map((note) => (
        <p key={note} className="text-xs text-warn">
          {note}
        </p>
      ))}
      {!model.is_selected && blocked !== null && !incompatible && <p className="text-xs text-mute">{blocked}</p>}
    </li>
  );
}

export function BrainPage() {
  const { status, loading, error, selecting, selectError, switchedTo, refresh, select } = useBrain();

  const [providers, setProviders] = useState<CloudProvider[]>([]);
  const [notifications, setNotifications] = useState<ModelNotification[]>([]);
  const [keyInputs, setKeyInputs] = useState<Record<string, string>>({});
  const [savingKey, setSavingKey] = useState<string | null>(null);
  const [saveMessage, setSaveMessage] = useState<Record<string, string>>({});

  const loadProvidersAndUpdates = useCallback(async () => {
    try {
      const [provRes, notifRes] = await Promise.all([
        getCloudProviders(),
        getModelUpdates(),
      ]);
      setProviders(provRes.providers || []);
      setNotifications(notifRes.notifications || []);
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    void loadProvidersAndUpdates();
  }, [loadProvidersAndUpdates]);

  const handleSaveKey = async (providerId: string) => {
    const key = (keyInputs[providerId] || "").trim();
    if (!key) return;
    setSavingKey(providerId);
    try {
      await saveProviderKey(providerId, key);
      setKeyInputs((prev) => ({ ...prev, [providerId]: "" }));
      setSaveMessage((prev) => ({ ...prev, [providerId]: "Key saved securely ✓" }));
      await loadProvidersAndUpdates();
      await refresh();
      setTimeout(() => {
        setSaveMessage((prev) => {
          const next = { ...prev };
          delete next[providerId];
          return next;
        });
      }, 3000);
    } catch (e: unknown) {
      setSaveMessage((prev) => ({ ...prev, [providerId]: e instanceof Error ? e.message : "Save failed" }));
    } finally {
      setSavingKey(null);
    }
  };

  const handleDeleteKey = async (providerId: string) => {
    try {
      await deleteProviderKey(providerId);
      await loadProvidersAndUpdates();
      await refresh();
    } catch {
      // ignore
    }
  };

  return (
    <div className="mx-auto max-w-2xl space-y-5 pb-10">
      <PageHeader
        title="Brain"
        mode="live"
        description="Choose how SAM thinks. Run sovereignly offline using local Ollama models, or supercharge speed with ultra-fast Cloud LLMs (Groq, Gemini, OpenAI)."
      />

      {/* Model Tech Updates & Upgrade Recommendations */}
      {notifications.length > 0 && (
        <div className="space-y-2">
          <h2 className="text-sm font-medium text-mute flex items-center gap-1.5">
            <FiZap className="text-amber-400" />
            <span>Latest Tech & Model Updates</span>
          </h2>
          <div className="grid gap-2">
            {notifications.map((n) => (
              <div
                key={n.id}
                className="flex items-start justify-between gap-3 p-3 rounded-lg border border-line bg-surface/80"
              >
                <div className="min-w-0 space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-semibold text-ink">{n.title}</span>
                    <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-ember/20 text-ember border border-ember/30">
                      {n.badge}
                    </span>
                  </div>
                  <p className="text-xs text-mute">{n.description}</p>
                </div>
                {n.action_url ? (
                  <a
                    href={n.action_url}
                    target="_blank"
                    rel="noreferrer"
                    className="shrink-0 flex items-center gap-1 px-2.5 py-1 text-xs font-medium rounded border border-line bg-surface hover:text-ink text-mute transition-colors"
                  >
                    <span>Get Key</span>
                    <FiExternalLink size={11} />
                  </a>
                ) : n.configured ? (
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => select(`${n.provider}:${n.model}`)}
                    disabled={selecting !== null}
                    loading={selecting === `${n.provider}:${n.model}`}
                  >
                    Use Model
                  </Button>
                ) : null}
              </div>
            ))}
          </div>
        </div>
      )}

      {error && (
        <div className="space-y-2 rounded-md border border-danger/25 bg-danger/5 px-3 py-2.5">
          <p className="text-sm text-danger">{error}</p>
          <Button variant="secondary" size="sm" onClick={refresh} loading={loading}>
            Try again
          </Button>
        </div>
      )}

      {!status && !error && <p className="text-sm text-mute">Loading…</p>}

      {status && (
        <>
          <Summary status={status} onRefresh={refresh} loading={loading} />

          {switchedTo && (
            <p role="status" className="text-xs text-success">
              Brain switched to {switchedTo}. The next task will use it.
            </p>
          )}
          {selectError && (
            <p role="alert" className="rounded-md border border-danger/25 bg-danger/5 px-3 py-2 text-xs text-danger">
              {selectError}
            </p>
          )}

          {/* Cloud LLM Providers Section */}
          <div className="space-y-3">
            <div>
              <h2 className="text-sm font-medium text-mute flex items-center gap-1.5">
                <FiZap className="text-ember" />
                <span>Cloud LLMs — Ultra-Fast Reasoning (~200ms)</span>
              </h2>
              <p className="text-xs text-mute">
                Add an API key to enable instant responses and skip local GPU/RAM inference wait times.
              </p>
            </div>

            <div className="space-y-3">
              {providers.map((p) => {
                const isConfigured = p.configured;
                const inputValue = keyInputs[p.id] || "";
                const msg = saveMessage[p.id];

                return (
                  <div
                    key={p.id}
                    className="rounded-lg border border-line bg-surface p-3.5 space-y-3"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="flex items-center gap-2">
                          <h3 className="text-sm font-medium text-ink">{p.name}</h3>
                          {isConfigured ? (
                            <Chip tone="emerald">Key Saved</Chip>
                          ) : (
                            <Chip tone="plain">No Key</Chip>
                          )}
                        </div>
                        <p className="text-xs text-mute mt-0.5">{p.description}</p>
                      </div>

                      {isConfigured && (
                        <button
                          type="button"
                          onClick={() => void handleDeleteKey(p.id)}
                          className="text-mute hover:text-danger p-1 text-xs flex items-center gap-1 transition-colors"
                          title="Remove saved API key"
                        >
                          <FiTrash2 size={13} />
                          <span>Remove</span>
                        </button>
                      )}
                    </div>

                    {/* Key input row */}
                    <div className="flex items-center gap-2">
                      <div className="relative flex-1">
                        <FiKey className="absolute left-2.5 top-1/2 -translate-y-1/2 text-mute" size={13} />
                        <input
                          type="password"
                          value={inputValue}
                          onChange={(e) =>
                            setKeyInputs((prev) => ({ ...prev, [p.id]: e.target.value }))
                          }
                          placeholder={isConfigured ? `Configured (${p.masked_key}) — enter new to replace` : `Enter ${p.name} API key`}
                          className="w-full pl-8 pr-3 py-1.5 bg-surface-raised border border-line rounded text-xs text-ink placeholder:text-mute/60 focus:outline-none focus:border-ember"
                          onKeyDown={(e) => {
                            if (e.key === "Enter") {
                              e.preventDefault();
                              void handleSaveKey(p.id);
                            }
                          }}
                        />
                      </div>
                      <Button
                        variant="secondary"
                        size="sm"
                        disabled={!inputValue.trim() || savingKey === p.id}
                        loading={savingKey === p.id}
                        onClick={() => void handleSaveKey(p.id)}
                      >
                        Save
                      </Button>
                    </div>

                    {msg && (
                      <p className={`text-xs ${msg.includes("✓") ? "text-emerald-500" : "text-danger"}`}>
                        {msg}
                      </p>
                    )}

                    {/* Available Models under this provider */}
                    {isConfigured && p.models && p.models.length > 0 && (
                      <div className="pt-2 border-t border-line/60 space-y-1.5">
                        <p className="text-[11px] font-medium text-mute">Available models:</p>
                        <div className="grid gap-1.5 sm:grid-cols-2">
                          {p.models.map((m) => {
                            const fullModelId = `${p.id}:${m.id}`;
                            const isCurrent = status.selected_model === fullModelId || (status.provider === p.id && status.active_model === m.id);

                            return (
                              <div
                                key={m.id}
                                className={`flex items-center justify-between p-2 rounded border text-xs ${
                                  isCurrent
                                    ? "border-ember/40 bg-ember/10 text-ember-text"
                                    : "border-line bg-surface-raised text-ink"
                                }`}
                              >
                                <div className="min-w-0 pr-2">
                                  <p className="truncate font-mono-data text-xs">{m.name}</p>
                                  <p className="text-[10px] text-mute">{m.fast ? "⚡ Ultra-Fast" : "Frontier Reasoning"}</p>
                                </div>
                                {isCurrent ? (
                                  <span className="text-[11px] text-ember font-medium shrink-0">Selected</span>
                                ) : (
                                  <Button
                                    variant="ghost"
                                    size="sm"
                                    onClick={() => void select(fullModelId)}
                                    disabled={selecting !== null}
                                    loading={selecting === fullModelId}
                                  >
                                    Use
                                  </Button>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          {/* Local Ollama Models Section */}
          <div className="space-y-2 pt-2 border-t border-line">
            <h2 className="text-sm font-medium text-mute flex items-center gap-1.5">
              <FiCpu className="text-mute" />
              <span>Installed Local Ollama Models ({status.models.length})</span>
            </h2>
            {status.models.length === 0 ? (
              <p className="rounded-lg border border-dashed border-line px-4 py-6 text-center text-sm text-mute">
                {status.status === "unavailable"
                  ? "Nothing to choose from yet. Start Ollama and install a model, then refresh."
                  : "No models installed."}
              </p>
            ) : (
              <ul className="space-y-2">
                {status.models.map((m) => (
                  <ModelRow key={m.name} status={status} model={m} selecting={selecting} onSelect={select} />
                ))}
              </ul>
            )}
          </div>

          <p className="text-xs text-mute">
            SAM can't verify how well a model follows its action format, so compatibility is shown as unknown unless
            a model is provably unusable. This changes the Brain the gateway uses. Other SAM processes (the voice or
            text session, the Telegram bridge) keep the model they started with until they restart.
          </p>
        </>
      )}
    </div>
  );
}
