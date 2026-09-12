import { FiChevronRight } from "react-icons/fi";
import { StatusPill } from "@/components/StatusPill";
import type { TaskRecord } from "@/api/types";
import { phaseToSamState } from "./phase";

export function SessionTaskList({
  tasks,
  selectedId,
  onSelect,
}: {
  tasks: TaskRecord[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  if (tasks.length === 0) {
    return (
      <p className="rounded-lg border border-dashed border-line px-4 py-6 text-center text-xs text-mute">
        No tasks yet this session.
      </p>
    );
  }

  return (
    <div className="space-y-1">
      <p className="px-1 font-mono-data text-[10px] uppercase tracking-wider text-mute/70">
        This session ({tasks.length}) — not a persistent history, see PHASE5_PLAN.md §F
      </p>
      {[...tasks].reverse().map((task) => (
        <button
          key={task.task_id}
          onClick={() => onSelect(task.task_id)}
          className={`flex w-full items-center gap-2 rounded-md border px-2.5 py-2 text-left text-xs transition-colors duration-[var(--sam-motion-fast)] ${
            selectedId === task.task_id
              ? "border-ember/30 bg-ember/5"
              : "border-transparent hover:border-line hover:bg-surface"
          }`}
        >
          <StatusPill state={phaseToSamState(task.status)} />
          <span className="min-w-0 flex-1 truncate text-ink">{task.instruction}</span>
          <FiChevronRight size={12} className="shrink-0 text-mute" />
        </button>
      ))}
    </div>
  );
}
