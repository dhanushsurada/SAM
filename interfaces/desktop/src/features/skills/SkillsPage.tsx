import { FiPackage } from "react-icons/fi";
import { PageHeader } from "@/components/PageHeader";
import { StatusPill } from "@/components/StatusPill";
import { DEMO_SKILLS } from "./types";

export function SkillsPage() {
  return (
    <div className="mx-auto max-w-2xl space-y-4">
      <PageHeader
        title="Skills"
        mode="demo"
        description="Compiled skills, matched automatically during task execution — there's no manual 'run skill' capability to wire up even once an API exists, so this stays read-only by design."
      />

      <div className="space-y-2">
        {DEMO_SKILLS.map((s) => (
          <div key={s.name} className="flex items-start gap-3 rounded-md border border-line bg-surface px-3 py-3">
            <FiPackage size={16} className="mt-0.5 shrink-0 text-mute" />
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <p className="truncate font-mono-data text-sm text-ink">{s.name}</p>
                <StatusPill state={s.compiled ? "SUCCESS" : "UNVERIFIED"} label={s.compiled ? "Compiled" : "Not compiled"} />
              </div>
              <p className="mt-0.5 text-xs text-mute">{s.description}</p>
              <p className="mt-1 font-mono-data text-[11px] text-unverified">
                used {s.use_count}× {s.last_used && `· last ${new Date(s.last_used).toLocaleDateString()}`}
              </p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
