import { useState, useEffect, useCallback } from "react";
import { FiCheck, FiX, FiPlus } from "react-icons/fi";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import {
  getFounderDecisions,
  getFounderTaste,
  getFounderPending,
  confirmFounderCapture,
  rejectFounderCapture,
  addFounderDecision,
  addFounderTaste,
  type FounderDecision,
  type FounderTasteItem,
  type FounderPendingCapture,
} from "@/api/client";

export function FounderModePage() {
  const [decisions, setDecisions] = useState<FounderDecision[]>([]);
  const [taste, setTaste] = useState<FounderTasteItem[]>([]);
  const [pending, setPending] = useState<FounderPendingCapture[]>([]);
  const [loading, setLoading] = useState(true);

  // Add custom rule state
  const [showAddModal, setShowAddModal] = useState(false);
  const [modalTab, setModalTab] = useState<"decision" | "taste">("taste");
  const [domainInput, setDomainInput] = useState("");
  const [prefInput, setPrefInput] = useState("");
  const [decisionInput, setDecisionInput] = useState("");
  const [reasonInput, setReasonInput] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [dRes, tRes, pRes] = await Promise.all([
        getFounderDecisions(50).catch(() => ({ decisions: [] })),
        getFounderTaste().catch(() => ({ taste: [] })),
        getFounderPending().catch(() => ({ pending: [] })),
      ]);
      setDecisions(dRes.decisions || []);
      setTaste(tRes.taste || []);
      setPending(pRes.pending || []);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const handleConfirm = async (p: FounderPendingCapture) => {
    try {
      await confirmFounderCapture(p.table, p.id);
      setPending((prev) => prev.filter((item) => item.id !== p.id));
      await refresh();
    } catch {
      // ignore
    }
  };

  const handleReject = async (p: FounderPendingCapture) => {
    try {
      await rejectFounderCapture(p.table, p.id);
      setPending((prev) => prev.filter((item) => item.id !== p.id));
    } catch {
      // ignore
    }
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      if (modalTab === "taste") {
        if (!domainInput.trim() || !prefInput.trim()) return;
        await addFounderTaste(domainInput.trim(), prefInput.trim());
      } else {
        if (!decisionInput.trim()) return;
        await addFounderDecision(decisionInput.trim(), reasonInput.trim());
      }
      setShowAddModal(false);
      setDomainInput("");
      setPrefInput("");
      setDecisionInput("");
      setReasonInput("");
      await refresh();
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="mx-auto max-w-2xl space-y-6 pb-12">
      <div className="flex items-start justify-between gap-3">
        <PageHeader
          title="Founder Mode"
          mode="live"
          description="SAM's persistent understanding of your architectural taste, guidelines, and feedback. Automatically shapes agent decisions across all sessions."
        />
        <Button variant="primary" size="sm" onClick={() => setShowAddModal(!showAddModal)}>
          <FiPlus size={14} /> Add Taste / Rule
        </Button>
      </div>

      {showAddModal && (
        <Card className="space-y-4 border-ember/40 bg-surface">
          <div className="flex items-center justify-between border-b border-line pb-2">
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={() => setModalTab("taste")}
                className={`text-xs font-medium pb-1 border-b-2 transition-colors ${
                  modalTab === "taste" ? "border-ember text-ink" : "border-transparent text-mute hover:text-ink"
                }`}
              >
                Taste Preference
              </button>
              <button
                type="button"
                onClick={() => setModalTab("decision")}
                className={`text-xs font-medium pb-1 border-b-2 transition-colors ${
                  modalTab === "decision" ? "border-ember text-ink" : "border-transparent text-mute hover:text-ink"
                }`}
              >
                Key Decision / Rule
              </button>
            </div>
            <button
              type="button"
              onClick={() => setShowAddModal(false)}
              className="text-xs text-mute hover:text-ink"
            >
              ✕
            </button>
          </div>

          <form onSubmit={handleCreate} className="space-y-3">
            {modalTab === "taste" ? (
              <>
                <div>
                  <label className="block text-xs font-medium text-ink mb-1">Domain / Category</label>
                  <input
                    type="text"
                    placeholder="e.g. backend_framework, code_style, ui_library"
                    value={domainInput}
                    onChange={(e) => setDomainInput(e.target.value)}
                    className="w-full rounded border border-line bg-surface-raised px-3 py-1.5 text-xs text-ink focus:border-ember focus:outline-none"
                    required
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-ink mb-1">Preference / Rule</label>
                  <input
                    type="text"
                    placeholder="e.g. Always prefer FastAPI and Tailwind CSS; keep components minimal"
                    value={prefInput}
                    onChange={(e) => setPrefInput(e.target.value)}
                    className="w-full rounded border border-line bg-surface-raised px-3 py-1.5 text-xs text-ink focus:border-ember focus:outline-none"
                    required
                  />
                </div>
              </>
            ) : (
              <>
                <div>
                  <label className="block text-xs font-medium text-ink mb-1">Decision</label>
                  <input
                    type="text"
                    placeholder="e.g. Never run destructive database migrations without confirmation"
                    value={decisionInput}
                    onChange={(e) => setDecisionInput(e.target.value)}
                    className="w-full rounded border border-line bg-surface-raised px-3 py-1.5 text-xs text-ink focus:border-ember focus:outline-none"
                    required
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-ink mb-1">Reasoning / Justification</label>
                  <textarea
                    placeholder="Why this decision was made..."
                    value={reasonInput}
                    onChange={(e) => setReasonInput(e.target.value)}
                    rows={2}
                    className="w-full rounded border border-line bg-surface-raised px-3 py-1.5 text-xs text-ink focus:border-ember focus:outline-none"
                  />
                </div>
              </>
            )}

            <div className="flex items-center justify-end gap-2 pt-1">
              <Button type="button" variant="ghost" size="sm" onClick={() => setShowAddModal(false)}>
                Cancel
              </Button>
              <Button type="submit" variant="primary" size="sm" loading={submitting}>
                Save to Founder Mode
              </Button>
            </div>
          </form>
        </Card>
      )}

      {/* Pending Reviews */}
      {pending.length > 0 && (
        <div className="space-y-2">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-mute">Pending Reviews ({pending.length})</h2>
          <div className="space-y-2">
            {pending.map((p) => (
              <div
                key={p.id}
                className="flex items-center justify-between gap-3 rounded-md border border-line bg-surface px-3 py-2.5"
              >
                <div className="min-w-0">
                  <p className="text-xs text-ink">{p.content}</p>
                  <p className="font-mono-data text-[10px] text-mute">{p.table} · {p.reasoning || "auto-detected"}</p>
                </div>
                <div className="flex shrink-0 gap-1.5">
                  <Button variant="ghost" size="sm" onClick={() => void handleConfirm(p)} title="Confirm">
                    <FiCheck size={14} className="text-success" />
                  </Button>
                  <Button variant="ghost" size="sm" onClick={() => void handleReject(p)} title="Reject">
                    <FiX size={14} className="text-danger" />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Taste Profile */}
      <div className="space-y-2">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-mute">Taste Profile ({taste.length})</h2>
        {loading ? (
          <div className="py-4 text-center text-xs text-mute">Loading taste profile...</div>
        ) : taste.length === 0 ? (
          <div className="rounded border border-dashed border-line p-4 text-center text-xs text-mute">
            No taste preferences recorded yet. Add your preferred stack and conventions above.
          </div>
        ) : (
          <div className="grid gap-2">
            {taste.map((t, i) => (
              <div
                key={i}
                className="flex items-center justify-between rounded-md border border-line bg-surface px-3 py-2.5 text-xs"
              >
                <div className="space-y-0.5">
                  <span className="font-medium text-ink">{t.preference}</span>
                  <p className="text-[10px] text-mute font-mono-data">domain: {t.domain}</p>
                </div>
                <span className="rounded bg-surface-raised px-2 py-0.5 text-[10px] font-mono-data text-emerald-400">
                  {t.strength || "verified"}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Decisions & Task Reflections */}
      <div className="space-y-2">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-mute">
          Decisions & Task Reflections ({decisions.length})
        </h2>
        {loading ? (
          <div className="py-4 text-center text-xs text-mute">Loading decisions...</div>
        ) : decisions.length === 0 ? (
          <div className="rounded border border-dashed border-line p-4 text-center text-xs text-mute">
            No decisions logged yet. As SAM runs tasks, lessons learned are automatically saved here.
          </div>
        ) : (
          <div className="space-y-2">
            {decisions.slice(0, 20).map((d, i) => (
              <div key={i} className="rounded-md border border-line bg-surface p-3 text-xs space-y-1">
                <div className="flex items-start justify-between gap-2">
                  <p className="font-medium text-ink">{d.decision}</p>
                  <span className="shrink-0 rounded bg-surface-raised px-1.5 py-0.5 text-[10px] font-mono-data text-mute">
                    {d.category}
                  </span>
                </div>
                {d.reasoning && <p className="text-mute text-[11px]">{d.reasoning}</p>}
                <p className="font-mono-data text-[10px] text-mute/80 pt-0.5">
                  confidence {(d.confidence * 100).toFixed(0)}%
                </p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
