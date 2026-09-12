import type { Decision, TasteItem, PendingCapture } from "./types";

export const DEMO_DECISIONS: Decision[] = [
  {
    id: "d1",
    decision: "Use interfaces/desktop/ instead of frontend/ for the new UI",
    reasoning: "frontend/ belongs to VEDA, a different product on a different branch.",
    confidence: 0.95,
    timestamp: "2026-09-11T01:20:00Z",
  },
  {
    id: "d2",
    decision: "Keep interfaces/web/ untouched rather than merging it in",
    reasoning: "It's real, working, and hackathon-critical — not worth the risk right now.",
    confidence: 0.88,
    timestamp: "2026-09-11T01:25:00Z",
  },
];

export const DEMO_TASTE: TasteItem[] = [
  { category: "communication", preference: "concise, direct status updates", confidence: 0.91 },
  { category: "engineering", preference: "honest about what's demo vs. real", confidence: 0.97 },
];

export const DEMO_PENDING: PendingCapture[] = [
  { id: "p1", table: "decisions", content: "Prioritize the iQOO workspace over Chat given the hackathon date." },
  { id: "p2", table: "taste", content: "Prefers reusing existing patterns over introducing new dependencies." },
];
