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
        `flex items-center gap-2.5 rounded-md px-2.5 py-2 text-sm transition-colors duration-[var(--sam-motion-fast)] ${
          isActive
            ? "bg-ember/10 text-ember-text font-medium"
            : "text-mute hover:bg-surface hover:text-ink"
        }`
      }
    >
      <Icon size={16} className="shrink-0" />
      <span className="truncate">{label}</span>
    </NavLink>
  );
}
