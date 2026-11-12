import { useState } from "react";
import { FiCamera, FiMusic, FiActivity, FiFolder, FiZap } from "react-icons/fi";
import { useTaskSession } from "@/stores/taskSession";
import { TaskComposer } from "@/features/iqoo/TaskComposer";
import { ActiveTask } from "@/features/iqoo/ActiveTask";
import { BrainCard } from "./BrainCard";
import { SystemPulse } from "./SystemPulse";
import { RecentTasks } from "./RecentTasks";

const QUICK_ACTIONS = [
  {
    icon: FiCamera,
    label: "Screenshot to Desktop",
    prompt: "Take a screenshot of the current screen and save it to the Desktop",
  },
  {
    icon: FiMusic,
    label: "Play Lofi on YouTube",
    prompt: "Open YouTube in the browser and search for lofi chill beats to relax",
  },
  {
    icon: FiActivity,
    label: "Check System Health",
    prompt: "Check system CPU, memory, running processes and disk usage",
  },
  {
    icon: FiFolder,
    label: "Explore Workspaces",
    prompt: "List the active project directory files and git status",
  },
];

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

  const [presetText, setPresetText] = useState("");

  return (
    <div className="mx-auto max-w-2xl space-y-5">
      <div className="flex flex-col gap-1">
        <div className="flex items-center gap-2">
          <span className="flex h-2 w-2 rounded-full bg-ember animate-pulse" />
          <h1 className="text-xl font-bold tracking-tight text-ink">Command Center</h1>
        </div>
        <p className="text-xs text-mute/80">
          Give SAM high-level autonomous tasks. It plans multi-step actions, controls desktop tools, and verifies completion before reporting back.
        </p>
      </div>

      {/* Quick Action Chips */}
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-[11px] font-mono text-mute/60 mr-1 flex items-center gap-1">
          <FiZap size={11} className="text-ember" /> Quick:
        </span>
        {QUICK_ACTIONS.map((action) => {
          const Icon = action.icon;
          return (
            <button
              key={action.label}
              type="button"
              onClick={() => setPresetText(action.prompt)}
              className="flex items-center gap-1.5 rounded-lg border border-line/70 bg-surface/70 px-2.5 py-1 text-xs text-mute hover:border-ember/40 hover:bg-surface hover:text-ink transition-all cursor-pointer shadow-sm active:scale-95"
            >
              <Icon size={12} className="text-ember shrink-0" />
              <span>{action.label}</span>
            </button>
          );
        })}
      </div>

      <TaskComposer
        onSubmit={submitTask}
        submitting={submitting}
        presetText={presetText}
        onClearPreset={() => setPresetText("")}
      />
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
