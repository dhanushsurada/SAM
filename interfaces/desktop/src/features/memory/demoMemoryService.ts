import type { Episode, SemanticMemory } from "./types";

const DEMO_EPISODES: Episode[] = [
  { id: "e1", content: "Asked SAM to summarize the iQOO PDR before the team sync.", timestamp: "2026-09-10T14:22:00Z", retention_days: 30 },
  { id: "e2", content: "Ran the demo-reset flow twice while testing the retry endpoint.", timestamp: "2026-09-10T11:05:00Z", retention_days: 30 },
  { id: "e3", content: "Discussed the Office Kit's unverified hardware assumptions.", timestamp: "2026-09-09T19:40:00Z", retention_days: 90 },
];

const DEMO_SEMANTIC: SemanticMemory[] = [
  { id: "s1", content: "Prefers concise status updates over long summaries.", score: 0.91, category: "communication" },
  { id: "s2", content: "Primary dev machine runs Ollama with qwen2.5:14b.", score: 0.84, category: "environment" },
  { id: "s3", content: "Hackathon deadline: iQOO x Reskilll, Sept 26-27.", score: 0.79, category: "context" },
];

export function getRecentEpisodes(): Episode[] {
  return DEMO_EPISODES;
}

/** A real (if trivial) substring match over canned data — search isn't a
 * dead control, it's just not hitting ChromaDB. */
export function searchSemantic(query: string): SemanticMemory[] {
  const q = query.trim().toLowerCase();
  if (!q) return [];
  return DEMO_SEMANTIC.filter((m) => m.content.toLowerCase().includes(q) || m.category.includes(q));
}
