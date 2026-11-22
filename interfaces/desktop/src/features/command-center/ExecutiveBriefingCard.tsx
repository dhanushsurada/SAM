import { useState, useEffect } from "react";
import { FiSun, FiCheckSquare, FiCalendar, FiMail, FiClock, FiPlay } from "react-icons/fi";
import { Card } from "@/components/Card";
import { ModeBadge } from "@/components/ModeBadge";

interface BriefingData {
  greeting: string;
  date: string;
  events: Array<{ title: string; start: string; is_virtual: boolean }>;
  urgent_emails: Array<{ subject: string; sender: string; is_urgent: boolean }>;
  notes_tasks: string[];
  recommendations: string[];
  next_meeting_prep?: string;
  spoken_summary?: string;
}

export function ExecutiveBriefingCard({ onRunTask }: { onRunTask?: (prompt: string) => void }) {
  const [activeTab, setActiveTab] = useState<"briefing" | "plate">("briefing");
  const [briefing, setBriefing] = useState<BriefingData | null>(null);

  useEffect(() => {
    let mounted = true;
    async function loadBriefing() {
      try {
        const res = await fetch("http://127.0.0.1:8420/api/briefing");
        if (res.ok) {
          const data = await res.json();
          if (mounted) setBriefing(data);
        }
      } catch {
        // Fallback demo state if local API is not running
        if (mounted) {
          setBriefing({
            greeting: "Good morning! Here is your executive briefing.",
            date: new Date().toLocaleDateString("en-US", { weekday: "long", month: "short", day: "numeric" }),
            events: [
              { title: "Sprint Sync & Demo", start: "10:00 AM", is_virtual: true },
              { title: "Architecture Alignment", start: "2:30 PM", is_virtual: false },
            ],
            urgent_emails: [
              { subject: "Review Q4 Infrastructure Plan", sender: "Lead Architect", is_urgent: true },
            ],
            notes_tasks: [
              "Finalize JEV voice reflex integration",
              "Review notes vault auto-sync",
            ],
            recommendations: [
              "Focus block: 11:00 AM - 1:30 PM recommended for deep work",
            ],
            next_meeting_prep: "First session: Sprint Sync at 10:00 AM. Zoom link ready.",
          });
        }
      }
    }
    loadBriefing();
    return () => { mounted = false; };
  }, []);

  return (
    <Card className="space-y-3.5 border-line/80 bg-surface/90 backdrop-blur-sm shadow-sm transition-all">
      {/* Header Bar */}
      <div className="flex items-center justify-between border-b border-line/40 pb-2.5">
        <div className="flex items-center gap-2">
          <div className="flex h-6 w-6 items-center justify-center rounded-md bg-amber-500/10 text-amber-500">
            <FiSun size={13} />
          </div>
          <div>
            <h2 className="text-xs font-semibold tracking-wide text-ink uppercase">
              Executive Briefing & Daily Plate
            </h2>
            <span className="text-[10px] text-mute font-mono">
              {briefing?.date || "Today"}
            </span>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1 rounded-full border border-emerald-500/20 bg-emerald-500/10 px-2 py-0.5 text-[10px] font-mono text-emerald-500 font-medium">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
            JEV Reflex: &lt;50ms
          </div>
          <ModeBadge mode="live" />
        </div>
      </div>

      {/* Segmented Control Tabs */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1 rounded-lg bg-void/60 p-0.5 border border-line/50 text-xs">
          <button
            type="button"
            onClick={() => setActiveTab("briefing")}
            className={`flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium transition-all cursor-pointer ${
              activeTab === "briefing"
                ? "bg-surface text-ink shadow-xs"
                : "text-mute hover:text-ink"
            }`}
          >
            <FiCalendar size={11} className={activeTab === "briefing" ? "text-amber-500" : ""} />
            <span>Today's Agenda</span>
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("plate")}
            className={`flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium transition-all cursor-pointer ${
              activeTab === "plate"
                ? "bg-surface text-ink shadow-xs"
                : "text-mute hover:text-ink"
            }`}
          >
            <FiCheckSquare size={11} className={activeTab === "plate" ? "text-ember" : ""} />
            <span>On My Plate</span>
            {briefing?.notes_tasks && briefing.notes_tasks.length > 0 && (
              <span className="rounded-full bg-ember/20 px-1.5 py-0.2 text-[9px] font-bold text-ember">
                {briefing.notes_tasks.length}
              </span>
            )}
          </button>
        </div>

        {onRunTask && (
          <button
            type="button"
            onClick={() => onRunTask("Give me my executive morning briefing")}
            className="flex items-center gap-1.5 rounded-lg border border-line/60 bg-surface/80 px-2.5 py-1 text-[11px] text-mute hover:border-amber-500/40 hover:text-ink hover:bg-surface transition-all cursor-pointer active:scale-95"
            title="Trigger full voice & text morning briefing"
          >
            <FiPlay size={10} className="text-amber-500" />
            <span>Run Briefing</span>
          </button>
        )}
      </div>

      {/* Tab Content: Today's Agenda */}
      {activeTab === "briefing" && (
        <div className="space-y-2.5 pt-0.5">
          {/* Calendar Events */}
          <div className="space-y-1.5">
            <span className="text-[10px] font-mono font-medium tracking-wider text-mute/80 uppercase">
              Schedule & Meetings
            </span>
            {(!briefing?.events || briefing.events.length === 0) ? (
              <p className="text-xs text-mute/60 italic py-1">No scheduled events. Day is fully open.</p>
            ) : (
              <div className="space-y-1">
                {briefing.events.map((ev, idx) => (
                  <div
                    key={idx}
                    className="flex items-center justify-between rounded-lg border border-line/40 bg-surface/40 px-2.5 py-1.5 text-xs hover:border-line/80 transition-colors"
                  >
                    <div className="flex items-center gap-2 truncate">
                      <FiClock size={11} className="text-mute/60 shrink-0" />
                      <span className="font-mono text-[11px] text-ink/90 font-medium">{ev.start}</span>
                      <span className="truncate text-ink">{ev.title}</span>
                    </div>
                    {ev.is_virtual && (
                      <span className="rounded bg-sky-500/10 px-1.5 py-0.5 text-[9px] font-mono text-sky-500 font-medium shrink-0">
                        Virtual
                      </span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Urgent Inquiries / Mail */}
          {briefing?.urgent_emails && briefing.urgent_emails.length > 0 && (
            <div className="space-y-1.5 pt-1">
              <span className="text-[10px] font-mono font-medium tracking-wider text-mute/80 uppercase">
                Priority Inquiries
              </span>
              <div className="space-y-1">
                {briefing.urgent_emails.map((m, idx) => (
                  <div
                    key={idx}
                    className="flex items-center justify-between rounded-lg border border-line/40 bg-surface/40 px-2.5 py-1.5 text-xs"
                  >
                    <div className="flex items-center gap-2 truncate">
                      <FiMail size={11} className="text-amber-500 shrink-0" />
                      <span className="font-medium text-ink truncate">{m.sender}</span>
                      <span className="text-mute truncate">{m.subject}</span>
                    </div>
                    {m.is_urgent && (
                      <span className="rounded bg-rose-500/10 px-1.5 py-0.5 text-[9px] font-mono text-rose-500 font-bold shrink-0">
                        Urgent
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Proactive Optimization Banner */}
          {briefing?.next_meeting_prep && (
            <div className="flex items-center gap-2 rounded-lg border border-amber-500/20 bg-amber-500/5 px-2.5 py-1.5 text-[11px] text-ink/90">
              <FiSun size={12} className="text-amber-500 shrink-0" />
              <span className="truncate">{briefing.next_meeting_prep}</span>
            </div>
          )}
        </div>
      )}

      {/* Tab Content: On My Plate (Notes Vault) */}
      {activeTab === "plate" && (
        <div className="space-y-2 pt-0.5">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-mono font-medium tracking-wider text-mute/80 uppercase">
              Active Notes Tasks & Priorities
            </span>
            <span className="text-[10px] text-mute/70 font-mono">Synced from Daily Vault</span>
          </div>

          {(!briefing?.notes_tasks || briefing.notes_tasks.length === 0) ? (
            <p className="text-xs text-mute/60 italic py-2">
              All tasks completed! Your notes vault has no pending checklist items for today.
            </p>
          ) : (
            <div className="space-y-1.5">
              {briefing.notes_tasks.map((task, idx) => (
                <div
                  key={idx}
                  className="flex items-start gap-2.5 rounded-lg border border-line/40 bg-surface/40 p-2 text-xs hover:border-line/80 transition-colors"
                >
                  <input
                    type="checkbox"
                    className="mt-0.5 rounded border-line text-ember focus:ring-0 cursor-pointer"
                    readOnly
                  />
                  <span className="text-ink leading-relaxed">{task}</span>
                </div>
              ))}
            </div>
          )}

          {briefing?.recommendations && briefing.recommendations.length > 0 && (
            <div className="rounded-lg border border-line/40 bg-void/30 p-2 text-[11px] text-mute">
              <span className="font-semibold text-ink">💡 Focus Recommendation: </span>
              {briefing.recommendations[0]}
            </div>
          )}
        </div>
      )}
    </Card>
  );
}
