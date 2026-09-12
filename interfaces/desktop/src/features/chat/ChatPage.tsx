import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ModeBadge } from "@/components/ModeBadge";
import { StatusPill } from "@/components/StatusPill";
import { ChatMessageBubble } from "./ChatMessageBubble";
import { ChatComposer } from "./ChatComposer";
import { sendDemoMessage } from "./demoChatService";
import type { ChatMessage } from "./types";

export function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [thinking, setThinking] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, thinking]);

  const handleSend = async (text: string) => {
    const userMessage: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: text,
      timestamp: new Date().toISOString(),
    };
    const nextHistory = [...messages, userMessage];
    setMessages(nextHistory);
    setThinking(true);
    try {
      const res = await sendDemoMessage({ message: text, history: nextHistory });
      setMessages((prev) => [...prev, res.message]);
    } finally {
      setThinking(false);
    }
  };

  return (
    <div className="mx-auto flex h-full max-w-2xl flex-col">
      <div className="flex items-center gap-2 pb-3">
        <h1 className="text-lg font-semibold text-ink">Chat</h1>
        <ModeBadge mode="demo" />
      </div>

      <p className="mb-4 rounded-md border border-warn/25 bg-warn/5 px-3 py-2 text-xs text-warn">
        Every reply on this screen is a placeholder — there's no chat engine behind it (see
        PHASE5_PLAN.md §A). For something that actually runs, use the{" "}
        <Link to="/iqoo" className="underline">
          iQOO workspace
        </Link>
        .
      </p>

      <div className="flex-1 space-y-3 overflow-y-auto">
        {messages.length === 0 && (
          <p className="pt-10 text-center text-sm text-mute">Send something to see the placeholder flow.</p>
        )}
        {messages.map((m) => (
          <ChatMessageBubble key={m.id} message={m} />
        ))}
        {thinking && (
          <div className="flex justify-start">
            <StatusPill state="THINKING" label="SAM (demo) is drafting a reply" />
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <div className="pt-3">
        <ChatComposer onSend={handleSend} disabled={thinking} />
      </div>
    </div>
  );
}
