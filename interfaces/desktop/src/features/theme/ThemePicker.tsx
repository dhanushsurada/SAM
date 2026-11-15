import { FiCheck, FiMoon, FiSun } from "react-icons/fi";
import { useTheme } from "@/app/theme";

interface ThemePickerProps {
  compact?: boolean;
}

export function ThemePicker({ compact = false }: ThemePickerProps) {
  const { theme, toggleTheme, colorTemplate, setColorTemplate, templates } = useTheme();

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-xs font-semibold uppercase tracking-wider text-mute">
            Appearance & Minimal Presets
          </h3>
          <p className="text-xs text-mute/80 mt-0.5">
            Select a minimal translucent glass theme. Zero orange branding.
          </p>
        </div>
        <button
          type="button"
          onClick={toggleTheme}
          className="flex items-center gap-1.5 rounded-lg border border-line bg-surface/70 px-2.5 py-1 text-xs text-ink hover:border-ember/40 hover:bg-surface transition-all"
          title={`Switch to ${theme === "dark" ? "Light" : "Dark"} mode`}
        >
          {theme === "dark" ? <FiSun size={13} className="text-warn" /> : <FiMoon size={13} />}
          <span className="capitalize">{theme}</span>
        </button>
      </div>

      <div
        className={
          compact
            ? "grid grid-cols-2 gap-2"
            : "grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2.5"
        }
      >
        {templates.map((tpl) => {
          const isSelected = colorTemplate === tpl.id;
          return (
            <button
              key={tpl.id}
              type="button"
              onClick={() => setColorTemplate(tpl.id)}
              className={`group relative flex flex-col text-left rounded-xl p-3 border transition-all cursor-pointer ${
                isSelected
                  ? "border-ember/70 bg-surface/90 shadow-md ring-1 ring-ember/30"
                  : "border-line/60 bg-surface/40 hover:border-line hover:bg-surface/70"
              }`}
            >
              <div className="flex items-center justify-between w-full mb-1.5">
                <div className="flex items-center gap-2">
                  <span
                    className={`h-3.5 w-3.5 rounded-full border border-white/20 shadow-sm ${tpl.dotClass}`}
                  />
                  <span className="text-xs font-medium text-ink group-hover:text-ember-text transition-colors">
                    {tpl.name}
                  </span>
                </div>
                {isSelected && (
                  <span className="flex h-4 w-4 items-center justify-center rounded-full bg-ember text-ember-ink text-[10px]">
                    <FiCheck size={10} />
                  </span>
                )}
              </div>
              <p className="text-[11px] text-mute line-clamp-1">{tpl.tagline}</p>

              {/* Minimal preview strip */}
              <div className="mt-2.5 flex h-1.5 w-full overflow-hidden rounded-full bg-void/80 border border-line/40">
                <div
                  className="h-full w-1/3 opacity-90"
                  style={{ backgroundColor: tpl.accentHex }}
                />
                <div className="h-full w-2/3 bg-line/40" />
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
