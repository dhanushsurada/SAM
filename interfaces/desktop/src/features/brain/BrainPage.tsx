import { FiRefreshCw } from "react-icons/fi";
import { Button } from "@/components/Button";
import { PageHeader } from "@/components/PageHeader";
import { StatusPill } from "@/components/StatusPill";
import type { BrainStatus, ModelInfo } from "@/api/types";
import { useBrain } from "./useBrain";
import { activeSourceLabel, describeOverrides, modelMeta, switchBlockedReason } from "./format";

function Chip({ children, tone }: { children: string; tone: "ember" | "plain" }) {
  return (
    <span
      className={`rounded-full border px-2 py-0.5 text-[11px] font-medium ${
        tone === "ember" ? "border-ember/40 bg-ember/10 text-ember-text" : "border-line text-mute"
      }`}
    >
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

  return (
    <div className="mx-auto max-w-2xl space-y-4">
      <PageHeader
        title="Brain"
        mode="live"
        description="The local model SAM thinks with. Pick any model installed in Ollama. The change applies to the next task and is saved for restarts."
      />

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

          <div className="space-y-2">
            <h2 className="text-sm font-medium text-mute">Installed models ({status.models.length})</h2>
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
