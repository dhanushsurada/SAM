import { Link } from "react-router-dom";
import { GROUP_LABELS, ROUTES, type NavGroup } from "@/app/routes";
import { NavItem } from "@/components/NavItem";
import { useTaskSession } from "@/stores/taskSession";
import type { HealthStatus } from "@/api/types";

type PulseVisual = { dotClass: string; textClass: string; label: string };

/** Derives the sidebar's gateway indicator from the same polled health data
 * IqooPage/HealthPanel already use (via useTaskSession) — no second fetch.
 * Only the dot is colored for the healthy case, not the text: status
 * colors here are functional, meant to draw the eye toward a problem, not
 * to celebrate the default "everything's fine" state everywhere at once. */
function gatewayPulse(health: HealthStatus | null, loading: boolean, error: string | null): PulseVisual {
  if (error) return { dotClass: "bg-danger", textClass: "text-danger", label: "Gateway unreachable" };
  if (!health) {
    return { dotClass: "bg-unverified", textClass: "text-mute", label: loading ? "Checking gateway…" : "Gateway status unknown" };
  }
  if (health.worker_alive && health.brain_reachable) {
    return { dotClass: "bg-success", textClass: "text-mute", label: "Gateway online" };
  }
  return { dotClass: "bg-warn", textClass: "text-warn", label: "Gateway degraded" };
}

const MAIN_GROUPS: Exclude<NavGroup, "settings">[] = ["assistant", "iqoo", "understanding", "system"];

export interface SidebarProps {
  mobileOpen: boolean;
  onCloseMobile: () => void;
}

export function Sidebar({ mobileOpen, onCloseMobile }: SidebarProps) {
  const settingsRoute = ROUTES.find((r) => r.group === "settings")!;
  const { health, healthLoading, healthError } = useTaskSession();
  const pulse = gatewayPulse(health, healthLoading, healthError);

  const content = (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2 px-4 py-4">
        <span className="h-2 w-2 rounded-full bg-ember" aria-hidden="true" />
        <span className="text-sm font-semibold tracking-wide text-ink">SAM</span>
        <span className="font-mono-data text-[10px] text-mute">local</span>
      </div>

      {/* Live system-status pulse (PHASE5_PLAN.md §E) — was deferred pending
          the typed API client from §H step 3, which now exists; reusing its
          shared poll here rather than fetching again. Steady, not animated:
          only "actively in progress" states pulse elsewhere (StatusPill) —
          an idle health readout animating forever would be exactly the
          decorative motion the brief says to avoid. */}
      <div className="flex items-center gap-2 px-4 pb-3 text-xs">
        <span className={`h-1.5 w-1.5 rounded-full ${pulse.dotClass}`} aria-hidden="true" />
        <span className={pulse.textClass}>{pulse.label}</span>
      </div>

      <nav className="flex-1 space-y-5 overflow-y-auto px-3 py-2">
        <NavItem to="/" end label="Command Center" icon={ROUTES[0].icon} onNavigate={onCloseMobile} />

        {MAIN_GROUPS.map((group) => {
          const items = ROUTES.filter((r) => r.group === group && r.path !== "/");
          if (items.length === 0) return null;
          return (
            <div key={group}>
              <p className="px-2.5 pb-1.5 font-mono-data text-[10px] uppercase tracking-wider text-mute/70">
                {GROUP_LABELS[group]}
              </p>
              <div className="space-y-0.5">
                {items.map((r) => (
                  <NavItem key={r.path} to={r.path} label={r.label} icon={r.icon} onNavigate={onCloseMobile} />
                ))}
              </div>
            </div>
          );
        })}
      </nav>

      <div className="border-t border-line px-3 py-3 space-y-0.5">
        <NavItem to={settingsRoute.path} label={settingsRoute.label} icon={settingsRoute.icon} onNavigate={onCloseMobile} />
        <Link
          to="/onboarding"
          onClick={onCloseMobile}
          className="block px-2.5 py-1.5 text-xs text-mute hover:text-ink"
        >
          Setup guide
        </Link>
      </div>
    </div>
  );

  return (
    <>
      {/* Desktop: static column, always visible at md and up. */}
      <aside className="hidden md:flex md:w-60 md:shrink-0 md:flex-col md:border-r md:border-line md:bg-void">
        {content}
      </aside>

      {/* Mobile: slide-in drawer + backdrop, md:hidden. Not a shrunk desktop
          layout — a distinct treatment, per the brief's explicit requirement. */}
      <div className="md:hidden">
        <div
          onClick={onCloseMobile}
          aria-hidden="true"
          className={`fixed inset-0 z-40 bg-black/50 transition-opacity duration-[var(--sam-motion-state)] ${
            mobileOpen ? "opacity-100" : "pointer-events-none opacity-0"
          }`}
        />
        <aside
          className={`fixed inset-y-0 left-0 z-50 w-64 border-r border-line bg-void transition-transform duration-[var(--sam-motion-state)] ${
            mobileOpen ? "translate-x-0" : "-translate-x-full"
          }`}
          aria-hidden={!mobileOpen}
        >
          {content}
        </aside>
      </div>
    </>
  );
}
