/**
 * A chat message is a view of a task, not a separate backend concept. SAM
 * has no dedicated chat endpoint and no server-side conversation (Session.
 * history is empty for every gateway task), so Chat sends each message as a
 * task through the same gateway everything else uses and shows the task's
 * outcome as SAM's reply. See ChatPage.tsx for what that does and doesn't
 * give you.
 */

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
  /** Visual treatment for an assistant reply that isn't a plain answer. */
  tone?: "default" | "danger" | "muted";
}
