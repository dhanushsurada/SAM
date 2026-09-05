// VEDA screens (M8-B). Depends on components.jsx (loaded first, see
// index.html) and the global `Api` client (lib/api.js, loaded first).

const { useState, useEffect, useRef } = React;

// calculate()'s tool output is always exactly "<expression> = <result>"
// (sovereign/tools/calculate.py — the expression is AST-validated
// arithmetic, so it can never itself contain " = "). Splitting on that
// literal is safe and exact, not a fragile guess.
function parseCalculation(observation) {
  const parts = observation.split(' = ');
  if (parts.length !== 2) return null;
  return { expression: parts[0], result: parts[1] };
}

const ACTION_BADGE = {
  read_document: 'READ',
  search_knowledge: 'SEARCH',
  calculate: 'CALCULATE',
  create_document: 'DRAFT',
};

// ─── Workspace ───────────────────────────────────────────────────────────

function TaskComposer({ onSubmit, busy, error, placeholder }) {
  const [text, setText] = useState('');
  return (
    <Card className="p-5">
      <LabelMicro className="mb-3">Run a Sovereign Task</LabelMicro>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        disabled={busy}
        rows={3}
        placeholder={placeholder || 'e.g. Review the inspection report against the applicable SOP, calculate the deviation, and prepare an approval note with supporting evidence.'}
        className="w-full resize-none rounded-lg border border-line p-3 text-sm focus:outline-none focus:ring-2 focus:ring-ink/20 disabled:bg-black/5 disabled:text-muted"
      />
      <div className="flex items-center justify-between mt-3">
        <span className="text-xs text-warn">{error || ''}</span>
        <button
          onClick={() => { if (text.trim()) { onSubmit(text.trim()); } }}
          disabled={busy || !text.trim()}
          className="px-4 py-2 rounded-lg bg-ink text-white text-sm font-medium disabled:bg-black/20 disabled:cursor-not-allowed"
        >
          {busy ? <>Running <Dots /></> : 'Run Task'}
        </button>
      </div>
    </Card>
  );
}

function WorkspaceScreen({ status, model, documents, lastTask, onSubmitTask, taskBusy, taskError, onNavigate }) {
  return (
    <div className="p-8 max-w-5xl mx-auto flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Workspace</h1>
        <p className="text-sm text-muted mt-1">Confidential industrial document analysis — processed entirely on this machine.</p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatBlock label="Documents" value={String(documents.length).padStart(2, '0')} sub={documents.length ? `${documents.filter(d => d.status === 'indexed').length} indexed` : 'none uploaded yet'} />
        <StatBlock label="Model" value={model?.status === 'ready' ? model.active_model : '—'} sub={model?.status === 'ready' ? 'local · ready' : (model?.detail || 'checking…')} />
        <StatBlock label="Sovereign Mode" value={status ? (status.sovereign_mode ? 'ON' : 'OFF') : '—'} dark={!!status?.sovereign_mode} sub="network guard" />
        <StatBlock label="Last Task" value={lastTask ? lastTask.status.toUpperCase() : '—'} sub={lastTask ? `${lastTask.steps.length} step(s) recorded` : 'none run yet'} />
      </div>

      <TaskComposer onSubmit={onSubmitTask} busy={taskBusy} error={taskError} />

      {lastTask && (
        <Card className="p-5 cursor-pointer hover:border-ink/30 transition-colors" >
          <div className="flex items-center justify-between">
            <div>
              <LabelMicro>Most Recent Task</LabelMicro>
              <p className="text-sm mt-1 max-w-xl truncate">{lastTask.task}</p>
            </div>
            <div className="flex items-center gap-3">
              <StatusPill status={lastTask.status} />
              <button onClick={() => onNavigate('activity')} className="text-xs font-medium underline underline-offset-2">
                View Activity →
              </button>
            </div>
          </div>
        </Card>
      )}
    </div>
  );
}

// ─── Documents ───────────────────────────────────────────────────────────

function UploadControl({ onUpload, uploading, error }) {
  const inputRef = useRef(null);
  const [dragOver, setDragOver] = useState(false);

  const handleFiles = (files) => {
    if (files && files[0]) onUpload(files[0]);
  };

  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(e) => { e.preventDefault(); setDragOver(false); handleFiles(e.dataTransfer.files); }}
      className={
        'border border-dashed rounded-xl p-6 flex flex-col items-center justify-center gap-2 text-center transition-colors ' +
        (dragOver ? 'border-ink bg-black/5' : 'border-line')
      }
    >
      <p className="text-sm">{uploading ? <>Ingesting <Dots /></> : 'Drop a document here, or'}</p>
      {!uploading && (
        <button onClick={() => inputRef.current.click()} className="px-3 py-1.5 rounded-lg bg-ink text-white text-xs font-medium">
          Choose File
        </button>
      )}
      <p className="text-[11px] text-muted mt-1">PDF, DOCX, TXT, PNG, JPG, WEBP</p>
      {error && <p className="text-xs text-warn mt-1">{error}</p>}
      <input ref={inputRef} type="file" className="hidden"
             accept=".pdf,.docx,.txt,.png,.jpg,.jpeg,.webp"
             onChange={(e) => handleFiles(e.target.files)} />
    </div>
  );
}

function DocumentsScreen({ documents, onUpload, uploading, uploadError }) {
  return (
    <div className="p-8 max-w-5xl mx-auto flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Documents</h1>
        <p className="text-sm text-muted mt-1">Ingested locally, indexed into the local knowledge base. Nothing leaves this machine.</p>
      </div>

      <UploadControl onUpload={onUpload} uploading={uploading} error={uploadError} />

      {documents.length === 0 ? (
        <EmptyState>No documents yet — upload an inspection report, SOP, or photo to begin.</EmptyState>
      ) : (
        <Card className="overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-line">
                {['File', 'Type', 'Status', 'Chunks', ''].map((h) => (
                  <th key={h} className="text-left label-micro px-4 py-3">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {documents.map((d, i) => (
                <tr key={i} className="border-b border-line last:border-0">
                  <td className="px-4 py-3 font-medium">{d.filename}</td>
                  <td className="px-4 py-3 text-muted uppercase text-xs">{d.file_type}</td>
                  <td className="px-4 py-3"><StatusPill status={d.status} /></td>
                  <td className="px-4 py-3 font-mono text-xs">{d.status === 'indexed' ? d.chunk_count : '—'}</td>
                  <td className="px-4 py-3 text-xs text-warn">{d.detail || ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}

// ─── Activity ────────────────────────────────────────────────────────────

function ActivityStepRow({ step }) {
  const calc = step.action === 'calculate' ? parseCalculation(step.observation) : null;
  return (
    <div className="flex gap-3 py-3 border-b border-line last:border-0">
      <div className="pt-0.5">
        {step.success === false ? (
          <span className="text-warn font-bold">✗</span>
        ) : (
          <span className="text-ok font-bold">✓</span>
        )}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          {step.action && <span className="label-micro text-muted">{ACTION_BADGE[step.action] || step.action}</span>}
          <span className="text-sm">{step.label}</span>
        </div>
        {calc ? (
          <div className="mt-2 inline-flex items-baseline gap-3 bg-black/5 rounded-lg px-4 py-2 font-mono">
            <span className="text-sm text-muted">{calc.expression}</span>
            <span className="text-2xl font-semibold">= {calc.result}</span>
          </div>
        ) : (
          step.observation && (
            <p className="text-xs text-muted mt-1 line-clamp-2">{step.observation}</p>
          )
        )}
      </div>
    </div>
  );
}

function ActivityScreen({ task, onSubmitTask, taskBusy, taskError }) {
  if (!task) {
    return (
      <div className="p-8 max-w-3xl mx-auto flex flex-col gap-6">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Activity</h1>
          <p className="text-sm text-muted mt-1">No task has been run yet.</p>
        </div>
        <TaskComposer onSubmit={onSubmitTask} busy={taskBusy} error={taskError} />
      </div>
    );
  }

  return (
    <div className="p-8 max-w-3xl mx-auto flex flex-col gap-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Activity</h1>
          <p className="text-sm text-muted mt-1 max-w-xl">{task.task}</p>
        </div>
        <StatusPill status={task.status} />
      </div>

      <Card className="p-5">
        <LabelMicro className="mb-1">Agent Activity</LabelMicro>
        {task.steps.length === 0 ? (
          <p className="text-sm text-muted py-4">{task.status === 'running' ? <>Starting <Dots /></> : 'No steps recorded.'}</p>
        ) : (
          <div className="mt-2">
            {task.steps.map((s) => <ActivityStepRow key={s.step} step={s} />)}
            {task.status === 'running' && <p className="text-xs text-muted pt-3">Working <Dots /></p>}
          </div>
        )}
      </Card>

      {(task.status === 'completed' || task.status === 'incomplete') && task.result && (
        <Card className="p-5">
          <LabelMicro className="mb-2">Result</LabelMicro>
          <p className="text-sm whitespace-pre-wrap">{task.result}</p>
        </Card>
      )}

      {task.status === 'failed' && (
        <Card className="p-5 border-warn/30">
          <LabelMicro className="mb-2 text-warn">Error</LabelMicro>
          <p className="text-sm text-warn">{task.error}</p>
        </Card>
      )}
    </div>
  );
}

// ─── Evidence & Deliverable ──────────────────────────────────────────────

function EvidenceCard({ result }) {
  return (
    <div className="border border-line rounded-lg p-4">
      <p className="text-sm">{result.text}</p>
      <div className="flex items-center gap-4 mt-3 flex-wrap">
        <span className="text-xs text-muted"><span className="label-micro">Source </span>{result.filename}</span>
        {result.section && <span className="text-xs text-muted"><span className="label-micro">Section </span>{result.section}</span>}
        <span className="text-xs text-muted"><span className="label-micro">Relevance </span>{(result.relevance * 100).toFixed(0)}%</span>
      </div>
    </div>
  );
}

function SovereigntyPanel({ taskId }) {
  const [report, setReport] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setReport(null);
    setError(null);
    Api.getSovereignty(taskId)
      .then((r) => !cancelled && setReport(r))
      .catch((e) => !cancelled && setError(e.message));
    return () => { cancelled = true; };
  }, [taskId]);

  if (error) return <Card className="p-5"><p className="text-xs text-warn">{error}</p></Card>;
  if (!report) return <Card className="p-5"><p className="text-xs text-muted">Loading <Dots /></p></Card>;

  if (!report.measured) {
    return (
      <Card className="p-5">
        <LabelMicro>Sovereignty</LabelMicro>
        <p className="text-sm text-muted mt-2">Not measured — this task ran with Sovereign Mode off.</p>
      </Card>
    );
  }

  const r = report.report;
  return (
    <Card dark className="p-5 flex flex-col gap-4">
      <LabelMicro className="text-white/50">Sovereignty</LabelMicro>
      <div className="grid grid-cols-2 gap-4">
        <div>
          <div className="text-[11px] text-white/50 uppercase tracking-wide">External Connections</div>
          <div className="text-3xl font-mono font-semibold">{String(r.external_transmission_count).padStart(2, '0')}</div>
        </div>
        <div>
          <div className="text-[11px] text-white/50 uppercase tracking-wide">Blocked Attempts</div>
          <div className="text-3xl font-mono font-semibold">{String(r.blocked_count).padStart(2, '0')}</div>
        </div>
      </div>
      <div className="text-xs text-white/60">
        {r.external_transmission_count === 0
          ? 'No data left this machine during this task.'
          : `${r.external_transmission_count} external connection(s) were allowed — see attempts below.`}
      </div>
    </Card>
  );
}

function EvidenceDeliverableScreen({ task }) {
  const [query, setQuery] = useState('');
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState(null);
  const [results, setResults] = useState(null);
  const [available, setAvailable] = useState(true);

  const runSearch = async () => {
    if (!query.trim()) return;
    setSearching(true);
    setSearchError(null);
    try {
      const res = await Api.searchKnowledge(query.trim());
      setAvailable(res.available);
      setResults(res.results);
    } catch (e) {
      setSearchError(e.message);
    } finally {
      setSearching(false);
    }
  };

  return (
    <div className="p-8 max-w-6xl mx-auto grid grid-cols-1 lg:grid-cols-3 gap-6">
      <div className="lg:col-span-2 flex flex-col gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Evidence</h1>
          <p className="text-sm text-muted mt-1">Search the local knowledge base directly — every result is traced to its source document.</p>
        </div>
        <div className="flex gap-2">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && runSearch()}
            placeholder="e.g. maximum allowed pressure"
            className="flex-1 rounded-lg border border-line px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ink/20"
          />
          <button onClick={runSearch} disabled={searching || !query.trim()}
                  className="px-4 py-2 rounded-lg bg-ink text-white text-sm font-medium disabled:bg-black/20">
            {searching ? <Dots /> : 'Search'}
          </button>
        </div>
        {searchError && <p className="text-xs text-warn">{searchError}</p>}
        {results === null ? (
          <EmptyState>Search results (with source, section, and relevance) will appear here.</EmptyState>
        ) : !available ? (
          <EmptyState>No documents have been indexed yet — upload one in Documents first.</EmptyState>
        ) : results.length === 0 ? (
          <EmptyState>No matching passages found.</EmptyState>
        ) : (
          <div className="flex flex-col gap-3">
            {results.map((r, i) => <EvidenceCard key={i} result={r} />)}
          </div>
        )}
      </div>

      <div className="flex flex-col gap-4">
        <LabelMicro>Deliverable</LabelMicro>
        {!task || !task.deliverable ? (
          <EmptyState>No approval note has been generated yet.</EmptyState>
        ) : (
          <Card className="p-5 flex flex-col gap-4">
            <div>
              <p className="text-sm font-medium">{task.deliverable.filename}</p>
              <p className="text-xs text-ok mt-1">Generated</p>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <LabelMicro>Sources</LabelMicro>
                <div className="text-2xl font-mono font-semibold">{task.deliverable.sources}</div>
              </div>
              <div>
                <LabelMicro>Evidence</LabelMicro>
                <div className="text-2xl font-mono font-semibold">{task.deliverable.evidence_count}</div>
              </div>
            </div>
            <a href={Api.deliverableFileUrl(task.id)} download
               className="text-center px-4 py-2 rounded-lg bg-ink text-white text-sm font-medium">
              Export DOCX
            </a>
          </Card>
        )}
        {task?.has_sovereignty_report && <SovereigntyPanel taskId={task.id} />}
      </div>
    </div>
  );
}
