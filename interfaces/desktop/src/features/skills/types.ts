export interface Skill {
  name: string;
  description: string;
  compiled: boolean;
  last_used: string | null;
  use_count: number;
}

export const DEMO_SKILLS: Skill[] = [
  { name: "open_youtube_and_search", description: "Opens YouTube and searches for a given query.", compiled: true, last_used: "2026-09-10T14:00:00Z", use_count: 12 },
  { name: "summarize_pdf", description: "Extracts and summarizes text from a local PDF.", compiled: true, last_used: "2026-09-08T09:12:00Z", use_count: 4 },
  { name: "fill_web_form", description: "Fills a detected web form from provided field values.", compiled: false, last_used: null, use_count: 0 },
];
