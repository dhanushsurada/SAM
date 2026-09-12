export interface Decision {
  id: string;
  decision: string;
  reasoning: string;
  confidence: number;
  timestamp: string;
}

export interface TasteItem {
  category: string;
  preference: string;
  confidence: number;
}

export interface PendingCapture {
  id: string;
  table: string;
  content: string;
}
