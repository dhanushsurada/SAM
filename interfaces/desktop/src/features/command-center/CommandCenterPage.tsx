import { useState } from "react";
import {
  FiCamera,
  FiMusic,
  FiActivity,
  FiFolder,
  FiZap,
  FiSun,
  FiCheckSquare,
  FiLayers,
  FiRadio,
  FiCpu,
  FiShield,
} from "react-icons/fi";
import { useTaskSession } from "@/stores/taskSession";
import { TaskComposer } from "@/features/iqoo/TaskComposer";
import { ActiveTask } from "@/features/iqoo/ActiveTask";
import { BrainCard } from "./BrainCard";
import { SystemPulse } from "./SystemPulse";
import { RecentTasks } from "./RecentTasks";
import { ExecutiveBriefingCard } from "./ExecutiveBriefingCard";

const QUICK_ACTIONS = [
  {
    icon: FiSun,
    label: "Morning Briefing",
    tag: "Briefing",
    prompt: "Give me an executive morning briefing of my schedule, priority mail, and daily goals",
  },
  {
    icon: FiCheckSquare,
    label: "On My Plate",
    tag: "Focus",
    prompt: "What's on my plate from my real life today? Check my notes and priorities",
  },
  {
    icon: FiCamera,
    label: "Verified Screenshot",
    tag: "Vision",
    prompt: "Take a verified screenshot of the current screen and save it to the Desktop",
  },
  {
    icon: FiMusic,
    label: "Play Lofi Chill",
    tag: "Media",
    prompt: "Open YouTube in the browser and search for lofi chill beats to relax",
  },
  {
    icon: FiLayers,
    label: "Sync Mesh Fabric",
    tag: "Fabric",
    prompt: "Check omnichannel bridge status and sync cross-device mesh clipboard",
  },
  {
    icon: FiActivity,
    label: "System Health & CPU",
    tag: "Telemetry",
    prompt: "Check system CPU, memory, running processes and disk usage",
  },
  {
    icon: FiFolder,
    label: "Explore Workspaces",
    tag: "Workspace",
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
    <div className="mx-auto max-w-4xl space-y-6 pb-12">
      {/* High-Tech HUD Header */}
      <div className="relative overflow-hidden rounded-2xl border border-line/70 bg-gradient-to-r from-surface via-surface-raised to-surface p-5 shadow-lg backdrop-blur-xl">
        <div className="absolute -right-12 -top-12 h-36 w-36 rounded-full bg-ember/10 blur-3xl pointer-events-none" />
        <div className="absolute -left-12 -bottom-12 h-36 w-36 rounded-full bg-blue-500/10 blur-3xl pointer-events-none" />

        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2.5">
              <span className="relative flex h-3 w-3">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                <span className="relative inline-flex rounded-full h-3 w-3 bg-emerald-500" />
              </span>
              <h1 className="text-xl font-bold tracking-tight text-ink">SAM Autonomous Cockpit</h1>
              <span className="rounded-full bg-surface-raised border border-line px-2.5 py-0.5 font-mono text-[10px] text-mute font-medium">
                v2.1.1 Enterprise
              </span>
            </div>
            <p className="mt-1 text-xs text-mute max-w-xl">
              Next-generation local-first autonomous intelligence. Plans multi-step reasoning, operates desktop tools, coordinates cross-device mesh fabrics, and verifies execution with vision.
            </p>
          </div>

          {/* Telemetry Live Badges */}
          <div className="flex flex-wrap sm:flex-col items-end gap-1.5 shrink-0 text-[11px] font-mono-data">
            <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-surface border border-line text-ink">
              <FiZap size={12} className="text-emerald-400" />
              <span>JEV Reflex: <strong className="text-emerald-400 font-bold">&lt;1ms Direct Bypass</strong></span>
            </div>
            <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-surface border border-line text-mute">
              <FiRadio size={12} className="text-blue-400" />
              <span>Fabric Mesh: <strong className="text-ink">33 Nodes Online</strong></span>
            </div>
          </div>
        </div>

        {/* Status Highlights Bar */}
        <div className="mt-4 pt-3 border-t border-line/40 grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
          <div className="flex items-center gap-2">
            <FiShield size={13} className="text-ember" />
            <span className="text-[11px] text-mute">Sovereign: <strong className="text-ink">100% Local</strong></span>
          </div>
          <div className="flex items-center gap-2">
            <FiCpu size={13} className="text-purple-400" />
            <span className="text-[11px] text-mute">Inference: <strong className="text-ink">Ollama Local</strong></span>
          </div>
          <div className="flex items-center gap-2">
            <FiCamera size={13} className="text-sky-400" />
            <span className="text-[11px] text-mute">Vision: <strong className="text-ink">Multi-Tier Screen</strong></span>
          </div>
          <div className="flex items-center gap-2">
            <FiLayers size={13} className="text-pink-400" />
            <span className="text-[11px] text-mute">Bridges: <strong className="text-ink">Omnichannel</strong></span>
          </div>
        </div>
      </div>

      {/* Quick Action Chips */}
      <div className="space-y-1.5">
        <div className="flex items-center justify-between text-[11px] text-mute font-mono">
          <span className="flex items-center gap-1">
            <FiZap size={11} className="text-ember" /> Quick Executive Actions:
          </span>
          <span className="text-[10px] text-mute/60">Click chip to stage task</span>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {QUICK_ACTIONS.map((action) => {
            const Icon = action.icon;
            return (
              <button
                key={action.label}
                type="button"
                onClick={() => setPresetText(action.prompt)}
                className="group flex items-center gap-2 rounded-xl border border-line/80 bg-surface/90 px-3 py-1.5 text-xs text-mute hover:border-ember/50 hover:bg-surface-raised hover:text-ink transition-all cursor-pointer shadow-sm active:scale-95"
              >
                <div className="flex h-5 w-5 items-center justify-center rounded-lg bg-surface-raised border border-line/60 group-hover:border-ember/40 text-ember transition-colors">
                  <Icon size={12} />
                </div>
                <span className="font-medium">{action.label}</span>
                <span className="text-[9px] font-mono px-1 py-0.2 rounded bg-surface border border-line/60 text-mute/70">
                  {action.tag}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Primary Task Composer */}
      <div className="relative rounded-2xl p-[1px] bg-gradient-to-b from-ember/30 via-line/40 to-line/20 shadow-md">
        <TaskComposer
          onSubmit={submitTask}
          submitting={submitting}
          presetText={presetText}
          onClearPreset={() => setPresetText("")}
        />
      </div>
      {submitError && (
        <div className="rounded-lg border border-danger/30 bg-danger/10 p-3 text-xs text-danger font-medium">
          {submitError}
        </div>
      )}

      {/* Active Task Execution Display */}
      {selectedTask && (
        <ActiveTask
          task={selectedTask}
          events={events}
          streamError={streamError}
          onCancel={cancelSelected}
          onRetry={retrySelected}
          onEditAndResubmit={(instruction) => void submitTask({ instruction, input_type: "text", attachments: [] })}
          cancelling={cancelling}
          retrying={retrying}
        />
      )}

      {/* Executive Briefing & Daily Plate Widget */}
      <ExecutiveBriefingCard onRunTask={(prompt) => setPresetText(prompt)} />

      {/* System Telemetry & Local Brain Cards */}
      <div className="grid gap-4 grid-cols-1 md:grid-cols-2">
        <SystemPulse health={health} loading={healthLoading} error={healthError} />
        <BrainCard />
      </div>

      {/* Recent Tasks List */}
      <RecentTasks tasks={sessionTasks} onSelect={selectTask} />
    </div>
  );
}
