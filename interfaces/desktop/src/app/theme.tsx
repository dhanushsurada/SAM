import { createContext, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";
import {
  type Theme,
  type ColorTemplate,
  type ColorTemplateMeta,
  COLOR_TEMPLATES,
  hexToRgb,
  rgbToTriplet,
  getContrastInk,
} from "./themePresets";

export type { Theme, ColorTemplate, ColorTemplateMeta };
export { COLOR_TEMPLATES };

const THEME_STORAGE_KEY = "sam.theme";
const TEMPLATE_STORAGE_KEY = "sam.color_template";
const CUSTOM_COLOR_STORAGE_KEY = "sam.custom_color";

const DEFAULT_CUSTOM_COLOR = "#3B82F6"; // Electric Sapphire Blue

interface ThemeContextValue {
  theme: Theme;
  colorTemplate: ColorTemplate;
  customColor: string;
  toggleTheme: () => void;
  setTheme: (t: Theme) => void;
  setColorTemplate: (tpl: ColorTemplate) => void;
  setCustomColor: (hex: string) => void;
  templates: ColorTemplateMeta[];
}

const ThemeContext = createContext<ThemeContextValue>({
  theme: "dark",
  colorTemplate: "obsidian",
  customColor: DEFAULT_CUSTOM_COLOR,
  toggleTheme: () => {},
  setTheme: () => {},
  setColorTemplate: () => {},
  setCustomColor: () => {},
  templates: COLOR_TEMPLATES,
});

function getInitialTheme(): Theme {
  if (typeof window === "undefined") return "dark";
  const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
  if (stored === "dark" || stored === "light") return stored;
  return window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
}

function getInitialColorTemplate(): ColorTemplate {
  if (typeof window === "undefined") return "obsidian";
  const stored = window.localStorage.getItem(TEMPLATE_STORAGE_KEY) as ColorTemplate | null;
  if (
    stored &&
    ["obsidian", "frost", "emerald", "amethyst", "coral", "titanium", "amber", "custom"].includes(stored)
  ) {
    return stored;
  }
  return "obsidian";
}

function getInitialCustomColor(): string {
  if (typeof window === "undefined") return DEFAULT_CUSTOM_COLOR;
  const stored = window.localStorage.getItem(CUSTOM_COLOR_STORAGE_KEY);
  return stored && /^#[0-9A-Fa-f]{3,6}$/.test(stored) ? stored : DEFAULT_CUSTOM_COLOR;
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(getInitialTheme);
  const [colorTemplate, setColorTemplateState] = useState<ColorTemplate>(getInitialColorTemplate);
  const [customColor, setCustomColorState] = useState<string>(getInitialCustomColor);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    window.localStorage.setItem(THEME_STORAGE_KEY, theme);

    if (typeof window !== "undefined" && "__TAURI_INTERNALS__" in window) {
      import("@tauri-apps/api/core")
        .then(({ invoke }) => {
          invoke("sync_theme_icon", { themeName: theme }).catch(() => {});
        })
        .catch(() => {});
    }
  }, [theme]);

  // Listen to OS system appearance changes (dark/light mode)
  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const handler = (e: MediaQueryListEvent) => {
      const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
      if (!stored) {
        setThemeState(e.matches ? "dark" : "light");
      }
    };
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, []);

  useEffect(() => {
    document.documentElement.dataset.colorTemplate = colorTemplate;
    window.localStorage.setItem(TEMPLATE_STORAGE_KEY, colorTemplate);

    if (colorTemplate === "custom") {
      const rgb = hexToRgb(customColor);
      if (rgb) {
        const triplet = rgbToTriplet(rgb.r, rgb.g, rgb.b);
        const ink = getContrastInk(rgb.r, rgb.g, rgb.b);
        document.documentElement.style.setProperty("--sam-ember", triplet);
        document.documentElement.style.setProperty("--sam-ember-ink", ink);
        document.documentElement.style.setProperty("--sam-ember-text", triplet);
      }
    } else {
      // Clear manual style properties so CSS template rules apply
      document.documentElement.style.removeProperty("--sam-ember");
      document.documentElement.style.removeProperty("--sam-ember-ink");
      document.documentElement.style.removeProperty("--sam-ember-text");
    }
  }, [colorTemplate, customColor, theme]);

  const setTheme = (t: Theme) => setThemeState(t);
  const toggleTheme = () => setThemeState((prev) => (prev === "dark" ? "light" : "dark"));

  const setColorTemplate = (tpl: ColorTemplate) => {
    setColorTemplateState(tpl);
  };

  const setCustomColor = (hex: string) => {
    setCustomColorState(hex);
    setColorTemplateState("custom");
    try {
      window.localStorage.setItem(CUSTOM_COLOR_STORAGE_KEY, hex);
    } catch {
      // ignore
    }
  };

  return (
    <ThemeContext.Provider
      value={{
        theme,
        colorTemplate,
        customColor,
        toggleTheme,
        setTheme,
        setColorTemplate,
        setCustomColor,
        templates: COLOR_TEMPLATES,
      }}
    >
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  return useContext(ThemeContext);
}
