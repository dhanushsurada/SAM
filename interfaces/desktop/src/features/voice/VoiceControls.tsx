import { useEffect, useRef } from "react";
import { FiMic, FiSquare, FiVolume2, FiVolumeX, FiX } from "react-icons/fi";
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
