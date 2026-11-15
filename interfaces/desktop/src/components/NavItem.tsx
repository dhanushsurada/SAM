import { NavLink } from "react-router-dom";
import type { SamIcon } from "@/app/routes";

export interface NavItemProps {
  to: string;
  label: string;
  icon: SamIcon;
  end?: boolean;
  onNavigate?: () => void;
}

export function NavItem({ to, label, icon: Icon, end, onNavigate }: NavItemProps) {
  return (
    <NavLink
      to={to}
      end={end}
      onClick={onNavigate}
      className={({ isActive }: { isActive: boolean }) =>
        `group relative flex items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-xs font-medium transition-all duration-150 ${
          isActive
            ? "bg-ember/12 text-ink shadow-sm border border-ember/30"
            : "text-mute hover:bg-surface/70 hover:text-ink hover:border-line/40 border border-transparent"
        }`
      }
    >
      {({ isActive }) => (
        <>
          {isActive && (
            <span className="absolute -left-1 top-1.5 bottom-1.5 w-1 rounded-r-full bg-ember shadow-[0_0_8px_rgb(var(--sam-ember)/0.7)]" />
          )}
          <Icon
            size={15}
            className={`shrink-0 transition-colors ${
              isActive ? "text-ember font-semibold" : "text-mute/80 group-hover:text-ink"
            }`}
          />
          <span className="truncate">{label}</span>
        </>
      )}
    </NavLink>
  );
}
