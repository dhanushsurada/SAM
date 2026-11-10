/**
 * The voice interaction as a state machine, free of React and the browser so
 * every transition can be tested in Node. VoiceProvider.tsx does the side
 * effects (microphone, task submission, playback); this file only decides
 * what each event means in each state.
 *
 *   idle --PRESS--> starting --STARTED--> listening --PRESS--> sending
 *     --SUBMITTED--> working --TASK_FINISHED--> speaking --SPEECH_ENDED--> idle
 *
 * STOP leaves any state for idle. An event that makes no sense in the
 * current state (a late STARTED after the user cancelled, a stale
 * TASK_FINISHED for an earlier task) returns the same state object, so it is
 * harmless and React does not re-render.
 */

export type VoiceState =
  | { kind: "idle" }
  /** Asking the OS for the microphone (can sit on a permission prompt). */
  | { kind: "starting" }
  | { kind: "listening" }
  /** Recording finished; encoding it and creating the task. */
  | { kind: "sending" }
  /** The voice task is running (transcribing, planning, executing…). */
  | { kind: "working"; taskId: string }
  /** SAM is reading the reply; `preparing` until audio actually starts. */
  | { kind: "speaking"; taskId: string; preparing: boolean }
  | { kind: "error"; message: string };

export type VoiceEvent =
  | { type: "PRESS" }
  | { type: "STARTED" }
  | { type: "START_FAILED"; message: string }
  | { type: "RECORDING_ENDED" }
  | { type: "RECORDING_FAILED"; message: string }
  | { type: "SUBMITTED"; taskId: string }
  | { type: "SUBMIT_FAILED"; message: string }
  | { type: "TASK_FINISHED"; taskId: string; speak: boolean }
  | { type: "AUDIO_STARTED" }
  | { type: "SPEECH_ENDED" }
  | { type: "STOP" }
  | { type: "DISMISS" };

export const IDLE: VoiceState = { kind: "idle" };

export function voiceReducer(state: VoiceState, event: VoiceEvent): VoiceState {
  switch (event.type) {
    case "PRESS":
      switch (state.kind) {
        case "idle":
        case "error":
          return { kind: "starting" };
        case "starting":
          return IDLE; // pressed again before the mic opened: cancel
        case "listening":
          return { kind: "sending" };
        default:
          return state; // sending / working / speaking: the button is Stop
      }
    case "STARTED":
      return state.kind === "starting" ? { kind: "listening" } : state;
    case "START_FAILED":
      return state.kind === "starting" ? { kind: "error", message: event.message } : state;
    case "RECORDING_ENDED": // the recorder stopped by itself (maximum length)
      return state.kind === "listening" ? { kind: "sending" } : state;
    case "RECORDING_FAILED":
      return state.kind === "listening" || state.kind === "sending"
        ? { kind: "error", message: event.message }
        : state;
    case "SUBMITTED":
      return state.kind === "sending" ? { kind: "working", taskId: event.taskId } : state;
    case "SUBMIT_FAILED":
      return state.kind === "sending" ? { kind: "error", message: event.message } : state;
    case "TASK_FINISHED":
      if (state.kind !== "working" || state.taskId !== event.taskId) return state;
      return event.speak ? { kind: "speaking", taskId: state.taskId, preparing: true } : IDLE;
    case "AUDIO_STARTED":
      return state.kind === "speaking" && state.preparing ? { ...state, preparing: false } : state;
    case "SPEECH_ENDED":
      return state.kind === "speaking" ? IDLE : state;
    case "STOP":
      return state.kind === "idle" ? state : IDLE;
    case "DISMISS":
      return state.kind === "error" ? IDLE : state;
  }
}

/** The microphone is open, or about to be. */
export function isCapturing(state: VoiceState): boolean {
  return state.kind === "starting" || state.kind === "listening";
}

/** Quick Assistant Escape dismisses its window; it must not withdraw a task
 * SAM has already accepted, but should stop capture, an in-flight submit, or
 * playback. */
export function shouldStopOnQuickAssistantEscape(state: VoiceState): boolean {
  return isCapturing(state) || state.kind === "sending" || state.kind === "speaking";
}

/** Something is in progress that Stop would end. */
export function isBusy(state: VoiceState): boolean {
  return state.kind !== "idle" && state.kind !== "error";
}
