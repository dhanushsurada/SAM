import { useEffect, useRef, useState } from "react";
import { FiMic, FiSquare, FiVolume2, FiVolumeX, FiX, FiSliders, FiCheck, FiPlay } from "react-icons/fi";
import { useTaskSession } from "@/stores/taskSession";
import { useVoice } from "./VoiceProvider";
import { isBusy } from "./voiceMachine";
import { taskLabel } from "./taskLabel";
import type { LabelledTask } from "./taskLabel";

/** How a task's instruction is shown: a voice task shows what SAM heard. */
export function useTaskLabel(): (task: LabelledTask) => string {
  const { transcripts } = useTaskSession();
  return (task) => taskLabel(task, transcripts);
}

/**
 * The mic button. Pressing it starts listening; pressing it again sends;
 * while SAM is sending, working or speaking it is Stop. `blockStart` keeps
 * a new recording from starting (another task is running) without taking
 * away Stop.
 */
export function VoiceMicButton({ blockStart = false, size = 16 }: { blockStart?: boolean; size?: number }) {
  const { state, unavailableReason, micLabel, press } = useVoice();
  const suppressRapidPress = useRef(false);
  const rapidPressTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => {
    if (rapidPressTimer.current !== null) clearTimeout(rapidPressTimer.current);
  }, []);
  const handlePress = () => {
    if (suppressRapidPress.current) return;
    suppressRapidPress.current = true;
    rapidPressTimer.current = setTimeout(() => {
      suppressRapidPress.current = false;
      rapidPressTimer.current = null;
    }, 400);
    press();
  };
  const canStart = state.kind === "idle" || state.kind === "error";
  const disabled = canStart && (unavailableReason !== null || blockStart);
  const stopLike = state.kind === "sending" || state.kind === "working" || state.kind === "speaking";
  const listening = state.kind === "listening";

  const look = listening
    ? "bg-danger text-ink animate-pulse"
    : state.kind === "starting"
      ? "text-ember-text animate-pulse"
      : stopLike
        ? "text-ember-text hover:bg-void"
        : state.kind === "error"
          ? "text-danger hover:bg-void"
          : "text-mute hover:bg-void hover:text-ink";

  return (
    <button
      type="button"
      onClick={handlePress}
      disabled={disabled}
      aria-label={micLabel}
      aria-pressed={listening}
      title={disabled && unavailableReason ? unavailableReason : micLabel}
      data-voice-state={state.kind}
      className={`flex items-center rounded-md p-2 transition-colors duration-[var(--sam-motion-state)] disabled:cursor-not-allowed disabled:opacity-40 ${look}`}
    >
      {stopLike ? <FiSquare size={size - 2} /> : <FiMic size={size} />}
    </button>
  );
}

/** Turns spoken replies on or off. Replies to typed messages are never spoken. */
export function VoiceSpeakToggle({ size = 16 }: { size?: number }) {
  const { speakReplies, setSpeakReplies } = useVoice();
  const label = speakReplies ? "Turn off spoken replies" : "Turn on spoken replies";
  return (
    <button
      type="button"
      onClick={() => setSpeakReplies(!speakReplies)}
      aria-pressed={speakReplies}
      aria-label={label}
      title={label}
      className="flex items-center rounded-md p-2 text-mute transition-colors duration-[var(--sam-motion-state)] hover:bg-void hover:text-ink"
    >
      {speakReplies ? <FiVolume2 size={size} /> : <FiVolumeX size={size} />}
    </button>
  );
}

/** Controls silent mode priority override and digital volume boost. */
export function VoiceAudioPriorityControl({ size = 16 }: { size?: number }) {
  const { audioConfig, setAudioConfig, speak } = useVoice();
  const [open, setOpen] = useState(false);
  const [testing, setTesting] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [open]);

  const handleTestAudio = async () => {
    setTesting(true);
    try {
      await speak("SAM voice override is active and audible.");
    } finally {
      setTesting(false);
    }
  };

  const dbGain = Math.round(20 * Math.log10(audioConfig.volumeBoost || 1.6));

  return (
    <div className="relative inline-block" ref={containerRef}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-label="Voice audibility and silent mode settings"
        title="Voice priority & audibility in silent mode"
        className={`relative flex items-center rounded-md p-2 transition-colors duration-[var(--sam-motion-state)] hover:bg-void ${
          audioConfig.overrideSilentMode ? "text-ember-text font-medium" : "text-mute hover:text-ink"
        }`}
      >
        <FiSliders size={size} />
        {audioConfig.overrideSilentMode && (
          <span
            className="absolute top-1 right-1 h-2 w-2 rounded-full bg-ember shadow-[0_0_6px_rgb(var(--sam-ember)/0.7)]"
            title="Silent mode override active"
          />
        )}
      </button>

      {open && (
        <div className="absolute right-0 bottom-full mb-2 w-72 rounded-xl border border-line/80 bg-surface/95 p-3.5 shadow-2xl backdrop-blur-xl z-50 animate-in fade-in zoom-in-95 duration-150">
          <div className="flex items-center justify-between border-b border-line/40 pb-2.5 mb-2.5">
            <div>
              <p className="text-xs font-semibold text-ink">Voice Priority & Gain</p>
              <p className="text-[10px] text-mute">Audible in silent / low volume</p>
            </div>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="rounded p-1 text-mute hover:text-ink"
              aria-label="Close"
            >
              <FiX size={12} />
            </button>
          </div>

          <div className="space-y-3">
            {/* Override Switch */}
            <div className="flex items-start justify-between gap-2">
              <div>
                <p className="text-xs font-medium text-ink">Audible in Silent Mode</p>
                <p className="text-[10px] text-mute leading-snug mt-0.5">
                  Play voice through speakers even when system/media volumes are kept low.
                </p>
              </div>
              <button
                type="button"
                role="switch"
                aria-checked={audioConfig.overrideSilentMode}
                onClick={() => setAudioConfig({ overrideSilentMode: !audioConfig.overrideSilentMode })}
                className={`relative inline-flex h-4.5 w-8 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out ${
                  audioConfig.overrideSilentMode ? "bg-ember" : "bg-line"
                }`}
              >
                <span
                  className={`pointer-events-none inline-block h-3.5 w-3.5 transform rounded-full bg-void shadow-md transition duration-200 ease-in-out ${
                    audioConfig.overrideSilentMode ? "translate-x-3.5" : "translate-x-0"
                  }`}
                />
              </button>
            </div>

            {/* Gain Boost Slider */}
            {audioConfig.overrideSilentMode && (
              <div className="space-y-1.5 pt-1 border-t border-line/30">
                <div className="flex items-center justify-between text-[11px]">
                  <span className="text-mute font-medium">Gain Boost</span>
                  <span className="font-mono text-ink text-xs font-semibold">
                    {audioConfig.volumeBoost.toFixed(1)}x ({dbGain >= 0 ? `+${dbGain}` : dbGain} dB)
                  </span>
                </div>
                <input
                  type="range"
                  min="1.0"
                  max="2.5"
                  step="0.1"
                  value={audioConfig.volumeBoost}
                  onChange={(e) => setAudioConfig({ volumeBoost: parseFloat(e.target.value) })}
                  className="w-full h-1.5 bg-line/80 rounded-lg appearance-none cursor-pointer accent-ember"
                />
                <div className="flex justify-between text-[9px] text-mute">
                  <span>1.0x (Normal)</span>
                  <span>1.8x (Balanced)</span>
                  <span>2.5x (Max Boost)</span>
                </div>
              </div>
            )}

            {/* Test Audibility Button */}
            <div className="pt-1 border-t border-line/30">
              <button
                type="button"
                onClick={handleTestAudio}
                disabled={testing}
                className="w-full flex items-center justify-center gap-1.5 rounded-lg border border-line/60 bg-void/70 py-1.5 text-xs font-medium text-ink hover:border-ember/50 hover:bg-void transition-colors disabled:opacity-50"
              >
                {testing ? <FiCheck size={12} className="text-success animate-spin" /> : <FiPlay size={12} className="text-ember" />}
                <span>{testing ? "Playing test voice..." : "Test Voice Audibility"}</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/** What voice is doing, in a sentence, and what to do about it. An assistive
 * technology reads changes to it aloud. */
export function VoiceStatusLine({ showUnavailable = false }: { showUnavailable?: boolean }) {
  const { state, status, unavailableReason, notice, dismissNotice, dismissError } = useVoice();
  const hint = showUnavailable && state.kind === "idle" ? unavailableReason : null;
  const text = status || hint || "";
  const isError = state.kind === "error";

  return (
    <div role="status" aria-live="polite" data-voice-status={state.kind}>
      {text && (
        <p className={`flex items-start gap-2 text-xs ${isError ? "text-danger" : "text-mute"}`}>
          <span className="min-w-0 flex-1">{text}</span>
          {isError && (
            <button type="button" onClick={dismissError} aria-label="Dismiss" className="shrink-0 text-mute hover:text-ink">
              <FiX size={12} />
            </button>
          )}
        </p>
      )}
      {notice && (
        <p className="mt-1 flex items-start gap-2 text-xs text-mute">
          <span className="min-w-0 flex-1">{notice}</span>
          <button type="button" onClick={dismissNotice} aria-label="Dismiss" className="shrink-0 hover:text-ink">
            <FiX size={12} />
          </button>
        </p>
      )}
    </div>
  );
}

/** A small always-visible indicator with Stop, for the top bar: the person
 * can leave the page that has the mic and still see, and stop, what voice is
 * doing. */
export function VoiceTopBarIndicator() {
  const { state, shortStatus, stop, dismissError } = useVoice();
  if (state.kind === "idle") return null;
  const isError = state.kind === "error";
  const busy = isBusy(state);

  return (
    <div
      className={`flex items-center gap-2 rounded-md border px-2 py-1 text-xs ${
        isError ? "border-danger/30 text-danger" : "border-line text-ember-text"
      }`}
      data-voice-indicator={state.kind}
    >
      <span
        aria-hidden="true"
        className={`h-2 w-2 rounded-full ${isError ? "bg-danger" : "animate-pulse bg-ember"}`}
      />
      <span>{shortStatus}</span>
      {busy && (
        <button
          type="button"
          onClick={stop}
          aria-label="Stop voice"
          title="Stop (Esc)"
          className="flex items-center text-mute hover:text-ink"
        >
          <FiSquare size={12} />
        </button>
      )}
      {isError && (
        <button type="button" onClick={dismissError} aria-label="Dismiss" className="flex items-center text-mute hover:text-ink">
          <FiX size={12} />
        </button>
      )}
    </div>
  );
}
