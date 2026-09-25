import { createRoot } from "react-dom/client";
import { App } from "./App";
import { QuickAssistantApp } from "./features/quick-assistant/QuickAssistantApp";
import { currentWindowLabel } from "./lib/native";
import "./styles/globals.css";

const container = document.getElementById("root");
if (!container) {
  throw new Error("Root element #root not found in index.html");
}

// Two Tauri windows load this exact same built bundle. Which tree mounts
// is decided by window *label* (read via native.ts), not by URL/route —
// that way the quick-assistant window never depends on the dev server or
// production asset server correctly resolving an arbitrary client-side
// path, which is a real SPA-hosting detail worth not assuming works. A
// plain browser tab has no Tauri window to label at all, so this always
// resolves to the ordinary app there.
currentWindowLabel().then((label) => {
  const tree = label === "quick-assistant" ? <QuickAssistantApp /> : <App />;
  createRoot(container).render(tree);
});
