/**
 * There is no real chat endpoint anywhere in this backend (confirmed —
 * see PHASE5_PLAN.md §A/§F: main.py calls Brain.process(session) in-process
 * inside the voice loop, never as a request/response cycle). So unlike
 * src/api/types.ts, which mirrors a real Pydantic model file, these types
 * are a proposal for what a future endpoint would need — kept in
 * features/chat/ rather than src/api/ specifically so that distinction
 * stays visible in the file layout, not just in a comment.
 */

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
}

export interface ChatRequest {
  message: string;
  /** Sent from the client because nothing establishes a server-side
   * session/conversation concept today — a real implementation might move
   * this server-side once one exists, at which point this shrinks to just
   * `message` (+ a session id). */
  history: ChatMessage[];
}

export interface ChatResponse {
  message: ChatMessage;
}
