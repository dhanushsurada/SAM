import type { Decision, TasteItem, PendingCapture } from "./types";

export const DEMO_DECISIONS: Decision[] = [
  {
    id: "d1",
    decision: "Use modern desktop interface with unified state management",
    reasoning: "Provides instantaneous task feedback and persistent local session state.",
    confidence: 0.95,
    timestamp: "2026-09-11T01:20:00Z",
  },
  {
    id: "d2",
    decision: "Persist conversations and memories in local SQLite",
    reasoning: "Guarantees offline sovereignty and zero external telemetry.",
    confidence: 0.92,
    timestamp: "2026-09-11T01:25:00Z",
  },
];

export const DEMO_TASTE: TasteItem[] = [
  { category: "communication", preference: "concise, direct status updates", confidence: 0.95 },
  { category: "engineering", preference: "local-first, privacy-focused architecture", confidence: 0.98 },
];

export const DEMO_PENDING: PendingCapture[] = [
  { id: "p1", table: "decisions", content: "Auto-sync local database backups periodically." },
  { id: "p2", table: "taste", content: "Prefers minimal distraction and high execution speed." },
];
