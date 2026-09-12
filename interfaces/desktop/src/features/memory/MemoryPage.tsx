import { useState, type ChangeEvent } from "react";
import { FiSearch, FiTrash2 } from "react-icons/fi";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/Button";
import { getRecentEpisodes, searchSemantic } from "./demoMemoryService";

export function MemoryPage() {
  const [query, setQuery] = useState("");
  const episodes = getRecentEpisodes();
  const results = searchSemantic(query);

  return (
    <div className="mx-auto max-w-2xl space-y-5">
      <div className="flex items-start justify-between gap-3">
        <PageHeader
          title="Memory"
          mode="demo"
          description="Episodic and semantic memory. No HTTP layer exists over MemoryStore yet — this is canned data, not your real memory."
        />
        <Button
          variant="secondary"
          size="sm"
          disabled
          title="MemoryStore has no delete/reset method yet, even internally — see PHASE5_PLAN.md §F"
        >
          <FiTrash2 size={14} /> Clear
        </Button>
      </div>

      <div>
        <h2 className="mb-2 text-sm font-medium text-mute">Search (filters the demo set below, live)</h2>
        <div className="flex items-center gap-2 rounded-md border border-line bg-surface px-3 py-2">
          <FiSearch size={14} className="text-mute" />
          <input
            value={query}
            onChange={(e: ChangeEvent<HTMLInputElement>) => setQuery(e.target.value)}
            placeholder="Try “ollama” or “communication”"
            className="w-full bg-transparent text-sm text-ink placeholder:text-mute focus:outline-none"
          />
        </div>
        {query && (
          <div className="mt-2 space-y-1.5">
            {results.length === 0 && <p className="text-xs text-mute">No matches in the demo set.</p>}
            {results.map((r) => (
              <div key={r.id} className="rounded-md border border-line bg-surface px-3 py-2 text-sm">
                <p className="text-ink">{r.content}</p>
                <p className="mt-1 font-mono-data text-[11px] text-unverified">
                  {r.category} · score {r.score.toFixed(2)}
                </p>
              </div>
            ))}
          </div>
        )}
      </div>

      <div>
        <h2 className="mb-2 text-sm font-medium text-mute">Recent episodes</h2>
        <div className="space-y-1.5">
          {episodes.map((e) => (
            <div key={e.id} className="rounded-md border border-line bg-surface px-3 py-2 text-sm">
              <p className="text-ink">{e.content}</p>
              <p className="mt-1 font-mono-data text-[11px] text-mute">
                {new Date(e.timestamp).toLocaleString()} · kept {e.retention_days}d
              </p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
