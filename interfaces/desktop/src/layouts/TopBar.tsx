import { useLocation, Link } from "react-router-dom";
import { FiMenu, FiSun, FiMoon, FiCpu, FiTerminal } from "react-icons/fi";
import { findRoute } from "@/app/routes";
import { useTheme } from "@/app/theme";
import { Button } from "@/components/Button";
import { VoiceTopBarIndicator } from "@/features/voice/VoiceControls";
import { TopBarProfile } from "@/features/profile/TopBarProfile";
import { useProfile } from "@/features/profile/ProfileContext";

export function TopBar({ onOpenMobileNav }: { onOpenMobileNav: () => void }) {
  const location = useLocation();
  const { theme, toggleTheme, colorTemplate } = useTheme();
  const { openProfileModal } = useProfile();
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

      <div className="flex items-center gap-2">
        <Link
          to="/brain"
          className="hidden sm:flex items-center gap-1.5 rounded-full border border-line/60 bg-surface/60 px-2.5 py-1 text-xs text-mute hover:text-ink hover:border-ember/40 transition-all"
          title="Brain & Model Settings"
        >
          <FiCpu size={12} className="text-ember" />
          <span className="font-mono text-[10px]">Brain Engine</span>
        </Link>
        <VoiceTopBarIndicator />

        {/* Quick Color Presets / Appearance Button */}
        <button
          type="button"
          onClick={() => openProfileModal("appearance")}
          aria-label="Color Template & Appearance"
          title={`Appearance: ${colorTemplate}`}
          className="flex items-center justify-center rounded-lg h-8 w-8 border border-line/60 bg-surface/60 text-mute hover:text-ink hover:border-ember/60 hover:bg-surface transition-all shadow-sm"
        >
          <span
            className="h-3.5 w-3.5 rounded-full border border-white/30 shadow-[0_0_8px_rgb(var(--sam-ember)/0.6)]"
            style={{ backgroundColor: "rgb(var(--sam-ember))" }}
          />
        </button>

        {/* Light / Dark Toggle */}
        <Button
          variant="ghost"
          size="sm"
          onClick={toggleTheme}
          aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
          className="rounded-lg h-8 w-8 p-0"
        >
          {theme === "dark" ? <FiSun size={15} /> : <FiMoon size={15} />}
        </Button>

        {/* User Profile Avatar Pill */}
        <div className="pl-1 border-l border-line/40">
          <TopBarProfile />
        </div>
      </div>
    </header>
  );
}
