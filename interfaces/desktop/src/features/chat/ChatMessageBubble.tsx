import { useState } from "react";
import { FiMic, FiCopy, FiCheck, FiVolume2, FiVolumeX, FiThumbsUp, FiThumbsDown, FiX, FiSend } from "react-icons/fi";
import { speechService } from "@/services/speech";
import { submitTaskFeedback } from "@/api/client";
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
  const [feedbackState, setFeedbackState] = useState<"idle" | "negative-open" | "submitted">("idle");
  const [feedbackComment, setFeedbackComment] = useState("");
  const [feedbackSubmitting, setFeedbackSubmitting] = useState(false);
  const [feedbackResult, setFeedbackResult] = useState<string | null>(null);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(message.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // ignore
    }
  };

  const handleFeedback = async (rating: "positive" | "negative", comment?: string) => {
    if (!message.taskId || feedbackSubmitting) return;
    setFeedbackSubmitting(true);
    try {
      await submitTaskFeedback(message.taskId, rating, comment);
      setFeedbackResult(rating === "positive" ? "Path saved to Founder Mode ✓" : "Critique saved to Founder Mode ✓");
      setFeedbackState("submitted");
    } catch {
      setFeedbackResult("Feedback recorded");
      setFeedbackState("submitted");
    } finally {
      setFeedbackSubmitting(false);
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
        <div className={`mt-1.5 flex flex-wrap items-center gap-2 pt-1 border-t ${isUser ? "border-ember-ink/20 text-ember-ink/80" : "border-line/60 text-mute"} text-xs opacity-80 group-hover:opacity-100 transition-opacity`}>
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

          {/* Minimal Optional Feedback System */}
          {!isUser && message.taskId && feedbackState === "idle" && (
            <div className="flex items-center gap-1 border-l border-line/60 pl-2">
              <span className="text-[11px] text-mute mr-1">Feedback:</span>
              <button
                type="button"
                onClick={() => void handleFeedback("positive")}
                className="hover:text-emerald-500 p-0.5 transition-colors"
                title="Good execution (reinforces this path in memory)"
              >
                <FiThumbsUp size={12} />
              </button>
              <button
                type="button"
                onClick={() => setFeedbackState("negative-open")}
                className="hover:text-rose-500 p-0.5 transition-colors"
                title="Needs improvement (provide optional critique/advice)"
              >
                <FiThumbsDown size={12} />
              </button>
            </div>
          )}

          {feedbackResult && feedbackState === "submitted" && (
            <span className="text-[10px] text-emerald-500 border-l border-line/60 pl-2 font-medium">
              {feedbackResult}
            </span>
          )}

          {message.timestamp && (
            <span className="ml-auto text-[10px] opacity-60">
              {new Date(message.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
            </span>
          )}
        </div>

        {/* Expandable critique / advice form on negative feedback */}
        {!isUser && feedbackState === "negative-open" && (
          <div className="mt-2 pt-2 border-t border-line/60 text-xs space-y-1.5">
            <p className="text-[11px] text-mute">What could SAM improve? (optional, can skip or close)</p>
            <div className="flex items-center gap-1.5">
              <input
                type="text"
                value={feedbackComment}
                onChange={(e) => setFeedbackComment(e.target.value)}
                placeholder="e.g. execute in background, verify element..."
                className="flex-1 bg-surface border border-line rounded px-2 py-1 text-xs text-ink placeholder:text-mute/60 focus:outline-none focus:border-ember"
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    void handleFeedback("negative", feedbackComment);
                  }
                }}
              />
              <button
                type="button"
                onClick={() => void handleFeedback("negative", feedbackComment)}
                disabled={feedbackSubmitting}
                className="px-2 py-1 bg-ember text-ember-ink rounded text-xs hover:opacity-90 transition-opacity flex items-center gap-1"
              >
                <FiSend size={10} />
                <span>Submit</span>
              </button>
              <button
                type="button"
                onClick={() => setFeedbackState("idle")}
                className="p-1 text-mute hover:text-ink transition-colors"
                title="Dismiss"
              >
                <FiX size={12} />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
