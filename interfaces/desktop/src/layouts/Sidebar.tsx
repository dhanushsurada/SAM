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

const MAIN_GROUPS: Exclude<NavGroup, "settings">[] = ["assistant", "core", "workspaces", "understanding", "system"];

export interface SidebarProps {
  mobileOpen: boolean;
  onCloseMobile: () => void;
}

export function Sidebar({ mobileOpen, onCloseMobile }: SidebarProps) {
  const settingsRoute = ROUTES.find((r) => r.group === "settings")!;
  const { health, healthLoading, healthError } = useTaskSession();
  const pulse = gatewayPulse(health, healthLoading, healthError);

  const content = (
    <div className="flex h-full flex-col bg-void/60 backdrop-blur-xl">
      <div className="flex items-center justify-between px-4 pt-4 pb-3 border-b border-line/40">
        <div className="flex items-center gap-2.5">
          <div className="relative flex h-7 w-7 items-center justify-center rounded-lg bg-ember/15 border border-ember/30 text-ember font-bold text-xs shadow-sm">
            S
            <span className="absolute -top-0.5 -right-0.5 h-1.5 w-1.5 rounded-full bg-ember" />
          </div>
          <div>
            <div className="flex items-center gap-1.5">
              <span className="text-sm font-semibold tracking-tight text-ink">SAM</span>
              <span className="rounded-md bg-surface border border-line/70 px-1.5 py-0.5 font-mono text-[9px] text-mute">2.0</span>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-1.5 rounded-full border border-line/60 bg-surface/80 px-2 py-0.5 text-[11px]" title={pulse.label}>
          <span className={`h-1.5 w-1.5 rounded-full ${pulse.dotClass}`} />
          <span className={`text-[10px] font-medium ${pulse.textClass}`}>
            {pulse.label.replace("Gateway ", "")}
          </span>
        </div>
      </div>

      <nav className="flex-1 space-y-4 overflow-y-auto px-3 py-3">
        <NavItem to="/" end label="Command Center" icon={ROUTES[0].icon} onNavigate={onCloseMobile} />

        {MAIN_GROUPS.map((group) => {
          const items = ROUTES.filter((r) => r.group === group && r.path !== "/");
          if (items.length === 0) return null;
          return (
            <div key={group} className="space-y-1">
              <p className="px-2.5 pb-1 font-mono text-[10px] font-medium uppercase tracking-wider text-mute/60">
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

      <div className="border-t border-line/60 p-3 space-y-1">
        <NavItem to={settingsRoute.path} label={settingsRoute.label} icon={settingsRoute.icon} onNavigate={onCloseMobile} />
        <div className="flex items-center justify-between px-2.5 py-1 text-[11px] text-mute">
          <Link
            to="/onboarding"
            onClick={onCloseMobile}
            className="hover:text-ink transition-colors"
          >
            Setup Guide
          </Link>
          <span className="font-mono text-[10px] bg-surface/80 px-1.5 py-0.5 rounded border border-line/60">Local First</span>
        </div>
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
