import type { ChatMessage } from "./types";

export function ChatMessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[80%] rounded-lg px-3.5 py-2.5 text-sm ${
          isUser ? "bg-ember text-ember-ink" : "border border-line bg-surface text-ink"
        }`}
      >
        {message.content}
      </div>
    </div>
  );
}
