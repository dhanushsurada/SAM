import type { ChatMessage } from "./types";

const ASSISTANT_TONE = {
  default: "border-line bg-surface text-ink",
  danger: "border-danger/25 bg-danger/5 text-danger",
  muted: "border-line bg-surface text-mute",
} as const;

export function ChatMessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[80%] whitespace-pre-wrap rounded-lg px-3.5 py-2.5 text-sm ${
          isUser ? "bg-ember text-ember-ink" : `border ${ASSISTANT_TONE[message.tone ?? "default"]}`
        }`}
      >
        {message.content}
      </div>
    </div>
  );
}
