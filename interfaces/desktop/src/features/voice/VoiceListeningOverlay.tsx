import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { FiMic, FiSend, FiX, FiEdit3 } from "react-icons/fi";
import { useVoice } from "./VoiceProvider";
import { Button } from "@/components/Button";

export function VoiceListeningOverlay() {
  const {
    state,
    liveTranscript,
    setLiveTranscript,
    wakeWordDetected,
    submitRectifiedText,
    press,
    stop,
  } = useVoice();

  const [isEditing, setIsEditing] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const isListening = state.kind === "listening" || state.kind === "starting" || wakeWordDetected;

  useEffect(() => {
    if (isListening && inputRef.current && !isEditing) {
      // Auto scroll to end of live transcript as speech streams in
      inputRef.current.scrollTop = inputRef.current.scrollHeight;
    }
  }, [liveTranscript, isListening, isEditing]);

  if (!isListening) return null;

  const handleSend = async () => {
    if (liveTranscript.trim()) {
      await submitRectifiedText(liveTranscript.trim());
    } else {
      press(); // Fallback to sending recorded audio directly
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void handleSend();
    } else if (e.key === "Escape") {
      e.preventDefault();
      stop();
    }
  };

  return (
    <aside
      aria-label="Voice input and real-time transcription"
      className="fixed inset-x-0 bottom-6 z-50 flex justify-center px-4 pointer-events-none animate-sam-slide-up"
    >
      <div className="pointer-events-auto w-full max-w-xl overflow-hidden rounded-2xl border border-ember/50 bg-surface/95 p-4 shadow-2xl backdrop-blur-2xl ring-1 ring-ember/20 text-ink">
        {/* Top Header Bar */}
        <div className="flex items-center justify-between border-b border-line/40 pb-2.5 mb-2.5">
          <div className="flex items-center gap-2.5">
            {/* Animated Pulsing Soundwave / Mic Badge */}
            <div className="relative flex h-8 w-8 items-center justify-center rounded-xl bg-ember/15 border border-ember/40 text-ember-text">
              <span className="absolute -inset-1 rounded-xl bg-ember/30 animate-ping opacity-60" />
              <FiMic size={15} className="relative z-10 animate-pulse" />
            </div>

            <div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-semibold text-ink flex items-center gap-1.5">
                  <span className="h-2 w-2 rounded-full bg-ember animate-pulse shadow-[0_0_8px_rgb(var(--sam-ember)/0.8)]" />
                  {wakeWordDetected ? "Wake Word Detected: Hey SAM" : "SAM is Listening..."}
                </span>
                <span className="rounded bg-ember/10 border border-ember/20 px-1.5 py-0.5 text-[9px] font-mono text-ember-text uppercase tracking-wider">
                  Live STT
                </span>
              </div>
              <p className="text-[11px] text-mute">
                Transcribing simultaneously. Click below anytime to rectify.
              </p>
            </div>
          </div>

          {/* Soundwave Bars Visualizer */}
          <div className="flex items-center gap-1 px-2 h-5">
            <span className="w-1 bg-ember/70 rounded-full animate-bounce [animation-delay:-0.3s] h-3" />
            <span className="w-1 bg-ember rounded-full animate-bounce [animation-delay:-0.15s] h-5" />
            <span className="w-1 bg-ember/90 rounded-full animate-bounce [animation-delay:-0.4s] h-4" />
            <span className="w-1 bg-ember rounded-full animate-bounce [animation-delay:-0.2s] h-6" />
            <span className="w-1 bg-ember/80 rounded-full animate-bounce [animation-delay:-0.35s] h-3.5" />
          </div>

          <button
            type="button"
            onClick={stop}
            className="rounded-lg p-1 text-mute hover:bg-void hover:text-ink transition-colors ml-2"
            aria-label="Cancel listening"
            title="Cancel (Esc)"
          >
            <FiX size={16} />
          </button>
        </div>

        {/* Real-Time Live Transcript Input (Directly Editable / Rectifiable) */}
        <div className="relative rounded-xl border border-line/60 bg-void/70 p-2.5 transition-all focus-within:border-ember focus-within:ring-1 focus-within:ring-ember/30">
          <textarea
            ref={inputRef}
            rows={2}
            value={liveTranscript}
            onChange={(e) => {
              setIsEditing(true);
              setLiveTranscript(e.target.value);
            }}
            onFocus={() => setIsEditing(true)}
            onKeyDown={handleKeyDown}
            placeholder="Listening... speak now. Words will appear simultaneously in real time..."
            className="w-full resize-none bg-transparent text-xs text-ink placeholder:text-mute/60 focus:outline-none leading-relaxed"
          />

          {isEditing && (
            <span className="absolute right-2 bottom-2 flex items-center gap-1 text-[10px] text-ember-text bg-surface/90 px-1.5 py-0.5 rounded border border-ember/20 shadow-xs pointer-events-none">
              <FiEdit3 size={10} /> Editing / Rectifying
            </span>
          )}
        </div>

        {/* Bottom Actions & Shortcuts */}
        <div className="flex items-center justify-between pt-2.5 mt-2 border-t border-line/30">
          <div className="flex items-center gap-2 text-[10px] text-mute font-mono">
            <span>↵ Enter to send</span>
            <span>·</span>
            <span>Esc to cancel</span>
          </div>

          <div className="flex items-center gap-2">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={stop}
              className="text-xs h-7 px-2.5 text-mute hover:text-ink"
            >
              Cancel
            </Button>

            <Button
              type="button"
              variant="primary"
              size="sm"
              onClick={handleSend}
              className="text-xs h-7 px-3 flex items-center gap-1.5 shadow-sm"
            >
              <FiSend size={11} />
              <span>Send Command</span>
            </Button>
          </div>
        </div>
      </div>
    </aside>
  );
}
