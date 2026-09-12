import { useState } from "react";
import { FiCheck, FiX } from "react-icons/fi";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/Button";
import { DEMO_DECISIONS, DEMO_TASTE, DEMO_PENDING } from "./demoData";
import type { PendingCapture } from "./types";

export function FounderModePage() {
  const [pending, setPending] = useState<PendingCapture[]>(DEMO_PENDING);

  const resolve = (id: string) => setPending((prev) => prev.filter((p) => p.id !== id));

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <PageHeader
        title="Founder Mode"
        mode="demo"
        description="SAM's persistent understanding of you — decisions, reflections, taste. FounderModeManager exists, nothing exposes it over HTTP yet."
      />

      <div>
        <h2 className="mb-2 text-sm font-medium text-mute">Pending review</h2>
        {pending.length === 0 && <p className="text-xs text-mute">Nothing waiting — try reloading the page.</p>}
        <div className="space-y-2">
          {pending.map((p) => (
            <div key={p.id} className="flex items-center justify-between gap-3 rounded-md border border-line bg-surface px-3 py-2.5">
              <div className="min-w-0">
                <p className="truncate text-sm text-ink">{p.content}</p>
                <p className="font-mono-data text-[11px] text-mute">{p.table}</p>
              </div>
              <div className="flex shrink-0 gap-1.5">
                <Button variant="ghost" size="sm" onClick={() => resolve(p.id)} aria-label="Confirm">
                  <FiCheck size={14} className="text-success" />
                </Button>
                <Button variant="ghost" size="sm" onClick={() => resolve(p.id)} aria-label="Reject">
                  <FiX size={14} className="text-danger" />
                </Button>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div>
        <h2 className="mb-2 text-sm font-medium text-mute">Recent decisions</h2>
        <div className="space-y-2">
          {DEMO_DECISIONS.map((d) => (
            <div key={d.id} className="rounded-md border border-line bg-surface px-3 py-2.5 text-sm">
              <p className="text-ink">{d.decision}</p>
              <p className="mt-1 text-xs text-mute">{d.reasoning}</p>
              <p className="mt-1 font-mono-data text-[11px] text-unverified">
                confidence {d.confidence.toFixed(2)}
              </p>
            </div>
          ))}
        </div>
      </div>

      <div>
        <h2 className="mb-2 text-sm font-medium text-mute">Taste profile</h2>
        <div className="space-y-2">
          {DEMO_TASTE.map((t, i) => (
            <div key={i} className="flex items-center justify-between rounded-md border border-line bg-surface px-3 py-2 text-sm">
              <span className="text-ink">{t.preference}</span>
              <span className="font-mono-data text-[11px] text-mute">{t.category}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
