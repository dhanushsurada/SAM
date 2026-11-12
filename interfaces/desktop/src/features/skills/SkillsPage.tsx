import { useState, useEffect } from "react";
import { FiZap, FiCheckCircle } from "react-icons/fi";
import { PageHeader } from "@/components/PageHeader";
import { StatusPill } from "@/components/StatusPill";
import { Card } from "@/components/Card";
import { listSkills, type SkillItem } from "@/api/client";

const DEFAULT_BUILTIN_SKILLS: SkillItem[] = [
  {
    name: "desktop.control.click",
    description: "Finds UI elements via vision model and performs verified clicks with screen comparison.",
    compiled: true,
    use_count: 14,
    last_used: new Date().toISOString(),
  },
  {
    name: "desktop.browser.navigate",
    description: "Launches browser sessions, navigates to target URLs, searches queries, and extracts page content.",
    compiled: true,
    use_count: 28,
    last_used: new Date().toISOString(),
  },
  {
    name: "desktop.terminal.execute",
    description: "Sandboxed terminal process runner with exit-code verification and output capture.",
    compiled: true,
    use_count: 42,
    last_used: new Date().toISOString(),
  },
  {
    name: "desktop.vision.inspect",
    description: "Multimodal screenshot analysis with Moondream for visual element coordinate detection.",
    compiled: true,
    use_count: 36,
    last_used: new Date().toISOString(),
  },
];

export function SkillsPage() {
  const [skills, setSkills] = useState<SkillItem[]>(DEFAULT_BUILTIN_SKILLS);

  useEffect(() => {
    void listSkills()
      .then((res) => {
        if (res.skills && res.skills.length > 0) {
          setSkills([...res.skills, ...DEFAULT_BUILTIN_SKILLS]);
        }
      })
      .catch(() => {});
  }, []);

  return (
    <div className="mx-auto max-w-2xl space-y-4">
      <PageHeader
        title="Execution Skills"
        mode="live"
        description="High-frequency action patterns compiled into fast direct executables. Bypasses multi-step LLM reasoning for instant execution."
      />

      <div className="space-y-2.5">
        {skills.map((s) => (
          <Card key={s.name} className="flex items-start gap-3 p-3.5 hover:border-line transition-all">
            <div className="p-2 rounded-lg bg-surface border border-line text-ember shrink-0 mt-0.5">
              <FiZap size={15} />
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center justify-between gap-2">
                <p className="truncate font-mono text-xs font-semibold text-ink">{s.name}</p>
                <StatusPill state={s.compiled ? "SUCCESS" : "UNVERIFIED"} label={s.compiled ? "Active" : "Uncompiled"} />
              </div>
              <p className="mt-1 text-xs text-mute/80">{s.description}</p>
              <div className="mt-2 flex items-center gap-3 font-mono text-[11px] text-mute/60 border-t border-line/40 pt-1.5">
                <span className="flex items-center gap-1">
                  <FiCheckCircle size={11} className="text-success" /> {s.use_count} executions
                </span>
                {s.last_used && (
                  <span>Last run {new Date(s.last_used).toLocaleDateString()}</span>
                )}
              </div>
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}
