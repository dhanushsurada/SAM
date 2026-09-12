import { Link } from "react-router-dom";
import { GROUP_LABELS, ROUTES, type NavGroup } from "@/app/routes";
import { NavItem } from "@/components/NavItem";

const MAIN_GROUPS: Exclude<NavGroup, "settings">[] = ["assistant", "iqoo", "understanding", "system"];

export interface SidebarProps {
  mobileOpen: boolean;
  onCloseMobile: () => void;
}

export function Sidebar({ mobileOpen, onCloseMobile }: SidebarProps) {
  const settingsRoute = ROUTES.find((r) => r.group === "settings")!;

  const content = (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2 px-4 py-4">
        <span className="h-2 w-2 rounded-full bg-ember" aria-hidden="true" />
        <span className="text-sm font-semibold tracking-wide text-ink">SAM</span>
        <span className="font-mono-data text-[10px] text-mute">local</span>
      </div>

      {/* A live system-status pulse belongs here (per PHASE5_PLAN.md §E) —
          deliberately not added yet. It needs the typed API client from §H
          step 3; a placeholder number here would be exactly the kind of
          fake-looking data the brief says never to show. */}

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
