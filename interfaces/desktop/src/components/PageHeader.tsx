import type { DataMode } from "./ModeBadge";
import { ModeBadge } from "./ModeBadge";

export function PageHeader({
  title,
  mode,
  description,
}: {
  title: string;
  mode?: DataMode;
  description?: string;
}) {
  return (
    <div className="space-y-1">
      <div className="flex items-center gap-2">
        <h1 className="text-lg font-semibold text-ink">{title}</h1>
        {mode && <ModeBadge mode={mode} />}
      </div>
      {description && <p className="text-sm text-mute">{description}</p>}
    </div>
  );
}
