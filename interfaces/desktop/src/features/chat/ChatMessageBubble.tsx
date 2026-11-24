import { useState } from "react";
import {
  FiMic,
  FiCopy,
  FiCheck,
  FiVolume2,
  FiVolumeX,
  FiThumbsUp,
  FiThumbsDown,
  FiX,
  FiSend,
  FiEdit2,
  FiRefreshCw,
  FiCornerDownLeft,
} from "react-icons/fi";
import { speechService } from "@/services/speech";
import { submitTaskFeedback } from "@/api/client";
import type { ChatMessage } from "./types";

const ASSISTANT_TONE = {
  default: "border-line bg-surface text-ink",
  danger: "border-danger/25 bg-danger/5 text-danger",
  muted: "border-line bg-surface text-mute",
} as const;

export interface ChatMessageBubbleProps {
  message: ChatMessage;
  onEditPrompt?: (messageId: string, newContent: string) => void;
  onQuoteToComposer?: (content: string) => void;
  onRegenerate?: (messageId: string) => void;
  isThinking?: boolean;
}

export function ChatMessageBubble({
  message,
  onEditPrompt,
  onQuoteToComposer,
  onRegenerate,
  isThinking = false,
}: ChatMessageBubbleProps) {
  const isUser = message.role === "user";
  const [copied, setCopied] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [editText, setEditText] = useState(message.content);
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

  const handleSaveEdit = () => {
    if (!editText.trim() || editText.trim() === message.content) {
      setIsEditing(false);
      return;
    }
    setIsEditing(false);
    onEditPrompt?.(message.id, editText.trim());
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
      {isUser && isEditing ? (
        <div className="w-full min-w-[280px] max-w-[640px] rounded-xl border border-ember/50 bg-surface/95 p-3 shadow-panel backdrop-blur-md">
          <textarea
            value={editText}
            onChange={(e) => setEditText(e.target.value)}
            className="w-full resize-none rounded-lg border border-line bg-void/80 p-2.5 text-xs text-ink placeholder:text-mute focus:border-ember focus:outline-none font-sans"
            rows={Math.min(8, Math.max(2, editText.split("\n").length))}
            autoFocus
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                e.preventDefault();
                handleSaveEdit();
              } else if (e.key === "Escape") {
                setIsEditing(false);
                setEditText(message.content);
              }
            }}
          />
          <div className="mt-2 flex items-center justify-between text-xs">
            <span className="text-[11px] text-mute">
              Press <kbd className="rounded border border-line px-1 py-0.5 font-mono text-[9px]">⌘ Enter</kbd> to submit
            </span>
            <div className="flex items-center gap-1.5">
              <button
                type="button"
                onClick={() => {
                  setIsEditing(false);
                  setEditText(message.content);
                }}
                className="rounded-md border border-line px-2.5 py-1 text-xs text-mute hover:bg-surface hover:text-ink transition-colors cursor-pointer"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleSaveEdit}
                disabled={!editText.trim() || isThinking}
                className="flex items-center gap-1 rounded-md bg-ember px-3 py-1 text-xs font-medium text-ember-ink hover:opacity-90 transition-opacity disabled:opacity-50 cursor-pointer"
              >
                <FiCheck size={12} /> Save & Submit
              </button>
            </div>
          </div>
        </div>
      ) : (
        <div
          className={`relative max-w-[85%] whitespace-pre-wrap rounded-xl px-3.5 py-2.5 text-sm shadow-sm transition-all ${
            isUser ? "bg-ember text-ember-ink font-medium" : `border ${ASSISTANT_TONE[message.tone ?? "default"]}`
          }`}
        >
          {message.via === "voice" && <FiMic size={12} className="mr-1.5 inline align-[-1px]" aria-label="Spoken" />}
          {message.content}

          {/* Action icons row */}
          <div
            className={`mt-1.5 flex flex-wrap items-center gap-2 pt-1 border-t ${
              isUser ? "border-ember-ink/20 text-ember-ink/80" : "border-line/60 text-mute"
            } text-xs opacity-75 group-hover:opacity-100 transition-opacity`}
          >
            {/* Copy button (all messages) */}
            <button
              type="button"
              onClick={handleCopy}
              className="flex items-center gap-1 hover:text-ink transition-colors cursor-pointer"
              title="Copy text"
            >
              {copied ? <FiCheck size={11} className="text-emerald-500" /> : <FiCopy size={11} />}
              <span>{copied ? "Copied" : "Copy"}</span>
            </button>

            {/* User message options: Edit & Reuse */}
            {isUser && onEditPrompt && (
              <button
                type="button"
                onClick={() => {
                  setEditText(message.content);
                  setIsEditing(true);
                }}
                disabled={isThinking}
                className="flex items-center gap-1 hover:text-ink transition-colors cursor-pointer disabled:opacity-40"
                title="Edit prompt and re-run (ChatGPT / Claude style)"
              >
                <FiEdit2 size={11} />
                <span>Edit</span>
              </button>
            )}

            {isUser && onQuoteToComposer && (
              <button
                type="button"
                onClick={() => onQuoteToComposer(message.content)}
                className="flex items-center gap-1 hover:text-ink transition-colors cursor-pointer"
                title="Quote or reuse prompt in composer"
              >
                <FiCornerDownLeft size={11} />
                <span>Reuse</span>
              </button>
            )}

            {/* Assistant message options: Regenerate & Speak */}
            {!isUser && onRegenerate && (
              <button
                type="button"
                onClick={() => onRegenerate(message.id)}
                disabled={isThinking}
                className="flex items-center gap-1 hover:text-ink transition-colors cursor-pointer disabled:opacity-40"
                title="Regenerate this answer"
              >
                <FiRefreshCw size={11} className={isThinking ? "animate-spin text-ember" : ""} />
                <span>Retry</span>
              </button>
            )}

            {!isUser && (
              <button
                type="button"
                onClick={handleSpeak}
                className={`flex items-center gap-1 transition-colors cursor-pointer ${
                  speaking ? "text-ember font-medium" : "hover:text-ink"
                }`}
                title={speaking ? "Stop speaking" : "Listen / Read aloud"}
              >
                {speaking ? <FiVolumeX size={11} /> : <FiVolume2 size={11} />}
                <span>{speaking ? "Stop" : "Read aloud"}</span>
              </button>
            )}

            {/* Optional Feedback System */}
            {!isUser && message.taskId && feedbackState === "idle" && (
              <div className="flex items-center gap-1 border-l border-line/60 pl-2">
                <span className="text-[10px] text-mute mr-0.5">Feedback:</span>
                <button
                  type="button"
                  onClick={() => void handleFeedback("positive")}
                  className="hover:text-emerald-500 p-0.5 transition-colors cursor-pointer"
                  title="Good execution (reinforces this path in memory)"
                >
                  <FiThumbsUp size={11} />
                </button>
                <button
                  type="button"
                  onClick={() => setFeedbackState("negative-open")}
                  className="hover:text-rose-500 p-0.5 transition-colors cursor-pointer"
                  title="Needs improvement (provide optional critique/advice)"
                >
                  <FiThumbsDown size={11} />
                </button>
              </div>
            )}

            {feedbackResult && feedbackState === "submitted" && (
              <span className="text-[10px] text-emerald-500 border-l border-line/60 pl-2 font-medium">
                {feedbackResult}
              </span>
            )}

            {message.timestamp && (
              <span className="ml-auto text-[10px] opacity-60 font-mono-data">
                {new Date(message.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
              </span>
            )}
          </div>

          {/* Expandable critique form on negative feedback */}
          {!isUser && feedbackState === "negative-open" && (
            <div className="mt-2 pt-2 border-t border-line/60 text-xs space-y-1.5">
              <p className="text-[11px] text-mute">What could SAM improve? (optional)</p>
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
                  className="px-2 py-1 bg-ember text-ember-ink rounded text-xs hover:opacity-90 transition-opacity flex items-center gap-1 cursor-pointer"
                >
                  <FiSend size={10} />
                  <span>Submit</span>
                </button>
                <button
                  type="button"
                  onClick={() => setFeedbackState("idle")}
                  className="p-1 text-mute hover:text-ink transition-colors cursor-pointer"
                  title="Dismiss"
                >
                  <FiX size={12} />
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
