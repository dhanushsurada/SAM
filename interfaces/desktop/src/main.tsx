import { createRoot } from "react-dom/client";
import { App } from "./App";
import { QuickAssistantApp } from "./features/quick-assistant/QuickAssistantApp";
import { currentWindowLabel } from "./lib/native";
import "@fontsource/ibm-plex-sans/400.css";
import "@fontsource/ibm-plex-sans/500.css";
import "@fontsource/ibm-plex-sans/600.css";
import "@fontsource/ibm-plex-sans/700.css";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/500.css";
import "@fontsource/ibm-plex-mono/600.css";
import "./styles/globals.css";

function getRootContainer(): HTMLElement {
  let el = document.getElementById("root");
  if (!el) {
    el = document.createElement("div");
    el.id = "root";
    document.body.appendChild(el);
  }
  return el;
}

function renderApp(label: string) {
  const container = getRootContainer();
  const tree = label === "quick-assistant" ? <QuickAssistantApp /> : <App />;
  createRoot(container).render(tree);
}

function start() {
  currentWindowLabel()
    .then(renderApp)
    .catch((err) => {
      console.error("SAM failed to resolve window label, rendering main application:", err);
      renderApp("main");
    });
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", start);
} else {
  start();
}
