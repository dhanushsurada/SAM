import { FiTrash2 } from "react-icons/fi";
import { ModeBadge } from "@/components/ModeBadge";
import { Button } from "@/components/Button";
import { useTaskSession } from "@/stores/taskSession";
import { TaskComposer } from "./TaskComposer";
import { ActiveTask } from "./ActiveTask";
import { SessionTaskList } from "./SessionTaskList";
import { HealthPanel } from "./HealthPanel";

/**
 * All state lives in stores/taskSession.tsx now, shared with Command
 * Center's quick-input card — this component is layout + composition
 * only. See that file's doc comment for why the state had to move.
 */
export function IqooPage() {
  const {
    sessionTasks,
    selectedTaskId,
    selectedTask,
    selectTask,
    events,
    streamError,
    submitting,
    submitError,
    submitTask,
    cancelling,
    cancelSelected,
    retrying,
    retrySelected,
    resetting,
    demoReset,
    health,
    healthLoading,
    healthError,
    refreshHealth,
  } = useTaskSession();

  const handleDemoReset = async () => {
    // window.confirm as a functional stand-in for a styled ConfirmDialog —
    // that primitive is still on the component inventory (PHASE5_PLAN.md
    // §E), not built yet. This clears real server-side state, so it gets a
    // confirmation step either way rather than waiting for the nicer one.
    if (!window.confirm("Clear all task state on the gateway? This can't be undone.")) return;
    await demoReset();
  };

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h1 className="text-lg font-semibold text-ink">iQOO workspace</h1>
          <ModeBadge mode="live" />
        </div>
        <Button variant="ghost" size="sm" onClick={handleDemoReset} loading={resetting}>
          <FiTrash2 size={14} /> Demo reset
        </Button>
      </div>

      <TaskComposer onSubmit={submitTask} submitting={submitting} />
      {submitError && <p className="text-xs text-danger">{submitError}</p>}

      <div className="grid gap-4 md:grid-cols-[1fr_260px]">
        <div>
          {selectedTask ? (
            <ActiveTask
              task={selectedTask}
              events={events}
              streamError={streamError}
              onCancel={cancelSelected}
              onRetry={retrySelected}
              cancelling={cancelling}
              retrying={retrying}
            />
          ) : (
            <p className="rounded-lg border border-dashed border-line px-4 py-10 text-center text-sm text-mute">
              Send a task above, or pick one from the list to see it live.
            </p>
          )}
        </div>
        <div className="space-y-4">
          <HealthPanel health={health} loading={healthLoading} error={healthError} onRefresh={refreshHealth} />
          <SessionTaskList tasks={sessionTasks} selectedId={selectedTaskId} onSelect={selectTask} />
        </div>
      </div>
    </div>
  );
}
