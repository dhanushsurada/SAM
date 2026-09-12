import type { Config } from "tailwindcss";

// Colors resolve through CSS variables (src/styles/tokens.css) rather than
// fixed hexes here, so the light/dark swap is one attribute flip on <html>
// and every utility class stays correct in both themes.
export default {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        void: "rgb(var(--sam-void) / <alpha-value>)",
        surface: "rgb(var(--sam-surface) / <alpha-value>)",
        line: "rgb(var(--sam-line) / <alpha-value>)",
        ink: "rgb(var(--sam-ink) / <alpha-value>)",
        mute: "rgb(var(--sam-mute) / <alpha-value>)",
        ember: "rgb(var(--sam-ember) / <alpha-value>)",
        "ember-ink": "rgb(var(--sam-ember-ink) / <alpha-value>)",
        "ember-text": "rgb(var(--sam-ember-text) / <alpha-value>)",
        success: "rgb(var(--sam-success) / <alpha-value>)",
        warn: "rgb(var(--sam-warn) / <alpha-value>)",
        danger: "rgb(var(--sam-danger) / <alpha-value>)",
        unverified: "rgb(var(--sam-unverified) / <alpha-value>)",
      },
      fontFamily: {
        sans: ["IBM Plex Sans", "system-ui", "sans-serif"],
        mono: ["IBM Plex Mono", "ui-monospace", "monospace"],
      },
      borderRadius: {
        sm: "6px",
        md: "10px",
        lg: "14px",
      },
      boxShadow: {
        panel: "0 1px 2px rgb(0 0 0 / 0.16), 0 0 0 1px rgb(var(--sam-line) / 0.6)",
      },
    },
  },
  plugins: [],
} satisfies Config;
