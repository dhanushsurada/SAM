import type { ChatRequest, ChatResponse } from "./types";

/**
 * Every single response says plainly that it's a placeholder — not just a
 * badge elsewhere on the page. Chat output is exactly the kind of content
 * that could be mistaken for genuine reasoning if the demo-ness only lived
 * in a corner-of-the-screen indicator; the product brief's "never present
 * a fake backend operation as successfully completed" rule bears the most
 * weight on this screen of any in the app.
 */
const PLACEHOLDER_REPLIES = [
  "I don't have a real answer for that yet — chat isn't wired to SAM's reasoning engine in this build. Task execution through the iQOO workspace is live today, though.",
  "This is a placeholder reply. There's no /api/chat endpoint behind this screen (see PHASE5_PLAN.md §F) — the iQOO workspace actually runs things.",
  "Simulated response — nothing here reflects what SAM would actually say. The Command Center's quick input is the one place on this screen that's real.",
];

let counter = 0;

function simulatedDelay(): Promise<void> {
  // A fixed, boring delay rather than something randomized to feel
  // "alive" — this is a demo of the loading state, not a demo of SAM being
  // thoughtful.
  return new Promise((resolve) => setTimeout(resolve, 700));
}

export async function sendDemoMessage(_req: ChatRequest): Promise<ChatResponse> {
  await simulatedDelay();
  const reply = PLACEHOLDER_REPLIES[counter % PLACEHOLDER_REPLIES.length];
  counter += 1;
  return {
    message: {
      id: crypto.randomUUID(),
      role: "assistant",
      content: reply,
      timestamp: new Date().toISOString(),
    },
  };
}
