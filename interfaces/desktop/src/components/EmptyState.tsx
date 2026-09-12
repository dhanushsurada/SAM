import type { ReactNode } from "react";
import { ModeBadge, type DataMode } from "./ModeBadge";
import type { SamIcon } from "@/app/routes";

export interface EmptyStateProps {
  icon: SamIcon;
  title: string;
  description: string;
  mode?: DataMode;
  meta?: string;
  action?: ReactNode;
  /** Denser padding/icon for use inside a card grid (e.g. Command Center)
   * rather than as a full-page stub. */
  compact?: boolean;
}

export function EmptyState({ icon: Icon, title, description, mode, meta, action, compact }: EmptyStateProps) {
  return (
    <div
      className={`flex flex-col items-center gap-3 rounded-lg border border-dashed border-line text-center ${
        compact ? "px-4 py-6" : "px-6 py-16"
      }`}
    >
      <Icon className="text-mute" size={compact ? 20 : 28} />
      <div className="flex items-center gap-2">
        <h2 className={`font-medium text-ink ${compact ? "text-sm" : "text-base"}`}>{title}</h2>
        {mode && <ModeBadge mode={mode} />}
      </div>
      <p className="max-w-sm text-sm text-mute">{description}</p>
      {meta && <p className="font-mono-data text-xs text-unverified">{meta}</p>}
      {action}
    </div>
  );
}
