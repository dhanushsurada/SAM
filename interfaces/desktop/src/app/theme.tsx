import { createContext, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";
import {
  type Theme,
  type ColorTemplate,
  type ColorTemplateMeta,
  COLOR_TEMPLATES,
} from "./themePresets";

export type { Theme, ColorTemplate, ColorTemplateMeta };
export { COLOR_TEMPLATES };

const THEME_STORAGE_KEY = "sam.theme";
const TEMPLATE_STORAGE_KEY = "sam.color_template";

interface ThemeContextValue {
  theme: Theme;
  colorTemplate: ColorTemplate;
  toggleTheme: () => void;
  setTheme: (t: Theme) => void;
  setColorTemplate: (tpl: ColorTemplate) => void;
  templates: ColorTemplateMeta[];
}

const ThemeContext = createContext<ThemeContextValue>({
  theme: "dark",
  colorTemplate: "obsidian",
  toggleTheme: () => {},
  setTheme: () => {},
  setColorTemplate: () => {},
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
    ["obsidian", "frost", "emerald", "amethyst", "titanium", "amber"].includes(stored)
  ) {
    return stored;
  }
  // Default to obsidian frost (minimal glass, zero orange)
  return "obsidian";
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(getInitialTheme);
  const [colorTemplate, setColorTemplateState] = useState<ColorTemplate>(getInitialColorTemplate);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    window.localStorage.setItem(THEME_STORAGE_KEY, theme);
  }, [theme]);

  useEffect(() => {
    document.documentElement.dataset.colorTemplate = colorTemplate;
    window.localStorage.setItem(TEMPLATE_STORAGE_KEY, colorTemplate);
  }, [colorTemplate]);

  const setTheme = (t: Theme) => setThemeState(t);
  const toggleTheme = () => setThemeState((prev) => (prev === "dark" ? "light" : "dark"));
  const setColorTemplate = (tpl: ColorTemplate) => setColorTemplateState(tpl);

  return (
    <ThemeContext.Provider
      value={{
        theme,
        colorTemplate,
        toggleTheme,
        setTheme,
        setColorTemplate,
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
