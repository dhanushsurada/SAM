import type { Episode, SemanticMemory } from "./types";

const DEMO_EPISODES: Episode[] = [
  { id: "e1", content: "Completed weekly code audit and generated optimization report.", timestamp: "2026-09-10T14:22:00Z", retention_days: 30 },
  { id: "e2", content: "Tested terminal and desktop browser automation tools.", timestamp: "2026-09-10T11:05:00Z", retention_days: 30 },
  { id: "e3", content: "Configured local Ollama model routing preferences.", timestamp: "2026-09-09T19:40:00Z", retention_days: 90 },
];

const DEMO_SEMANTIC: SemanticMemory[] = [
  { id: "s1", content: "Prefers concise status updates over long summaries.", score: 0.91, category: "communication" },
  { id: "s2", content: "Primary dev machine runs Ollama with SparkLLM / Qwen models.", score: 0.88, category: "environment" },
  { id: "s3", content: "Prefers dark mode with clean typography and fast shortcuts.", score: 0.82, category: "context" },
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
