import { useTaskSession } from "@/stores/taskSession";
import { TaskComposer } from "@/features/iqoo/TaskComposer";
import { ActiveTask } from "@/features/iqoo/ActiveTask";
import { BrainCard } from "./BrainCard";
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
          Tell SAM what to do. It plans the work, acts on this computer, and checks each step's result
          before it reports back.
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
        <BrainCard />
      </div>

      <RecentTasks tasks={sessionTasks} onSelect={selectTask} />
    </div>
  );
}
