import { FiCpu } from "react-icons/fi";
import { useTaskSession } from "@/stores/taskSession";
import { EmptyState } from "@/components/EmptyState";
import { TaskComposer } from "@/features/iqoo/TaskComposer";
import { ActiveTask } from "@/features/iqoo/ActiveTask";
import { SystemPulse } from "./SystemPulse";
import { RecentTasks } from "./RecentTasks";

export function CommandCenterPage() {
  const {
    selectedTask,
    events,
    streamError,
    submitting,
    submitError,
    submitTask,
    cancelling,
    cancelSelected,
    retrying,
    retrySelected,
    sessionTasks,
    selectTask,
    health,
    healthLoading,
    healthError,
  } = useTaskSession();

  return (
    <div className="mx-auto max-w-2xl space-y-4">
      <div>
        <h1 className="text-lg font-semibold text-ink">Command Center</h1>
        <p className="text-sm text-mute">
          Tell SAM what to do — this submits through the same live iQOO gateway as the dedicated
          workspace, it's just the quick version.
        </p>
      </div>

      <TaskComposer onSubmit={submitTask} submitting={submitting} />
      {submitError && <p className="text-xs text-danger">{submitError}</p>}

      {selectedTask && (
        <ActiveTask
          task={selectedTask}
          events={events}
          streamError={streamError}
          onCancel={cancelSelected}
          onRetry={retrySelected}
          cancelling={cancelling}
          retrying={retrying}
        />
      )}

      <div className="grid gap-4 sm:grid-cols-2">
        <SystemPulse health={health} loading={healthLoading} error={healthError} />
        <EmptyState
          compact
          icon={FiCpu}
          title="Model"
          description="Active model, fallback, and Ollama availability — nothing surfaces this over HTTP yet."
          mode="planned"
          meta="Step 7 — see PHASE5_PLAN.md §F"
        />
      </div>

      <RecentTasks tasks={sessionTasks} onSelect={selectTask} />
    </div>
  );
}
