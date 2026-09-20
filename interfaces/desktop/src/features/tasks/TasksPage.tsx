import { PageHeader } from "@/components/PageHeader";
import { useTaskSession } from "@/stores/taskSession";
import { TaskComposer } from "@/features/iqoo/TaskComposer";
import { ActiveTask } from "@/features/iqoo/ActiveTask";
import { SessionTaskList } from "@/features/iqoo/SessionTaskList";
import { LifecycleStrip } from "./LifecycleStrip";

/**
 * SAM's general task console: give SAM something to do, watch it move from
 * request to outcome, cancel or retry it. It says nothing about the
 * browser or the phone because neither defines a task — a task is whatever
 * the ReAct loop runs, and it reaches for desktop control, vision, the
 * browser or the terminal as the work needs (see Hands).
 *
 * Same session store as Command Center and the iQOO workspace, so a task
 * started anywhere shows up here.
 */
export function TasksPage() {
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
  } = useTaskSession();

  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <PageHeader
        title="Tasks"
        mode="live"
        description="What SAM is doing and has done this session, from request to outcome. A task runs on this computer and can use any of SAM's Hands."
      />

      <TaskComposer onSubmit={submitTask} submitting={submitting} />
      {submitError && <p className="text-xs text-danger">{submitError}</p>}

      <div className="grid gap-4 md:grid-cols-[260px_1fr]">
        <SessionTaskList tasks={sessionTasks} selectedId={selectedTaskId} onSelect={selectTask} />

        <div className="space-y-3">
          {selectedTask ? (
            <>
              <LifecycleStrip events={events} status={selectedTask.status} />
              <ActiveTask
                task={selectedTask}
                events={events}
                streamError={streamError}
                onCancel={cancelSelected}
                onRetry={retrySelected}
                cancelling={cancelling}
                retrying={retrying}
              />
            </>
          ) : (
            <p className="rounded-lg border border-dashed border-line px-4 py-10 text-center text-sm text-mute">
              Send SAM a task above, or pick one from the list to follow it.
            </p>
          )}
          <p className="text-xs text-mute">
            Tasks sent from a phone client run through the same pipeline but aren't listed here: the gateway
            keeps a task ledger, and no endpoint exposes it yet.
          </p>
        </div>
      </div>
    </div>
  );
}
