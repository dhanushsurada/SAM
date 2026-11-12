import { useState, useEffect, useCallback, type ChangeEvent } from "react";
import { FiSearch, FiTrash2, FiDatabase, FiClock } from "react-icons/fi";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/Button";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import {
  getMemoryEpisodes,
  searchMemory,
  clearMemory,
  type MemoryEpisode,
  type SemanticMemoryResult,
} from "@/api/client";

export function MemoryPage() {
  const [episodes, setEpisodes] = useState<MemoryEpisode[]>([]);
  const [query, setQuery] = useState("");
  const [searchResults, setSearchResults] = useState<SemanticMemoryResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [searching, setSearching] = useState(false);
  const [confirmClear, setConfirmClear] = useState(false);
  const [clearing, setClearing] = useState(false);

  const fetchEpisodes = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getMemoryEpisodes(50);
      setEpisodes(data.episodes || []);
    } catch {
      // fallback
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchEpisodes();
  }, [fetchEpisodes]);

  const handleSearch = async (val: string) => {
    setQuery(val);
    if (!val.trim()) {
      setSearchResults([]);
      return;
    }
    setSearching(true);
    try {
      const res = await searchMemory(val.trim());
      setSearchResults(res.results || []);
    } catch {
      setSearchResults([]);
    } finally {
      setSearching(false);
    }
  };

  const handleClearAll = async () => {
    setClearing(true);
    try {
      await clearMemory();
      setEpisodes([]);
      setSearchResults([]);
      setConfirmClear(false);
    } catch {
      // ignore
    } finally {
      setClearing(false);
    }
  };

  return (
    <div className="mx-auto max-w-2xl space-y-6 pb-12">
      <div className="flex items-start justify-between gap-3">
        <PageHeader
          title="Memory"
          mode="live"
          description="Episodic and semantic recall stored permanently in SQLite and ChromaDB. Survives application restarts and system updates."
        />
        <Button
          variant="secondary"
          size="sm"
          onClick={() => setConfirmClear(true)}
          disabled={episodes.length === 0}
        >
          <FiTrash2 size={13} /> Clear
        </Button>
      </div>

      {/* Semantic Memory Search */}
      <div className="space-y-2">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-mute">Semantic Search</h2>
        <div className="flex items-center gap-2 rounded-md border border-line bg-surface px-3 py-2">
          <FiSearch size={14} className="text-mute" />
          <input
            value={query}
            onChange={(e: ChangeEvent<HTMLInputElement>) => void handleSearch(e.target.value)}
            placeholder="Search recalled memories, past tasks, or facts..."
            className="w-full bg-transparent text-xs text-ink placeholder:text-mute focus:outline-none"
          />
          {searching && <span className="text-[11px] text-mute animate-pulse">Searching...</span>}
        </div>

        {query.trim() && (
          <div className="space-y-1.5 pt-1">
            {searchResults.length === 0 && !searching && (
              <p className="text-xs text-mute py-2 text-center border border-dashed border-line rounded">
                No matching semantic memories found for "{query}".
              </p>
            )}
            {searchResults.map((r, i) => (
              <div key={i} className="rounded-md border border-line bg-surface px-3 py-2.5 text-xs space-y-1">
                <p className="text-ink">{r.content}</p>
                {r.relevance !== undefined && (
                  <p className="font-mono-data text-[10px] text-emerald-400">
                    relevance {(r.relevance * 100).toFixed(0)}%
                  </p>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Recent Episodes */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-mute">
            Recent Episodes ({episodes.length})
          </h2>
          <span className="text-[11px] text-mute flex items-center gap-1 font-mono-data">
            <FiDatabase size={11} /> ~/.sam_data/memory.db
          </span>
        </div>

        {loading ? (
          <div className="py-8 text-center text-xs text-mute">Loading episodes from database...</div>
        ) : episodes.length === 0 ? (
          <div className="rounded-md border border-dashed border-line py-8 text-center text-xs text-mute">
            No memory episodes recorded yet. Ask SAM questions or run tasks to generate memory.
          </div>
        ) : (
          <div className="space-y-2">
            {episodes.map((e, idx) => (
              <div key={idx} className="rounded-md border border-line bg-surface p-3 text-xs space-y-1.5">
                <div className="flex items-center justify-between text-[11px] text-mute font-mono-data border-b border-line/60 pb-1">
                  <span className="flex items-center gap-1 text-ink/70">
                    <FiClock size={11} /> {new Date(e.timestamp).toLocaleString()}
                  </span>
                  {e.action && (
                    <span className="rounded bg-surface-raised px-1.5 py-0.5 text-[10px] text-ember">
                      {e.action}
                    </span>
                  )}
                </div>
                <div>
                  <span className="text-mute font-medium">User: </span>
                  <span className="text-ink">{e.user}</span>
                </div>
                <div>
                  <span className="text-mute font-medium">SAM: </span>
                  <span className="text-ink/90">{e.response}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <ConfirmDialog
        open={confirmClear}
        title="Clear Memory Store?"
        description="This will permanently delete all past conversation episodes and semantic embeddings from your local memory database. This cannot be undone."
        confirmLabel="Clear All"
        confirming={clearing}
        onConfirm={handleClearAll}
        onCancel={() => setConfirmClear(false)}
      />
    </div>
  );
}
