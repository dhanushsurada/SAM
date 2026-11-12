import { useLocation, Link } from "react-router-dom";
import { FiMenu, FiSun, FiMoon, FiCpu, FiTerminal } from "react-icons/fi";
import { findRoute } from "@/app/routes";
import { useTheme } from "@/app/theme";
import { Button } from "@/components/Button";
import { VoiceTopBarIndicator } from "@/features/voice/VoiceControls";

export function TopBar({ onOpenMobileNav }: { onOpenMobileNav: () => void }) {
  const location = useLocation();
  const { theme, toggleTheme } = useTheme();
  const route = findRoute(location.pathname);
  const Icon = route?.icon || FiTerminal;

  return (
    <header className="sticky top-0 z-30 flex h-14 shrink-0 items-center justify-between border-b border-line/50 bg-void/80 px-4 backdrop-blur-xl sm:px-6">
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={onOpenMobileNav}
          className="rounded-lg p-1.5 text-mute hover:bg-surface hover:text-ink md:hidden transition-colors"
          aria-label="Open navigation"
        >
          <FiMenu size={18} />
        </button>
        <div className="flex items-center gap-2">
          <Icon size={15} className="text-ember shrink-0" />
          <h1 className="text-sm font-semibold tracking-tight text-ink">{route?.label ?? "SAM"}</h1>
        </div>
      </div>

      <div className="flex items-center gap-2.5">
        <Link
          to="/brain"
          className="hidden sm:flex items-center gap-1.5 rounded-full border border-line/60 bg-surface/60 px-2.5 py-1 text-xs text-mute hover:text-ink hover:border-ember/40 transition-all"
          title="Brain & Model Settings"
        >
          <FiCpu size={12} className="text-ember" />
          <span className="font-mono text-[10px]">Brain Engine</span>
        </Link>
        <VoiceTopBarIndicator />
        <Button
          variant="ghost"
          size="sm"
          onClick={toggleTheme}
          aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
          className="rounded-lg h-8 w-8 p-0"
        >
          {theme === "dark" ? <FiSun size={15} /> : <FiMoon size={15} />}
        </Button>
      </div>
    </header>
  );
}
