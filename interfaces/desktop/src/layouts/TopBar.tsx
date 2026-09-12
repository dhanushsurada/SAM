import { useLocation } from "react-router-dom";
import { FiMenu, FiSun, FiMoon } from "react-icons/fi";
import { findRoute } from "@/app/routes";
import { useTheme } from "@/app/theme";
import { Button } from "@/components/Button";

export function TopBar({ onOpenMobileNav }: { onOpenMobileNav: () => void }) {
  const location = useLocation();
  const { theme, toggleTheme } = useTheme();
  const route = findRoute(location.pathname);

  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-line bg-void px-4 sm:px-6">
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={onOpenMobileNav}
          className="rounded-md p-1.5 text-mute hover:bg-surface hover:text-ink md:hidden"
          aria-label="Open navigation"
        >
          <FiMenu size={18} />
        </button>
        <h1 className="text-sm font-medium text-ink">{route?.label ?? "SAM"}</h1>
      </div>

      <Button
        variant="ghost"
        size="sm"
        onClick={toggleTheme}
        aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
      >
        {theme === "dark" ? <FiSun size={16} /> : <FiMoon size={16} />}
      </Button>
    </header>
  );
}
