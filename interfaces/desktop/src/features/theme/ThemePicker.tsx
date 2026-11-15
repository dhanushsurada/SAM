import { useState, type ChangeEvent, type FormEvent } from "react";
import { FiCheck, FiMoon, FiSun, FiDroplet } from "react-icons/fi";
import { useTheme } from "@/app/theme";
import { QUICK_CUSTOM_SWATCHES } from "@/app/themePresets";

interface ThemePickerProps {
  compact?: boolean;
}

export function ThemePicker({ compact = false }: ThemePickerProps) {
  const {
    theme,
    setTheme,
    colorTemplate,
    setColorTemplate,
    customColor,
    setCustomColor,
    templates,
  } = useTheme();

  const [hexInput, setHexInput] = useState(customColor);
  const [hexError, setHexError] = useState(false);

  const handleCustomHexSubmit = (e: FormEvent) => {
    e.preventDefault();
    let val = hexInput.trim();
    if (!val.startsWith("#")) val = `#${val}`;
    if (/^#[0-9A-Fa-f]{6}$/.test(val) || /^#[0-9A-Fa-f]{3}$/.test(val)) {
      setHexError(false);
      setCustomColor(val);
    } else {
      setHexError(true);
    }
  };

  const handleNativeColorChange = (e: ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value;
    setHexInput(val);
    setHexError(false);
    setCustomColor(val);
  };

  return (
    <div className="space-y-5">
      {/* Mode Segmented Controls */}
      <div className="rounded-xl border border-line/70 bg-surface/60 p-3 backdrop-blur-md shadow-sm">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <span className="text-xs font-semibold uppercase tracking-wider text-mute block">
              Display Canvas Mode
            </span>
            <p className="text-xs text-mute/90 mt-0.5">
              {theme === "light"
                ? "Daytime mode with enhanced layered porcelain glass and vibrant accents."
                : "Midnight mode with deep obsidian surfaces and ambient frosted lighting."}
            </p>
          </div>
          <div className="flex items-center gap-1.5 rounded-lg border border-line bg-void/60 p-1 shrink-0">
            <button
              type="button"
              onClick={() => setTheme("light")}
              className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-all ${
                theme === "light"
                  ? "bg-surface text-ink shadow-sm border border-line"
                  : "text-mute hover:text-ink"
              }`}
            >
              <FiSun size={13} className={theme === "light" ? "text-amber-500" : ""} />
              Daytime
            </button>
            <button
              type="button"
              onClick={() => setTheme("dark")}
              className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-all ${
                theme === "dark"
                  ? "bg-surface text-ink shadow-sm border border-line"
                  : "text-mute hover:text-ink"
              }`}
            >
              <FiMoon size={13} className={theme === "dark" ? "text-sky-400" : ""} />
              Midnight
            </button>
          </div>
        </div>
      </div>

      {/* Curated Presets */}
      <div className="space-y-2.5">
        <div className="flex items-center justify-between">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-mute">
            Curated Color Templates
          </h3>
          <span className="text-[11px] text-mute font-mono">
            Active: <span className="text-ink font-semibold capitalize">{colorTemplate}</span>
          </span>
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
            const currentAccent = theme === "light" ? tpl.lightAccentHex : tpl.accentHex;

            return (
              <button
                key={tpl.id}
                type="button"
                onClick={() => setColorTemplate(tpl.id)}
                className={`group relative flex flex-col text-left rounded-xl p-3 border transition-all cursor-pointer ${
                  isSelected
                    ? "border-ember bg-surface shadow-md ring-1 ring-ember/40"
                    : "border-line/70 bg-surface/50 hover:border-line hover:bg-surface/80"
                }`}
              >
                <div className="flex items-center justify-between w-full mb-1">
                  <div className="flex items-center gap-2">
                    <span
                      className="h-3.5 w-3.5 rounded-full border border-white/20 shadow-sm"
                      style={{ backgroundColor: currentAccent }}
                    />
                    <span className="text-xs font-semibold text-ink group-hover:text-ember-text transition-colors">
                      {tpl.name}
                    </span>
                  </div>
                  {isSelected && (
                    <span className="flex h-4 w-4 items-center justify-center rounded-full bg-ember text-ember-ink text-[10px] shadow-sm">
                      <FiCheck size={10} />
                    </span>
                  )}
                </div>
                <p className="text-[11px] text-mute line-clamp-1">{tpl.tagline}</p>

                {/* Color preview ribbon */}
                <div className="mt-2.5 flex h-1.5 w-full overflow-hidden rounded-full bg-void/80 border border-line/40">
                  <div
                    className="h-full w-2/5 transition-all"
                    style={{ backgroundColor: currentAccent }}
                  />
                  <div className="h-full w-3/5 bg-line/50" />
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* Custom Color Palette & Wheel Picker */}
      <div className="rounded-xl border border-line/70 bg-surface/60 p-3.5 backdrop-blur-md space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <FiDroplet size={14} className="text-ember" />
            <h4 className="text-xs font-semibold uppercase tracking-wider text-ink">
              Custom Color Palette
            </h4>
          </div>
          {colorTemplate === "custom" && (
            <span className="flex items-center gap-1 rounded-full bg-ember/15 px-2 py-0.5 text-[10px] font-mono text-ember-text border border-ember/30">
              <span className="h-1.5 w-1.5 rounded-full bg-ember" />
              Custom Active
            </span>
          )}
        </div>

        <p className="text-xs text-mute">
          Select any quick shade or use the color wheel to personalize SAM with your favorite color.
        </p>

        {/* Quick Custom Swatches */}
        <div className="flex flex-wrap items-center gap-2 pt-1">
          {QUICK_CUSTOM_SWATCHES.map((swatch) => {
            const isMatch = colorTemplate === "custom" && customColor.toLowerCase() === swatch.hex.toLowerCase();
            return (
              <button
                key={swatch.hex}
                type="button"
                onClick={() => {
                  setHexInput(swatch.hex);
                  setCustomColor(swatch.hex);
                }}
                className={`relative flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs transition-all cursor-pointer ${
                  isMatch
                    ? "border-ember bg-surface text-ink font-semibold shadow-sm ring-1 ring-ember/40"
                    : "border-line bg-void/70 text-mute hover:text-ink hover:border-line/80 hover:bg-surface/60"
                }`}
                title={swatch.name}
              >
                <span
                  className="h-2.5 w-2.5 rounded-full shadow-sm"
                  style={{ backgroundColor: swatch.hex }}
                />
                <span>{swatch.name}</span>
                {isMatch && <FiCheck size={11} className="text-ember ml-0.5" />}
              </button>
            );
          })}
        </div>

        {/* Color Wheel & Hex Input */}
        <form onSubmit={handleCustomHexSubmit} className="flex flex-wrap items-center gap-2.5 pt-2 border-t border-line/50">
          <div className="flex items-center gap-2">
            <label
              className="relative flex h-8 w-8 shrink-0 cursor-pointer items-center justify-center rounded-lg border border-line shadow-sm overflow-hidden hover:scale-105 transition-transform"
              title="Open Color Wheel"
            >
              <input
                type="color"
                value={customColor}
                onChange={handleNativeColorChange}
                className="absolute -inset-2 h-12 w-12 cursor-pointer opacity-0"
              />
              <span
                className="h-full w-full"
                style={{ backgroundColor: customColor }}
              />
            </label>
            <span className="text-xs text-mute">Wheel</span>
          </div>

          <div className="flex items-center gap-1.5 flex-1 min-w-[160px]">
            <input
              type="text"
              value={hexInput}
              onChange={(e) => setHexInput(e.target.value)}
              placeholder="#3B82F6"
              maxLength={7}
              className={`w-28 rounded-lg border bg-void px-2.5 py-1 text-xs font-mono text-ink placeholder:text-mute focus:outline-none ${
                hexError ? "border-danger ring-1 ring-danger/30" : "border-line focus:border-ember"
              }`}
            />
            <button
              type="submit"
              className="rounded-lg border border-line bg-surface/80 px-3 py-1 text-xs font-medium text-ink hover:border-ember/50 hover:bg-surface transition-all shadow-sm active:scale-95"
            >
              Apply Color
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
