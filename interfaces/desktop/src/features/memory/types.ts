export interface Episode {
  id: string;
  content: string;
  timestamp: string;
  retention_days: number;
}

export interface SemanticMemory {
  id: string;
  content: string;
  score: number;
  category: string;
}
