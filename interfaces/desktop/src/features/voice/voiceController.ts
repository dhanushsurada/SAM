/**
 * The voice interaction's controller: the side effects the state machine
 * (voiceMachine.ts) leaves out. It opens the microphone, sends the recording
 * to SAM as a task, waits for the task, and speaks the reply. It is written
 * without React so that the sequencing that goes wrong in real use can be
 * tested in Node: Stop pressed while a message is still being sent, an
 * answer that arrives after Stop, a recording that ends by itself.
 *
 * Everything that outlives the click that started it is tagged with an
 * "attempt" number. Stop, and starting over, bump it; an answer that arrives
 * afterwards is recognised as stale and ignored, so it cannot move the state
 * somewhere the user has already left.
 */

import { IDLE, voiceReducer } from "./voiceMachine.ts";
import type { VoiceEvent, VoiceState } from "./voiceMachine.ts";
import { RecordingCancelled } from "./recorder.ts";
import type { Recording, RecordingResult } from "./recorder.ts";
import { replyToSpeak } from "./speechText.ts";
import type { FinishedTask } from "./speechText.ts";
import type { SpeakResult } from "./speak.ts";
import { VOICE_PLACEHOLDER } from "./taskLabel.ts";
import { READ_FAILED, SEND_FAILED } from "./voiceText.ts";

/** What a touch-to-talk task looks like on the wire (a TaskCreateRequest). */
export interface VoiceTaskRequest {
  instruction: string;
  input_type: "voice";
  attachments: Array<{ kind: "audio"; mime_type: string; data: string; filename: string }>;
}

export interface VoiceControllerDeps {
  /** Opens the microphone and starts recording; gives up when `signal` aborts. */
  startRecording(signal: AbortSignal): Promise<Recording>;
  /** The recording as base64, without a "data:" prefix. */
  encode(blob: Blob): Promise<string>;
  /** Creates the task. Resolves with its id, or null when it could not be created. */
  submit(request: VoiceTaskRequest): Promise<string | null>;
  cancelTask(taskId: string): Promise<void>;
  /** Says `text` out loud; `onAudioStart` is called when sound is about to begin. */
  speak(text: string, signal: AbortSignal, onAudioStart: () => void): Promise<SpeakResult>;
  /** Called inside the click: browsers only allow audio to start after a gesture. */
  unlockAudio(): void;
  /** Silences whatever is playing, or about to play. */
  stopAudio(): void;
  /** Something worth telling the user quietly (not an error). */
  onNotice?(text: string): void;
}

export interface VoiceController {
  getState(): VoiceState;
  subscribe(listener: () => void): () => void;
  /** The mic button: talk, send, or (while SAM is busy) stop. */
  press(): void;
  /** Stops everything: closes the microphone, silences speech, and cancels
   * the voice task if it is still running. */
  stop(): void;
  dismissError(): void;
  /** A task reached a final state. Ignored unless it is the voice task being
   * waited for; otherwise its reply is spoken (when `speakReplies`). */
  taskFinished(task: FinishedTask & { task_id: string }, speakReplies: boolean): void;
  /** The owner is going away: close the microphone and silence audio. Leaves
   * any running task alone. */
  dispose(): void;
}

function messageOf(error: unknown): string {
  return error instanceof Error && error.message ? error.message : "Something went wrong with the microphone.";
}

export function createVoiceController(deps: VoiceControllerDeps): VoiceController {
  let state: VoiceState = IDLE;
  let attempt = 0;
  let abort: AbortController | null = null;
  let recording: Recording | null = null;
  const listeners = new Set<() => void>();

  const dispatch = (event: VoiceEvent): VoiceState => {
    const next = voiceReducer(state, event);
    if (next !== state) {
      state = next;
      for (const listener of [...listeners]) listener();
    }
    return state;
  };

  const isCurrent = (mine: number) => mine === attempt;
  const ignoreFailure = (work: Promise<unknown>) => {
    work.catch(() => {});
  };

  /** Everything in flight now belongs to the past. */
  const invalidate = () => {
    attempt += 1;
    abort?.abort();
    abort = null;
    recording?.cancel();
    recording = null;
    deps.stopAudio();
  };

  const recordAndSend = async (mine: number, signal: AbortSignal): Promise<void> => {
    let started: Recording;
    try {
      started = await deps.startRecording(signal);
    } catch (error) {
      if (isCurrent(mine)) dispatch({ type: "START_FAILED", message: messageOf(error) });
      return;
    }
    if (!isCurrent(mine)) {
      started.cancel(); // the user gave up while the microphone was opening
      return;
    }
    recording = started;
    dispatch({ type: "STARTED" });

    let result: RecordingResult;
    try {
      result = await started.finished;
    } catch (error) {
      if (!isCurrent(mine) || error instanceof RecordingCancelled) return;
      recording = null;
      dispatch({ type: "RECORDING_FAILED", message: messageOf(error) });
      return;
    }
    if (!isCurrent(mine)) return;
    recording = null;
    dispatch({ type: "RECORDING_ENDED" }); // a no-op unless the recorder stopped by itself

    let data: string;
    try {
      data = await deps.encode(result.blob);
    } catch {
      if (isCurrent(mine)) dispatch({ type: "RECORDING_FAILED", message: READ_FAILED });
      return;
    }
    if (!isCurrent(mine)) return;

    let taskId: string | null;
    try {
      taskId = await deps.submit({
        instruction: VOICE_PLACEHOLDER,
        input_type: "voice",
        attachments: [{ kind: "audio", mime_type: result.mimeType, data, filename: "voice-message" }],
      });
    } catch {
      taskId = null;
    }
    if (!isCurrent(mine)) {
      // Stop was pressed while the message was on its way. The task exists
      // now, so withdraw it: SAM must not act on a command the user took back.
      if (taskId !== null) ignoreFailure(Promise.resolve(deps.cancelTask(taskId)));
      return;
    }
    if (taskId === null) {
      dispatch({ type: "SUBMIT_FAILED", message: SEND_FAILED });
      return;
    }
    dispatch({ type: "SUBMITTED", taskId });
  };

  const begin = () => {
    attempt += 1;
    const controller = new AbortController();
    abort = controller;
    dispatch({ type: "PRESS" }); // idle or error -> starting
    void recordAndSend(attempt, controller.signal);
  };

  const stop = () => {
    if (state.kind === "idle") return;
    const runningTask = state.kind === "working" ? state.taskId : null;
    invalidate();
    if (runningTask !== null) ignoreFailure(Promise.resolve(deps.cancelTask(runningTask)));
    dispatch({ type: "STOP" });
  };

  return {
    getState: () => state,

    subscribe(listener) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },

    press() {
      // Audio playback is optional. A webview can reject AudioContext
      // construction; that must not prevent starting or stopping capture.
      try {
        deps.unlockAudio();
      } catch {
        // Keep the microphone controls usable without Web Audio.
      }
      switch (state.kind) {
        case "idle":
        case "error":
          begin();
          return;
        case "starting":
          invalidate(); // pressed again before the microphone opened: cancel
          dispatch({ type: "PRESS" });
          return;
        case "listening":
          dispatch({ type: "PRESS" }); // -> sending
          recording?.stop(); // `finished` now resolves with the audio
          return;
        default:
          stop(); // sending, working, speaking: the button is Stop
      }
    },

    stop,

    dismissError() {
      dispatch({ type: "DISMISS" });
    },

    taskFinished(task, speakReplies) {
      const reply = speakReplies ? replyToSpeak(task) : null;
      const before = state;
      const next = dispatch({ type: "TASK_FINISHED", taskId: task.task_id, speak: reply !== null });
      // The state machine only moves for the task being waited for; any other
      // task (or the same one twice) leaves the state as it was.
      if (next === before || reply === null) return;

      const mine = attempt;
      const controller = new AbortController();
      abort = controller;
      void (async () => {
        try {
          const result = await deps.speak(reply, controller.signal, () => {
            if (isCurrent(mine)) dispatch({ type: "AUDIO_STARTED" });
          });
          if (!isCurrent(mine)) return;
          if (result.notice) deps.onNotice?.(result.notice);
        } catch {
          // Speaking is a courtesy; the reply is already on screen.
        }
        if (isCurrent(mine)) dispatch({ type: "SPEECH_ENDED" });
      })();
    },

    dispose() {
      invalidate();
      dispatch({ type: "STOP" });
    },
  };
}
