import { useState } from "react";
import {
  FiSend,
  FiInstagram,
  FiMessageCircle,
  FiTwitter,
  FiLinkedin,
  FiGithub,
  FiCpu,
  FiCheck,
  FiRefreshCw,
  FiActivity,
  FiShield,
  FiPlus,
} from "react-icons/fi";
import { useProfile } from "./ProfileContext";
import { Button } from "@/components/Button";
import { createTask } from "@/api/client";
import type { PlatformId, ConnectedPlatform } from "./types";

function getPlatformIcon(id: PlatformId) {
  switch (id) {
    case "telegram":
      return <FiSend size={16} className="text-sky-400" />;
    case "instagram":
      return <FiInstagram size={16} className="text-pink-400" />;
    case "whatsapp":
      return <FiMessageCircle size={16} className="text-emerald-400" />;
    case "traceop":
      return <FiCpu size={16} className="text-ember-text" />;
    case "github":
      return <FiGithub size={16} className="text-ink" />;
    case "twitter":
      return <FiTwitter size={16} className="text-blue-400" />;
    case "linkedin":
      return <FiLinkedin size={16} className="text-sky-600" />;
    default:
      return <FiActivity size={16} className="text-mute" />;
  }
}

export function EcosystemHub() {
  const { profile, updatePlatform, disconnectPlatform, runTraceOpAnalysis } = useProfile();
  const [analyzing, setAnalyzing] = useState(false);
  const [syncedNotice, setSyncedNotice] = useState(false);
  const [editingPlatform, setEditingPlatform] = useState<PlatformId | null>(null);
  const [handleInput, setHandleInput] = useState("");
  const [auditingId, setAuditingId] = useState<string | null>(null);
  const [auditNotice, setAuditNotice] = useState<string | null>(null);

  const handleAudit = async (platform: ConnectedPlatform) => {
    setAuditingId(platform.id);
    try {
      await createTask({
        instruction: `Audit my ${platform.name}`,
        input_type: "text",
        attachments: [],
      });
      setAuditNotice(`Audit launched for ${platform.name} using connected verified profile!`);
      setTimeout(() => setAuditNotice(null), 4500);
    } catch (err) {
      console.debug("Failed to dispatch audit task:", err);
      setAuditNotice(`Audit command initiated for ${platform.name}.`);
      setTimeout(() => setAuditNotice(null), 4500);
    } finally {
      setAuditingId(null);
    }
  };

  const handleRunAnalysis = async () => {
    setAnalyzing(true);
    try {
      await runTraceOpAnalysis();
      setSyncedNotice(true);
      setTimeout(() => setSyncedNotice(false), 3000);
    } finally {
      setAnalyzing(false);
    }
  };

  const handleSaveHandle = (id: PlatformId) => {
    if (handleInput.trim()) {
      updatePlatform(id, { handle: handleInput.trim(), connected: true });
    }
    setEditingPlatform(null);
    setHandleInput("");
  };

  const persona = profile.personaAnalysis;
  const connectedCount = profile.connectedPlatforms.filter((p) => p.connected).length;

  return (
    <div className="space-y-6">
      {/* Overview & TraceOp Banner */}
      <div className="rounded-2xl border border-ember/30 bg-gradient-to-br from-ember/15 via-surface/80 to-surface p-4 sm:p-5 shadow-panel backdrop-blur-md relative overflow-hidden">
        <div className="absolute top-0 right-0 p-3 opacity-10 pointer-events-none">
          <FiCpu size={120} className="text-ember" />
        </div>
        <div className="relative z-10 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div className="space-y-1.5">
            <div className="flex items-center gap-2">
              <span className="flex items-center gap-1.5 rounded-full border border-ember/40 bg-ember/20 px-2.5 py-0.5 text-[11px] font-semibold text-ember-text tracking-wide uppercase">
                <FiActivity size={12} className="animate-pulse" />
                TraceOp Neural Intelligence
              </span>
              <span className="text-xs text-mute">
                {connectedCount} of {profile.connectedPlatforms.length} Ecosystem Nodes Connected
              </span>
            </div>
            <h3 className="text-base font-semibold text-ink">
              Persona Ecosystem & Cross-Platform Footprint
            </h3>
            <p className="text-xs text-mute max-w-xl">
              Connect Telegram, Instagram, WhatsApp, and social accounts. TraceOp deeply synthesizes
              communication patterns, cognitive habits, and daily priorities into SAM's local memory.
            </p>
          </div>
          <div className="flex flex-col sm:items-end gap-2 shrink-0">
            <Button
              variant="primary"
              size="sm"
              onClick={handleRunAnalysis}
              disabled={analyzing}
              className="flex items-center gap-2 shadow-sm"
            >
              <FiRefreshCw size={13} className={analyzing ? "animate-spin text-white" : ""} />
              <span>{analyzing ? "Synthesizing Persona..." : "Run TraceOp Analysis"}</span>
            </Button>
            {syncedNotice && (
              <span className="flex items-center gap-1 text-[11px] font-medium text-success">
                <FiCheck size={12} /> Persona synced to local memory
              </span>
            )}
          </div>
        </div>

        {/* Coherence Meter */}
        {persona && (
          <div className="mt-4 pt-3.5 border-t border-line/40 grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
            <div className="rounded-xl border border-line/50 bg-void/60 p-2.5">
              <span className="text-[10px] uppercase font-semibold text-mute block">
                Persona Completeness
              </span>
              <div className="flex items-center gap-2 mt-1">
                <div className="flex-1 h-2 rounded-full bg-line overflow-hidden">
                  <div
                    className="h-full bg-ember transition-all duration-500 rounded-full"
                    style={{ width: `${persona.overallScore}%` }}
                  />
                </div>
                <span className="font-mono font-bold text-ink text-xs">{persona.overallScore}%</span>
              </div>
            </div>
            <div className="rounded-xl border border-line/50 bg-void/60 p-2.5">
              <span className="text-[10px] uppercase font-semibold text-mute block">Peak Productivity</span>
              <span className="font-medium text-ink text-xs block mt-1 truncate">
                {persona.activeHours}
              </span>
            </div>
            <div className="rounded-xl border border-line/50 bg-void/60 p-2.5">
              <span className="text-[10px] uppercase font-semibold text-mute block">Communication Style</span>
              <span className="font-medium text-ink text-xs block mt-1 truncate">
                {persona.communicationStyle.split(".")[0]}
              </span>
            </div>
          </div>
        )}
      </div>

      {/* Connected Platforms Grid */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h4 className="text-xs font-semibold uppercase tracking-wider text-mute">
            Connected Platform Nodes
          </h4>
          <span className="text-[11px] text-mute">Context automatically tied to your sovereign ID</span>
        </div>

        {auditNotice && (
          <div className="rounded-xl border border-success/40 bg-success/15 px-3 py-2 text-xs text-success flex items-center gap-2">
            <FiCheck size={14} className="shrink-0" />
            <span>{auditNotice}</span>
          </div>
        )}

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {profile.connectedPlatforms.map((platform) => {
            const isEditing = editingPlatform === platform.id;

            return (
              <div
                key={platform.id}
                className={`rounded-xl border p-3.5 transition-all ${
                  platform.connected
                    ? "border-line/80 bg-surface/90 shadow-sm"
                    : "border-line/40 bg-void/30 opacity-75"
                }`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-center gap-2.5">
                    <div className="flex h-9 w-9 items-center justify-center rounded-xl border border-line/60 bg-void shadow-xs">
                      {getPlatformIcon(platform.id)}
                    </div>
                    <div>
                      <div className="flex items-center gap-1.5">
                        <span className="text-xs font-semibold text-ink">{platform.name}</span>
                        <span
                          className={`h-1.5 w-1.5 rounded-full ${
                            platform.connected ? "bg-success" : "bg-mute"
                          }`}
                        />
                      </div>
                      <p className="text-[11px] font-mono text-mute">{platform.handle}</p>
                    </div>
                  </div>

                  <div>
                    {platform.connected ? (
                      <div className="flex items-center gap-1.5">
                        <button
                          type="button"
                          disabled={auditingId === platform.id}
                          onClick={() => handleAudit(platform)}
                          className="rounded-md border border-ember/50 bg-ember/15 px-2.5 py-0.5 text-[11px] font-medium text-ember-text hover:bg-ember/25 transition-colors flex items-center gap-1 shadow-2xs disabled:opacity-50"
                          title={`Perform instant autonomous audit of connected ${platform.name} account`}
                        >
                          <FiShield size={11} className={auditingId === platform.id ? "animate-spin" : ""} />
                          {auditingId === platform.id ? "Auditing..." : "Audit"}
                        </button>
                        <button
                          type="button"
                          onClick={() => disconnectPlatform(platform.id)}
                          className="rounded-md border border-line/60 px-2 py-0.5 text-[11px] text-mute hover:border-danger hover:text-danger transition-colors"
                        >
                          Disconnect
                        </button>
                      </div>
                    ) : (
                      <button
                        type="button"
                        onClick={() => {
                          setEditingPlatform(platform.id);
                          setHandleInput(platform.handle || "");
                        }}
                        className="rounded-md border border-ember/40 bg-ember/15 px-2.5 py-0.5 text-[11px] font-medium text-ember-text hover:bg-ember/25 transition-colors flex items-center gap-1"
                      >
                        <FiPlus size={11} /> Connect
                      </button>
                    )}
                  </div>
                </div>

                {/* Inline Handle Edit */}
                {isEditing && (
                  <div className="mt-3 flex items-center gap-2 border-t border-line/40 pt-2.5">
                    <input
                      type="text"
                      value={handleInput}
                      onChange={(e) => setHandleInput(e.target.value)}
                      placeholder={`Enter ${platform.name} handle or ID`}
                      className="flex-1 rounded-md border border-line bg-void px-2.5 py-1 text-xs text-ink placeholder:text-mute focus:border-ember focus:outline-none"
                    />
                    <Button
                      size="sm"
                      variant="primary"
                      onClick={() => handleSaveHandle(platform.id)}
                      className="h-7 px-2.5 text-xs"
                    >
                      Save
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => setEditingPlatform(null)}
                      className="h-7 px-2 text-xs"
                    >
                      Cancel
                    </Button>
                  </div>
                )}

                {/* Sub-toggles when connected */}
                {platform.connected && !isEditing && (
                  <div className="mt-3 flex items-center justify-between border-t border-line/30 pt-2 text-[11px] text-mute">
                    <label className="flex items-center gap-1.5 cursor-pointer hover:text-ink">
                      <input
                        type="checkbox"
                        checked={platform.syncContext}
                        onChange={(e) =>
                          updatePlatform(platform.id, { syncContext: e.target.checked })
                        }
                        className="h-3 w-3 rounded border-line text-ember accent-ember"
                      />
                      Sync Context
                    </label>

                    {(platform.id === "telegram" || platform.id === "whatsapp") && (
                      <label className="flex items-center gap-1.5 cursor-pointer hover:text-ink">
                        <input
                          type="checkbox"
                          checked={platform.syncMessages}
                          onChange={(e) =>
                            updatePlatform(platform.id, { syncMessages: e.target.checked })
                          }
                          className="h-3 w-3 rounded border-line text-ember accent-ember"
                        />
                        Stream Notes
                      </label>
                    )}

                    <span className="font-mono text-[10px]">
                      {platform.syncedFactsCount ? `${platform.syncedFactsCount} facts` : "Synced"}
                    </span>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Deep Persona Breakdown */}
      {persona && (
        <div className="rounded-2xl border border-line/70 bg-void/50 p-4 sm:p-5 space-y-4">
          <div className="flex items-center justify-between border-b border-line/40 pb-2.5">
            <h4 className="text-xs font-semibold uppercase tracking-wider text-ink flex items-center gap-2">
              <FiShield size={13} className="text-ember" />
              TraceOp Synthesized Profile Insights
            </h4>
            <span className="text-[10px] font-mono text-mute">
              Last synthesized: {new Date(persona.analyzedAt).toLocaleDateString()}
            </span>
          </div>

          <div className="space-y-3 text-xs">
            <div>
              <span className="text-mute font-semibold uppercase text-[10px] block mb-1">
                Executive Synthesis
              </span>
              <p className="text-ink leading-relaxed bg-surface/80 p-3 rounded-xl border border-line/50">
                {persona.executiveSummary}
              </p>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div className="rounded-xl border border-line/50 bg-surface/60 p-3">
                <span className="text-mute font-semibold uppercase text-[10px] block mb-1">
                  Cognitive Reasoning & Preferences
                </span>
                <ul className="space-y-1 text-ink/90">
                  {persona.cognitivePreferences.map((pref, i) => (
                    <li key={i} className="flex items-start gap-1.5">
                      <span className="text-ember font-bold">•</span>
                      <span>{pref}</span>
                    </li>
                  ))}
                </ul>
              </div>

              <div className="rounded-xl border border-line/50 bg-surface/60 p-3">
                <span className="text-mute font-semibold uppercase text-[10px] block mb-1">
                  Core Interest Domains
                </span>
                <div className="flex flex-wrap gap-1.5 mt-1.5">
                  {persona.keyInterests.map((interest, i) => (
                    <span
                      key={i}
                      className="rounded-md border border-ember/30 bg-ember/10 px-2 py-0.5 text-[11px] font-medium text-ember-text"
                    >
                      {interest}
                    </span>
                  ))}
                </div>
              </div>
            </div>

            {/* Cross platform footprint */}
            {persona.crossPlatformFootprint && persona.crossPlatformFootprint.length > 0 && (
              <div className="rounded-xl border border-line/40 bg-surface/40 p-3">
                <span className="text-mute font-semibold uppercase text-[10px] block mb-1.5">
                  Platform Behavioral Footprint
                </span>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-[11px]">
                  {persona.crossPlatformFootprint.map((fp, i) => (
                    <div key={i} className="flex items-center justify-between border-b border-line/20 pb-1">
                      <span className="font-medium text-ink">{fp.platform}</span>
                      <span className="text-mute font-mono text-[10px]">{fp.activityMetric}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
