import { useState } from "react";
import { FiMic, FiCopy, FiCheck, FiVolume2, FiVolumeX } from "react-icons/fi";
import { speechService } from "@/services/speech";
import type { ChatMessage } from "./types";

const ASSISTANT_TONE = {
  default: "border-line bg-surface text-ink",
  danger: "border-danger/25 bg-danger/5 text-danger",
  muted: "border-line bg-surface text-mute",
} as const;

export function ChatMessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  const [copied, setCopied] = useState(false);
  const [speaking, setSpeaking] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(message.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // ignore
    }
  };

  const handleSpeak = async () => {
    if (speaking) {
      if (typeof window !== "undefined" && window.speechSynthesis) {
        window.speechSynthesis.cancel();
      }
      setSpeaking(false);
      return;
    }

    setSpeaking(true);
    try {
      // 1. Try SAM's high-quality backend speech
      const audioBuffer = await speechService.synthesize(message.content);
      const AudioCtx = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      const ctx = new AudioCtx();
      const decoded = await ctx.decodeAudioData(audioBuffer.slice(0));
      const source = ctx.createBufferSource();
      source.buffer = decoded;
      source.connect(ctx.destination);
      source.onended = () => {
        setSpeaking(false);
        void ctx.close();
      };
      source.start(0);
    } catch {
      // 2. Fall back to browser Web Speech API
      if (typeof window !== "undefined" && window.speechSynthesis) {
        window.speechSynthesis.cancel();
        const utterance = new SpeechSynthesisUtterance(message.content);
        utterance.onend = () => setSpeaking(false);
        utterance.onerror = () => setSpeaking(false);
        window.speechSynthesis.speak(utterance);
      } else {
        setSpeaking(false);
      }
    }
  };

  return (
    <div className={`group flex flex-col ${isUser ? "items-end" : "items-start"}`}>
      <div
        className={`relative max-w-[85%] whitespace-pre-wrap rounded-lg px-3.5 py-2.5 text-sm ${
          isUser ? "bg-ember text-ember-ink" : `border ${ASSISTANT_TONE[message.tone ?? "default"]}`
        }`}
      >
        {message.via === "voice" && <FiMic size={12} className="mr-1.5 inline align-[-1px]" aria-label="Spoken" />}
        {message.content}

        {/* Action icons row */}
        <div className={`mt-1.5 flex items-center gap-2 pt-1 border-t ${isUser ? "border-ember-ink/20 text-ember-ink/80" : "border-line/60 text-mute"} text-xs opacity-75 group-hover:opacity-100 transition-opacity`}>
          <button
            type="button"
            onClick={handleCopy}
            className="flex items-center gap-1 hover:text-ink transition-colors"
            title="Copy message text"
          >
            {copied ? <FiCheck size={12} className="text-emerald-500" /> : <FiCopy size={12} />}
            <span>{copied ? "Copied" : "Copy"}</span>
          </button>

          {!isUser && (
            <button
              type="button"
              onClick={handleSpeak}
              className={`flex items-center gap-1 transition-colors ${speaking ? "text-ember font-medium" : "hover:text-ink"}`}
              title={speaking ? "Stop speaking" : "Listen / Read aloud"}
            >
              {speaking ? <FiVolumeX size={12} /> : <FiVolume2 size={12} />}
              <span>{speaking ? "Stop" : "Read aloud"}</span>
            </button>
          )}

          {message.timestamp && (
            <span className="ml-auto text-[10px] opacity-60">
              {new Date(message.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
