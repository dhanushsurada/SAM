import { Link } from "react-router-dom";
import { StatusPill } from "@/components/StatusPill";
import type { TaskRecord } from "@/api/types";
import { phaseToSamState } from "@/features/iqoo/phase";

export function RecentTasks({
  tasks,
  onSelect,
}: {
  tasks: TaskRecord[];
  onSelect: (id: string) => void;
}) {
  const recent = [...tasks].reverse().slice(0, 3);

  return (
    <div className="space-y-2 rounded-lg border border-line bg-surface p-4 shadow-panel">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-medium text-mute">Recent tasks</h2>
        <Link to="/iqoo" className="text-xs text-ember-text hover:underline">
          Open iQOO workspace →
        </Link>
      </div>

      {recent.length === 0 && <p className="text-xs text-mute">Nothing sent yet.</p>}

      <div className="space-y-1">
        {recent.map((task) => (
          <button
            key={task.task_id}
            onClick={() => onSelect(task.task_id)}
            className="flex w-full items-center gap-2 rounded-md px-1.5 py-1.5 text-left text-xs hover:bg-void"
          >
            <StatusPill state={phaseToSamState(task.status)} />
            <span className="min-w-0 flex-1 truncate text-ink">{task.instruction}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
