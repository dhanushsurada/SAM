import { Link } from "react-router-dom";
import { StatusPill } from "@/components/StatusPill";
import { Card } from "@/components/Card";
import type { TaskRecord } from "@/api/types";
import { phaseToSamState } from "@/features/iqoo/phase";
import { useTaskLabel } from "@/features/voice/VoiceControls";

export function RecentTasks({
  tasks,
  onSelect,
}: {
  tasks: TaskRecord[];
  onSelect: (id: string) => void;
}) {
  const recent = [...tasks].reverse().slice(0, 5);
  const labelOf = useTaskLabel();

  return (
    <Card className="space-y-3">
      <div className="flex items-center justify-between border-b border-line/40 pb-2">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-mute">Recent tasks</h2>
        <Link to="/tasks" className="text-xs text-ember-text hover:underline">
          View all ({tasks.length})
        </Link>
      </div>

      {recent.length === 0 && (
        <p className="py-4 text-center text-xs text-mute/60">
          No tasks dispatched yet. Run a prompt above or pick a quick action.
        </p>
      )}

      <div className="space-y-1">
        {recent.map((task) => (
          <button
            key={task.task_id}
            onClick={() => onSelect(task.task_id)}
            className="flex w-full items-center justify-between gap-2.5 rounded-lg px-2 py-1.5 text-left text-xs hover:bg-void/70 hover:border-line/60 border border-transparent transition-all cursor-pointer"
          >
            <div className="flex items-center gap-2 truncate min-w-0">
              <StatusPill state={phaseToSamState(task.status)} />
              <span className="truncate text-ink font-medium">{labelOf(task)}</span>
            </div>
            <span className="shrink-0 font-mono text-[10px] text-mute/60">
              {task.task_id.slice(-6)}
            </span>
          </button>
        ))}
      </div>
    </Card>
  );
}
