// VEDA app root (M8-B). Depends on components.jsx + screens.jsx (loaded
// first, see index.html) and the global `Api` client (lib/api.js).

const { useState, useEffect, useRef } = React;

const STATUS_POLL_MS = 4000;
const TASK_POLL_MS = 1200;

function App() {
  const [activeScreen, setActiveScreen] = useState('workspace');

  const [status, setStatus] = useState(null);
  const [model, setModel] = useState(null);
  const [documents, setDocuments] = useState([]);

  const [currentTask, setCurrentTask] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [taskError, setTaskError] = useState(null);

  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState(null);

  const taskPollRef = useRef(null);

  // ─── status/model/documents: cheap, always-on polling for the
  // always-visible top/bottom bars and the Workspace hero row.
  //
  // Reload recovery: currentTask lives only in React state, so a page
  // reload during — or right after — a live task would otherwise show
  // an empty Workspace as if nothing had happened, even though the
  // server-side TaskManager still has it. status.last_task_id (set once
  // per task and never cleared, unlike the manager's internal "is one
  // running right now" flag) is real existing server state, not
  // invented for this purpose. On the very first status fetch only, if
  // one exists, adopt it. ─────────────────────────────────────────────
  useEffect(() => {
    let cancelled = false;
    const load = () => {
      Api.status().then((s) => !cancelled && setStatus(s)).catch(() => {});
      Api.model().then((m) => !cancelled && setModel(m)).catch(() => {});
    };
    (async () => {
      try {
        const s = await Api.status();
        if (cancelled) return;
        setStatus(s);
        if (s.last_task_id) {
          const t = await Api.getTask(s.last_task_id);
          if (!cancelled) setCurrentTask(t);
        }
      } catch (_) { /* server not reachable yet — recurring poll below will retry */ }
    })();
    Api.model().then((m) => !cancelled && setModel(m)).catch(() => {});
    Api.listDocuments().then((d) => !cancelled && setDocuments(d)).catch(() => {});
    const id = setInterval(load, STATUS_POLL_MS);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  // ─── task polling: only while a task is actually in flight ───────────
  useEffect(() => {
    if (!currentTask || !['queued', 'running'].includes(currentTask.status)) {
      clearInterval(taskPollRef.current);
      return;
    }
    taskPollRef.current = setInterval(async () => {
      try {
        const t = await Api.getTask(currentTask.id);
        setCurrentTask(t);
        if (!['queued', 'running'].includes(t.status)) {
          clearInterval(taskPollRef.current);
          // A task just finished — its output is real, current state now,
          // so refresh the document list too (ingestion inside a task
          // isn't currently a real capability, but this keeps Workspace's
          // document count honest if that ever changes).
          Api.listDocuments().then(setDocuments).catch(() => {});
        }
      } catch (e) {
        clearInterval(taskPollRef.current);
        setCurrentTask((t) => t ? { ...t, status: 'failed', error: e.message } : t);
      }
    }, TASK_POLL_MS);
    return () => clearInterval(taskPollRef.current);
    // eslint-disable-next-line
  }, [currentTask?.id, currentTask?.status]);

  const handleSubmitTask = async (text) => {
    setSubmitting(true);
    setTaskError(null);
    try {
      const created = await Api.createTask(text);
      // Minimal shape until the first poll fills in the rest — matches
      // TaskStatusResponse's real fields, just empty/null until polled.
      setCurrentTask({
        id: created.task_id, task: text, status: created.status,
        created_at: Date.now() / 1000, started_at: null, completed_at: null,
        steps: [], result: null, error: null, deliverable: null,
      });
      setActiveScreen('activity');
    } catch (e) {
      setTaskError(e.message);
    } finally {
      setSubmitting(false);
    }
  };

  const handleUpload = async (file) => {
    setUploading(true);
    setUploadError(null);
    try {
      const info = await Api.uploadDocument(file);
      setDocuments((prev) => [...prev, info]);
      if (info.status === 'failed') setUploadError(info.detail || 'Ingestion failed');
    } catch (e) {
      setUploadError(e.message);
    } finally {
      setUploading(false);
    }
  };

  const taskBusy = submitting || (currentTask && ['queued', 'running'].includes(currentTask.status));

  let screen;
  if (activeScreen === 'workspace') {
    screen = (
      <WorkspaceScreen
        status={status} model={model} documents={documents} lastTask={currentTask}
        onSubmitTask={handleSubmitTask} taskBusy={taskBusy} taskError={taskError}
        onNavigate={setActiveScreen}
      />
    );
  } else if (activeScreen === 'documents') {
    screen = (
      <DocumentsScreen documents={documents} onUpload={handleUpload} uploading={uploading} uploadError={uploadError} />
    );
  } else if (activeScreen === 'activity') {
    screen = (
      <ActivityScreen task={currentTask} onSubmitTask={handleSubmitTask} taskBusy={taskBusy} taskError={taskError} />
    );
  } else {
    screen = <EvidenceDeliverableScreen task={currentTask} />;
  }

  return (
    <div className="h-screen flex flex-col bg-paper">
      <TopBar status={status} />
      <div className="flex flex-1 min-h-0">
        <NavRail active={activeScreen} onSelect={setActiveScreen} docCount={documents.length} taskStatus={currentTask?.status} />
        <main className="flex-1 overflow-y-auto">{screen}</main>
      </div>
      <BottomStatusBar status={status} model={model} />
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />);
